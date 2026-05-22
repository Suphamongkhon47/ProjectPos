from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Sum, Count, F
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from datetime import datetime, timedelta
import json
from django.core.paginator import Paginator
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from products.Services.payment_service import PaymentService
from products.models import Transaction, TransactionItem, Product, Supplier 
from products.Services.return_service import (
    create_return_transaction,
    post_return,
    validate_return_eligibility,
    cancel_return as service_cancel_return 
)


# ===================================
# 1. หน้าหลักรับคืนสินค้า
# ===================================
@login_required
def returns(request):
    """หน้ารับคืนสินค้าหลัก"""
    
    today = datetime.now()
    doc_prefix = f"RET-{today.strftime('%Y%m%d')}"
    
    # นับบิลรับคืนวันนี้
    today_returns_count = Transaction.objects.filter(
        doc_no__startswith=doc_prefix,
        doc_type='RETURN'
    ).count()
    
    next_number = str(today_returns_count + 1).zfill(4)
    doc_no = f"{doc_prefix}-{next_number}"
    
    context = {
        'doc_no': doc_no,
        'today': today,
    }
    
    return render(request, 'products/returns/return_product.html', context)


# ===================================
# 2. ค้นหาบิลเดิม (AJAX) - Smart Search
# ===================================
@login_required
@require_http_methods(["GET"])
def search_sale_for_return(request):
    """
    ค้นหาบิลเดิมสำหรับรับคืน
    """
    query = request.GET.get('q', '').strip()
    
    if len(query) < 3:
        return JsonResponse({'success': False, 'error': 'กรุณากรอกอย่างน้อย 3 ตัวอักษร'}, status=400)
    
    try:
        # -------------------------------------------------------
        # ✅ จุดที่แก้ไข: ลบ 'payment' ออกจาก select_related
        # -------------------------------------------------------
        sale = Transaction.objects.filter(
            doc_no__icontains=query,
            doc_type='SALE',
            status='POSTED' # ⚠️ ต้องมั่นใจว่าบิลเป็นสถานะนี้
        ).select_related('created_by').first() # เหลือแค่ created_by พอ
        
        if not sale:
            return JsonResponse({'success': False, 'error': 'ไม่พบบิลที่ค้นหา (หรือสถานะไม่ใช่ "ขายแล้ว")'}, status=404)
        
        # ตรวจสอบความพร้อมในการคืน (ถ้ามีฟังก์ชันนี้)
        try:
            validate_return_eligibility(sale)
        except ValueError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
        # ดึงรายการสินค้า
        items = sale.items.select_related('product', 'product__category').all()
        
        # ... (ส่วนคำนวณจำนวนคืน history คงเดิม) ...
        returned_items = {}
        returns_history = Transaction.objects.filter(doc_type='RETURN', ref_doc_no=sale.doc_no, status='POSTED')
        for ret in returns_history:
            for ret_item in ret.items.all():
                returned_items[ret_item.product_id] = returned_items.get(ret_item.product_id, 0) + ret_item.quantity

        items_data = []
        for item in items:
            already_returned = returned_items.get(item.product_id, 0)
            remaining = item.quantity - already_returned
            
            if remaining > 0:
                # ⭐ ใช้ข้อมูลจาก TransactionItem
                display_sku = item.display_sku or item.product.sku
                display_name = item.product.name
                
                # ⭐ ถ้าขายเป็นคู่/ชุด → ใช้ base_name
                if item.unit_type in ['คู่', 'ชุด']:
                    display_name = item.product.base_name or item.product.name
                
                items_data.append({
                    'id': item.id,
                    'product_id': item.product.id,
                    'sku': display_sku,  # ✅ MIR-VIOS
                    'name': display_name,  # ✅ กระจก
                    'unit': item.unit_type or item.product.unit,  # ✅ คู่
                    'original_quantity': float(item.quantity),
                    'already_returned': float(already_returned),
                    'remaining_quantity': float(remaining),
                    'unit_price': float(item.unit_price),  # ✅ 1000
                    'cost_price': float(item.cost_price),
                    'unit_type': item.unit_type or 'ชิ้น',  # ⭐ เพิ่ม
                    'bundle_items': item.bundle_items  # ⭐ เพิ่ม
                })
        
        # ดึง Payment Method อย่างปลอดภัย
        payment_method = 'ไม่ระบุ'
        if hasattr(sale, 'payment'):
            payment_method = sale.payment.method

        # ข้อมูลบิล
        transaction_data = {
            'id': sale.id,
            'doc_no': sale.doc_no,
            # ✅ ใช้ TransactionItem_date ให้ตรง Model
            'sale_date': sale.transaction_date.strftime('%d/%m/%Y %H:%M'), 
            'grand_total': float(sale.grand_total),
            'created_by': sale.created_by.get_full_name() or sale.created_by.username,
            'payment_method': payment_method,
            'items': items_data,
        }
        
        return JsonResponse({
            'success': True,
            'sale': transaction_data 
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'เกิดข้อผิดพลาด: {str(e)}'}, status=500)


# ===================================
# 3. บันทึกบิลรับคืน (AJAX)
# ===================================
@login_required
@require_http_methods(["POST"])
def create_return(request):
    """
    บันทึกบิลรับคืนสินค้า
    """
    
    try:
        data = json.loads(request.body)
        
        doc_no = data.get('doc_no')
        ref_doc_no = data.get('ref_doc_no')
        items = data.get('items', [])
        
        return_reason = data.get('return_reason', 'other')
        return_note = data.get('return_note', '')
        
        refund_method = data.get('refund_method', 'cash')
        refund_bank = data.get('refund_bank', '')
        refund_account = data.get('refund_account', '')
        refund_name = data.get('refund_name', '')
        
        discount_return = Decimal(str(data.get('discount_return', 0)))
        
        if not ref_doc_no:
            return JsonResponse({'success': False, 'error': 'ไม่พบเลขที่บิลเดิม'}, status=400)
        
        if not items:
            return JsonResponse({'success': False, 'error': 'ไม่มีรายการสินค้าที่คืน'}, status=400)
        
        if Transaction.objects.filter(doc_no=doc_no).exists():
             today_str = datetime.now().strftime('%Y%m%d')
             prefix = f"RET-{today_str}"
             last = Transaction.objects.filter(doc_no__startswith=prefix).count()
             doc_no = f"{prefix}-{str(last + 1).zfill(4)}"
        
        original_transaction = get_object_or_404(
            Transaction,
            doc_no=ref_doc_no,
            doc_type='SALE',
            status='POSTED'
        )
        
        validate_return_eligibility(original_transaction)
        
        # สร้าง Return Transaction
        return_transaction = create_return_transaction(
            user=request.user,
            ref_doc_no=ref_doc_no,
            items_data=items,
            return_reason=return_reason,
            return_note=return_note,
            discount_amount=discount_return,
            doc_no=doc_no
        )
        
        refund_amount = -abs(return_transaction.grand_total)
        
        # ✅ แก้ไข 4: เรียก PaymentService ด้วย transaction_obj= (ตามที่ตกลงกัน)
        PaymentService.create_payment(
            sale=return_transaction, # เปลี่ยนจาก sale= เป็น transaction_obj=
            method=refund_method,
            received=refund_amount,
            note=f"คืนเงิน: {return_reason}\n{return_note}"
        )
          
        post_return(return_transaction)

        # ===== Broadcast WebSocket → Dashboard =====
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "dashboard",
            {
                "type": "dashboard.update",
                "data": {
                    "event": "sale_posted",
                    "doc_no": return_transaction.doc_no,
                    "grand_total": float(return_transaction.grand_total),
                }
            }
        )

        return JsonResponse({
            'success': True,
            'sale_id': return_transaction.id,
            'doc_no': return_transaction.doc_no,
            'grand_total': float(return_transaction.grand_total),
            'status': return_transaction.status,
            'redirect_url': f'/returns/{return_transaction.id}/'
        })
        
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'เกิดข้อผิดพลาด: {str(e)}'}, status=500)


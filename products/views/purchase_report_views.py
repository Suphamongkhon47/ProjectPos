"""
products/views/purchase_report_views.py
รายงานการนำเข้าสินค้า - แสดงข้อมูลเดิม
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from products.models import Purchase, PurchaseItem, Supplier
User = get_user_model() # ✅ ประกาศ User Model


def purchase_report(request):
    """หน้ารายงานการนำเข้าสินค้า"""
    
    today = timezone.now().date()
    first_day = today.replace(day=1)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from: date_from = first_day.strftime('%Y-%m-%d')
    if not date_to: date_to = today.strftime('%Y-%m-%d')

    purchases = Purchase.objects.select_related('supplier', 'created_by').prefetch_related('items')
    
    # --- Filter Logic ---
    try:
        d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        dt_from = timezone.make_aware(datetime.combine(d_from, time.min))
        purchases = purchases.filter(purchase_date__gte=dt_from)
    except: pass

    try:
        d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        dt_to = timezone.make_aware(datetime.combine(d_to, time.max))
        purchases = purchases.filter(purchase_date__lte=dt_to)
    except: pass

    search = request.GET.get('search', '').strip()
    if search:
        purchases = purchases.filter(
            Q(doc_no__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(remark__icontains=search)
        )
    
    supplier_id = request.GET.get('supplier', '')
    if supplier_id: purchases = purchases.filter(supplier_id=supplier_id)
    
    created_by_id = request.GET.get('created_by', '')
    if created_by_id: purchases = purchases.filter(created_by_id=created_by_id)

    status = request.GET.get('status', '')
    if status: purchases = purchases.filter(status=status)
    
    purchases = purchases.order_by('-purchase_date', '-id')
    
    # ✅ FIX: แยกคำนวณเพื่อความถูกต้อง 100% (แก้ปัญหาเลขเบิ้ล/นับผิด)
    # 1. นับจำนวนบิล (Count Purchase)
    total_purchases = purchases.count()
    
    # 2. ยอดเงินรวม (Sum Grand Total) - คำนวณจากหัวบิลโดยตรง
    total_amount = purchases.aggregate(Sum('grand_total'))['grand_total__sum'] or Decimal('0')
    
    stats = {
        'total_purchases': total_purchases, # เลขนี้จะโชว์ 1 (ถ้ามี 1 บิล)
        'total_amount': total_amount
    }
    
    # Pagination
    paginator = Paginator(purchases, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    suppliers = Supplier.objects.order_by('name')
    users = User.objects.filter(is_active=True).order_by('username')
    
    last_purchase_id = request.session.pop('last_purchase_id', None)
    
    context = {
        'page_obj': page_obj,
        'suppliers': suppliers,
        'users': users,
        'search': search,
        'supplier_id': supplier_id,
        'created_by_id': created_by_id,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
        'last_purchase_id': last_purchase_id,
    }
    return render(request, 'products/reports/purchase_report.html', context)

def purchase_detail(request, id):
    """
    หน้ารายละเอียดบิลนำเข้า
    แสดงข้อมูลเดิม ไม่เพิ่มเติม
    """

    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier', 'created_by').prefetch_related('items__product__category'), 
        id=id
    )

    # ดึงรายการสินค้า
    items = purchase.items.select_related('product__category').order_by('id')
    
    # คำนวณยอดรวม
    total_amount = Decimal('0')
    for item in items:
        total_amount += item.line_total
    
    context = {
        'purchase': purchase,
        'items': items,
        'total_amount': total_amount,
    }
    
    return render(request, 'products/reports/purchase_detail.html', context)


def cancel_purchase(request, id):
    """
    ยกเลิกเอกสารรับเข้า (เฉพาะ DRAFT)
    """
    
    if request.method != 'POST':
        return redirect('purchase_report')
    
    purchase = get_object_or_404(Purchase, id=id)
    
    if purchase.status == 'POSTED':
        messages.error(request, "❌ ไม่สามารถยกเลิกเอกสารที่ยืนยันแล้ว (POSTED)")
        return redirect('purchase_detail', id=id)
    
    if purchase.status == 'CANCELLED':
        messages.warning(request, "⚠️ เอกสารนี้ยกเลิกแล้ว")
        return redirect('purchase_detail', id=id)
    
    # ยกเลิก
    purchase.status = 'CANCELLED'
    purchase.save(update_fields=['status'])
    
    messages.success(request, f"✅ ยกเลิกเอกสาร {purchase.doc_no} เรียบร้อยแล้ว")
    return redirect('purchase_report')

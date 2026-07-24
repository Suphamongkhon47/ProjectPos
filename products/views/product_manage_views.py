from datetime import timedelta
from decimal import Decimal
from itertools import product

from django.db import transaction
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator

# ✅ เพิ่ม import user_passes_test
from django.contrib.auth.decorators import login_required, user_passes_test
from products.Services.product_service import ProductService
from products.models import Product, Category, StockMovement , TransactionItem ,PurchaseItem

# =========================================================
# ✅ ฟังก์ชันเช็คสิทธิ์ (เฉพาะ Superuser เท่านั้น)
# =========================================================
def is_superuser_check(user):
    return user.is_superuser

# =========================================================
# Views
# =========================================================

@login_required
@user_passes_test(is_superuser_check)
def manage_products(request):
    """แสดงรายการสินค้าทั้งหมด พร้อมค้นหาและกรอง"""
    
    # ===== รับค่าจากฟอร์มค้นหา =====
    search = request.GET.get('search', '').strip()
    category_id = request.GET.get('category', '')
    stock_status = request.GET.get('stock_status', '')
    
    # ===== Query สินค้า =====
    # prefetch_related bundle_components เพื่อลด query เวลาคำนวณสต็อก
    products = Product.objects.select_related('category').prefetch_related('bundle_components').order_by('sku')
    
    # ค้นหา
    if search:
        products = products.filter(
            Q(sku__icontains=search) |
            Q(name__icontains=search)
        )
    
    # กรองตามหมวดหมู่
    if category_id:
        products = products.filter(category_id=category_id)
    
    # ✅ กรองตามสถานะสต็อก (ปรับปรุงใหม่ รองรับ Bundle)
    if stock_status:
        products_list = []
        # หมายเหตุ: การวน loop กรองแบบนี้อาจช้าถ้าสินค้าเยอะมาก 
        # แต่อยู่ในขอบเขตที่ยอมรับได้สำหรับระบบจัดการหลังบ้าน
        for p in products:
            # ใช้ Service คำนวณสต็อกจริง (รวมถึง Bundle)
            status_data = ProductService.get_stock_status(p)
            qty = status_data['quantity']
            
            if stock_status == 'in_stock' and qty > 10:
                products_list.append(p)
            elif stock_status == 'low_stock' and 0 < qty <= 10:
                products_list.append(p)
            elif stock_status == 'out_of_stock' and qty <= 0:
                products_list.append(p)
        
        products = products_list
    
    # ===== Pagination =====
    paginator = Paginator(products, 20)
    page = request.GET.get('page', 1)
    products_page = paginator.get_page(page)
    
    # ===== เพิ่ม stock_quantity ให้แต่ละสินค้า (สำหรับแสดงผล) =====
    for product in products_page:
        # ✅ เรียกใช้ Service คำนวณสต็อกที่จะโชว์
        # ถ้าเป็น Bundle มันจะไปนับลูกมาให้ ถ้าเป็นปกติก็โชว์ตามจริง
        status_data = ProductService.get_stock_status(product)
        product.stock_quantity = status_data['quantity'] # แปะค่ากลับเข้าไปเพื่อเอาไปโชว์ใน HTML
    
    # ===== Context =====
    context = {
        'products': products_page,
        'categories': Category.objects.order_by('name'),
        'search': search,
        'category_id': category_id,
        'stock_status': stock_status,
        'total_products': len(products) if isinstance(products, list) else products.count(),
    }
    
    return render(request, 'products/manage/manage_products.html', context)


@login_required
@user_passes_test(is_superuser_check)
def edit_product(request, product_id):
    """แก้ไขข้อมูลสินค้า"""
    product = get_object_or_404(Product, id=product_id)
    categories = Category.objects.all().order_by('name')

    if request.method == 'POST':
        try:
            # รับข้อมูลจากฟอร์ม
            sku = request.POST.get('sku', '').strip()
            name = request.POST.get('name', '').strip()
            category_id = request.POST.get('category')
            cost_price = request.POST.get('cost_price', 0)
            selling_price = request.POST.get('selling_price', 0)
            wholesale_price = request.POST.get('wholesale_price', 0)
            unit = request.POST.get('unit', '').strip()
            min_quantity = request.POST.get('min_quantity', 0)
            description = request.POST.get('description', '')
            
            # Checkbox
            is_active = request.POST.get('is_active') == 'on'
            is_bundle = request.POST.get('is_bundle') == 'on' # ✅ รับค่า is_bundle

            # Validation
            if sku != product.sku and Product.objects.filter(sku=sku).exists():
                messages.error(request, f"❌ รหัสสินค้า '{sku}' มีอยู่ในระบบแล้ว")
                return redirect('edit_product', product_id=product_id)

            if not sku or not name:
                messages.error(request, "❌ กรุณากรอกรหัสสินค้าและชื่อสินค้า")
                return redirect('edit_product', product_id=product_id)

            # อัปเดตข้อมูล
            product.sku = sku
            product.name = name
            product.category_id = category_id if category_id else None
            product.cost_price = Decimal(str(cost_price))
            product.selling_price = Decimal(str(selling_price))
            product.wholesale_price = Decimal(str(wholesale_price))
            product.unit = unit
            product.min_quantity = int(min_quantity)
            product.description = description
            product.is_active = is_active
            product.is_bundle = is_bundle # ✅ บันทึกค่า is_bundle

            product.save()

            messages.success(request, f"✅ บันทึกข้อมูลสินค้า '{product.name}' เรียบร้อยแล้ว")
            return redirect('manage_products')

        except Exception as e:
            messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")
            return redirect('edit_product', product_id=product_id)

    context = {
        'product': product,
        'categories': categories,
    }
    return render(request, 'products/manage/edit_product.html', context)


@login_required
@user_passes_test(is_superuser_check) # 🔒 ล็อกสิทธิ์
def delete_product(request, product_id):
    """ลบสินค้า - เช็คเงื่อนไข"""
    
    if request.method != 'POST':
        messages.warning(request, '⚠️ กรุณาใช้ฟอร์มในการลบสินค้า')
        return redirect('manage_products')
    
    product = get_object_or_404(Product, id=product_id)
    sku = product.sku
    product_name = product.name
    
    # ===== เช็คเงื่อนไข =====
    can_delete = True
    error_reasons = []
    
    # เช็ค Movement OUT
    out_movements = StockMovement.objects.filter(product=product,movement_type='OUT')
    if out_movements.exists():
        out_count = out_movements.count()
        total_out = out_movements.aggregate(Sum('quantity'))['quantity__sum'] or 0
        
        can_delete = False
        error_reasons.append(
            f"📤 <strong>มีประวัติการจ่ายออก/ขาย:</strong> {out_count} รายการ "
            f"(รวม {total_out:.0f} ชิ้น)"
        )
    
    # เช็ค SaleItem
    try:   
        sale_items = TransactionItem.objects.filter(product=product)
        if sale_items.exists():
            sale_count = sale_items.count()
            can_delete = False
            error_reasons.append(
                f"📋 <strong>มีในรายการขาย:</strong> {sale_count} รายการ"
            )
    except (ImportError, AttributeError):
        pass
    
    # เช็ค PurchaseItem
    try:
        
        purchase_items = PurchaseItem.objects.filter(product=product)
        if purchase_items.exists():
            purchase_count = purchase_items.count()
            can_delete = False
            error_reasons.append(
                f"🛒 <strong>มีในรายการสั่งซื้อ:</strong> {purchase_count} รายการ"
            )
    except (ImportError, AttributeError):
        pass
    
    # ===== ถ้าลบไม่ได้ =====
    if not can_delete:
        error_msg = (
            f"❌ <strong>ไม่สามารถลบสินค้า '{sku}' ได้</strong><br><br>"
            f"<strong>เหตุผล:</strong><br>"
        )
        error_msg += "<br>".join(f"&nbsp;&nbsp;&nbsp;&nbsp;• {reason}" for reason in error_reasons)
        error_msg += (
            "<br><br>💡 <strong>ทำไมลบไม่ได้?</strong><br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;เพื่อรักษาความถูกต้องของข้อมูลธุรกิจและบัญชี<br><br>"
            "<strong>ทางเลือก:</strong><br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;1. ปิดการใช้งาน (is_active = False)<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;2. ปรับสต็อกเป็น 0"
        )
        
        messages.error(request, error_msg)
        return redirect('manage_products')
    
    # ===== คำเตือน =====
    warnings = []
    
    try:
        created_time = product.created_at
        time_since_created = timezone.now() - created_time
        
        if time_since_created > timedelta(hours=24):
            try:
                # แก้ไข: ใช้ p.quantity โดยตรง
                current_stock = product.quantity
                if current_stock > 0:
                    warnings.append(
                        f"⚠️ สินค้ามีสต็อกคงเหลือ <strong>{current_stock:.0f}</strong> ชิ้น"
                    )
            except:
                pass
            
            in_movements = StockMovement.objects.filter(
                product=product,
                movement_type__in=['IN', 'ADJ']
            )
            
            if in_movements.exists():
                in_count = in_movements.count()
                warnings.append(
                    f"ℹ️ มีประวัติการรับเข้า/ปรับยอด <strong>{in_count}</strong> รายการ"
                )
    except:
        pass
    
    if warnings:
        warning_msg = (
            f"⚠️ <strong>คำเตือน:</strong><br>"
            + "<br>".join(f"&nbsp;&nbsp;&nbsp;&nbsp;• {w}" for w in warnings)
        )
        messages.warning(request, warning_msg)
    
    # ===== ลบสินค้า =====
    try:
        with transaction.atomic():
            deleted_data = {}
            
            # ลบ StockMovement
            movement_count = StockMovement.objects.filter(product=product).count()
            if movement_count > 0:
                StockMovement.objects.filter(product=product).delete()
                deleted_data['ประวัติการเคลื่อนไหว'] = movement_count
            
            # ลบ Product
            product.delete()
            
            # Success Message
            success_msg = f"✅ <strong>ลบสินค้า '{sku}' ({product_name}) สำเร็จ</strong>"
            
            if deleted_data:
                success_msg += "<br><br><strong>ข้อมูลที่ถูกลบ:</strong><br>"
                for key, count in deleted_data.items():
                    success_msg += f"&nbsp;&nbsp;&nbsp;&nbsp;• {key}: {count} รายการ<br>"
            
            messages.success(request, success_msg)
            
    except Exception as e:
        messages.error(
            request,
            f"❌ <strong>เกิดข้อผิดพลาด:</strong><br>{str(e)}"
        )
    
    return redirect('manage_products')


@login_required
@user_passes_test(is_superuser_check) # 🔒 ล็อกสิทธิ์
def product_history(request, product_id):
    """ดูประวัติการเคลื่อนไหวสินค้า (รองรับ Bundle ให้โชว์ลูกด้วย)"""
    
    product = get_object_or_404(Product, id=product_id)
    

    if product.is_bundle:
        
        # 2. ค้นหา Movement ที่เป็นของ "ตัวแม่" OR "ลูกๆ"
        movements = StockMovement.objects.filter(product=product).order_by('-created_at') # select_related เพื่อดึงชื่อสินค้าลูกมาแสดง
        
    else:
        # 3. ถ้าเป็นสินค้าปกติ -> ดึงแค่ของตัวเอง
        movements = StockMovement.objects.filter(
            product=product
        ).order_by('-created_at')
    # =========================================================

    total_in = movements.filter(movement_type='IN').aggregate(Sum('quantity'))['quantity__sum'] or 0
    total_out = movements.filter(movement_type='OUT').aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # ✅ ปรับปรุง: ใช้ Service คำนวณสต็อกคงเหลือ (เพื่อให้แม่โชว์จำนวนชุดที่ขายได้จริง)
    try:
        status_data = ProductService.get_stock_status(product)
        current_stock = status_data.get('quantity', 0)
    except:
        current_stock = 0
    
    context = {
        'product': product,
        'movements': movements,
        'total_in': total_in,
        'total_out': total_out,
        'current_stock': current_stock,
    }
    
    return render(request, 'products/manage/product_history.html', context)


@login_required
@user_passes_test(is_superuser_check) # 🔒 ล็อกสิทธิ์
def bulk_delete_products(request):
    """ลบสินค้าหลายรายการพร้อมกัน"""
    
    if request.method != 'POST':
        messages.warning(request, '⚠️ กรุณาใช้ฟอร์มในการลบสินค้า')
        return redirect('manage_products')
    
    product_ids = request.POST.getlist('product_ids')
    
    if not product_ids:
        messages.error(request, '❌ ไม่ได้เลือกสินค้า')
        return redirect('manage_products')
    
    products = Product.objects.filter(id__in=product_ids)
    
    if not products.exists():
        messages.error(request, '❌ ไม่พบสินค้าที่เลือก')
        return redirect('manage_products')
    
    total_selected = products.count()
    deleted_count = 0
    failed_count = 0
    failed_products = []
    
    for product in products:
        can_delete = True
        reasons = []
        
        # เช็ค Movement OUT
        if StockMovement.objects.filter(product=product, movement_type='OUT').exists():
            can_delete = False
            reasons.append("มีประวัติการขาย")
        
        # เช็ค SaleItem
        try:
            if TransactionItem.objects.filter(product=product).exists():
                can_delete = False
                reasons.append("อยู่ในรายการขาย")
        except:
            pass
        
        # เช็ค PurchaseItem
        try:
            from products.models import PurchaseItem
            if PurchaseItem.objects.filter(product=product).exists():
                can_delete = False
                reasons.append("อยู่ในรายการสั่งซื้อ")
        except:
            pass
        
        # ลบ
        if can_delete:
            try:
                with transaction.atomic():
                    StockMovement.objects.filter(product=product).delete()
                    product.delete()
                    deleted_count += 1
            except Exception as e:
                failed_count += 1
                failed_products.append({
                    'sku': product.sku,
                    'reason': str(e)
                })
        else:
            failed_count += 1
            failed_products.append({
                'sku': product.sku,
                'reason': ', '.join(reasons)
            })
    
    # แสดงผล
    if deleted_count > 0:
        messages.success(
            request,
            f"✅ ลบสินค้าสำเร็จ <strong>{deleted_count}/{total_selected}</strong> รายการ"
        )
    
    if failed_count > 0:
        failed_list = "<br>".join([
            f"&nbsp;&nbsp;&nbsp;&nbsp;• <strong>{p['sku']}</strong>: {p['reason']}"
            for p in failed_products[:10]
        ])
        
        messages.warning(
            request,
            f"⚠️ ไม่สามารถลบได้ <strong>{failed_count}/{total_selected}</strong> รายการ:<br><br>"
            f"{failed_list}"
            + (f"<br>&nbsp;&nbsp;&nbsp;&nbsp;... และอีก {failed_count - 10} รายการ" if failed_count > 10 else "")
        )
    
    return redirect('manage_products')
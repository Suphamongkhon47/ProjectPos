from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse
from products.models import Supplier, Product, Purchase  # ใช้ model จาก products app
from products.forms import supplier_form  # จะสร้างในขั้นตอนถัดไป


def supplier_list(request):
    """
    แสดงรายการซัพพลายเออร์ทั้งหมด
    URL: /suppliers/
    """
    if not request.user.is_superuser:
        return render(request, 'products/permission_denied.html', {
            'perm_key': 'Superuser Only (เฉพาะเจ้าของร้าน)',
        }, status=403)
    # ดึงค่าค้นหาจาก GET parameter
    search_query = request.GET.get('search', '').strip()
    
    # Query ฐานข้อมูล
    suppliers = Supplier.objects.all()
    
    # นับจำนวนสินค้าที่นำเข้าจากแต่ละ Supplier
    suppliers = suppliers.annotate(
        product_count=Count('product')
    )
    
    # ค้นหา (ชื่อ หรือ เบอร์โทร)
    if search_query:
        suppliers = suppliers.filter(
            Q(name__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # เรียงตามชื่อ A-Z
    suppliers = suppliers.order_by('name')
    
    # คำนวณสถิติ
    total_suppliers = suppliers.count()
    total_products = sum(s.product_count for s in suppliers)
    
    # Pagination (แสดงหน้าละ 10 รายการ)
    paginator = Paginator(suppliers, 10)
    page_number = request.GET.get('page')
    suppliers_page = paginator.get_page(page_number)
    
    context = {
        'suppliers': suppliers_page,
        'search_query': search_query,
        'total_suppliers': total_suppliers,
        'total_products': total_products,
    }
    
    return render(request, 'products/suppliers/supplier_list.html', context)


def supplier_create(request):
    """
    เพิ่มซัพพลายเออร์ใหม่
    URL: /suppliers/create/
    """
    if not request.user.is_superuser:
        return render(request, 'products/permission_denied.html', {
            'perm_key': 'Superuser Only (เฉพาะเจ้าของร้าน)',
        }, status=403)
    if request.method == 'POST':
        form = supplier_form.SupplierForm(request.POST)
        
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f'✅ เพิ่มซัพพลายเออร์ "{supplier.name}" สำเร็จ!')
            return redirect('supplier_list')
        else:
            messages.error(request, '❌ กรุณาตรวจสอบข้อมูลที่กรอก')
    else:
        form = supplier_form.SupplierForm()
    
    context = {
        'form': form,
        'title': 'เพิ่มซัพพลายเออร์ใหม่',
        'submit_text': 'บันทึก',
        'action': 'create',
    }
    
    return render(request, 'products/suppliers/supplier_form.html', context)


def supplier_edit(request, supplier_id):
    """
    แก้ไขข้อมูลซัพพลายเออร์
    URL: /suppliers/<id>/edit/
    """
    if not request.user.is_superuser:
        return render(request, 'products/permission_denied.html', {
            'perm_key': 'Superuser Only (เฉพาะเจ้าของร้าน)',
        }, status=403)
    from products.forms import SupplierForm
    
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f'✅ แก้ไขข้อมูล "{supplier.name}" สำเร็จ!')
            return redirect('supplier_list')
        else:
            messages.error(request, '❌ กรุณาตรวจสอบข้อมูลที่กรอก')
    else:
        form = SupplierForm(instance=supplier)
    
    context = {
        'form': form,
        'supplier': supplier,
        'title': f'แก้ไข: {supplier.name}',
        'submit_text': 'บันทึกการแก้ไข',
        'action': 'edit',
    }
    
    return render(request, 'products/suppliers/supplier_form.html', context)


def supplier_search_by_product(request):
    """
    API: ค้นหาสินค้า → แสดงซัพพลายเออร์ที่มีสินค้านั้น (Group by Supplier)
    URL: /supplier/search-by-product/?q=ยาง
    Returns: JSON รายชื่อซัพพลายเออร์ที่ไม่ซ้ำกัน
    """
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'results': [], 'count': 0})

    # หา Supplier ที่มีสินค้าตรงคำค้น (Distinct)
    suppliers = Supplier.objects.filter(
        Q(product__name__icontains=q) |
        Q(product__sku__icontains=q) |
        Q(product__compatible_models__icontains=q),
        product__is_active=True,
    ).annotate(
        matched_count=Count('product', filter=
            Q(product__is_active=True) & (
                Q(product__name__icontains=q) |
                Q(product__sku__icontains=q) |
                Q(product__compatible_models__icontains=q)
            )
        )
    ).distinct().order_by('name')

    results = []
    for sup in suppliers:
        results.append({
            'supplier_id': sup.id,
            'supplier_name': sup.name,
            'supplier_phone': sup.phone or '-',
            'supplier_address': sup.address or '-',
            'matched_count': sup.matched_count,
        })

    return JsonResponse({'results': results, 'count': len(results)})


def supplier_products_api(request, supplier_id):
    """
    API: ดึงข้อมูลสินค้า + ประวัตินำเข้าของ Supplier
    URL: /supplier/<id>/products/
    Returns: JSON
    """
    supplier = get_object_or_404(Supplier, id=supplier_id)

    # ─── สินค้าที่เชื่อมกับ Supplier นี้ ───
    products = Product.objects.filter(
        primary_supplier=supplier
    ).select_related('category').order_by('sku')

    products_data = []
    for p in products:
        products_data.append({
            'id': p.id,
            'sku': p.sku,
            'name': p.name,
            'category': p.category.name if p.category else '-',
            'cost_price': float(p.cost_price),
            'selling_price': float(p.selling_price),
            'quantity': float(p.quantity),
            'unit': p.unit,
            'is_active': p.is_active,
            'compatible_models': p.compatible_models or '-',
        })

    # ─── ประวัติการนำเข้าจาก Supplier นี้ (10 รายการล่าสุด) ───
    purchases = Purchase.objects.filter(
        supplier=supplier
    ).select_related('created_by').order_by('-purchase_date')[:10]

    purchases_data = []
    for pu in purchases:
        purchases_data.append({
            'id': pu.id,
            'doc_no': pu.doc_no,
            'purchase_date': pu.purchase_date.strftime('%d/%m/%Y %H:%M'),
            'status': pu.get_status_display(),
            'status_code': pu.status,
            'grand_total': float(pu.grand_total),
            'created_by': pu.created_by.get_full_name() or pu.created_by.username,
        })

    # ─── สถิติรวม ───
    total_purchase_amount = Purchase.objects.filter(
        supplier=supplier, status='POSTED'
    ).aggregate(total=Sum('grand_total'))['total'] or 0

    return JsonResponse({
        'supplier_name': supplier.name,
        'products': products_data,
        'purchases': purchases_data,
        'stats': {
            'product_count': len(products_data),
            'purchase_count': Purchase.objects.filter(supplier=supplier).count(),
            'total_purchase_amount': float(total_purchase_amount),
        }
    })


def supplier_delete(request, supplier_id):
    """
    ลบซัพพลายเออร์
    URL: /suppliers/<id>/delete/
    """
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    if request.method == 'POST':
        supplier_name = supplier.name
        
        # ตรวจสอบว่ามีสินค้าที่เชื่อมโยงอยู่หรือไม่
        product_count = supplier.product_set.count()
        
        if product_count > 0:
            messages.warning(
                request, 
                f'⚠️ ไม่สามารถลบ "{supplier_name}" ได้ เนื่องจากมีสินค้า {product_count} รายการเชื่อมโยงอยู่'
            )
        else:
            supplier.delete()
            messages.success(request, f'✅ ลบ "{supplier_name}" สำเร็จ!')
        
        return redirect('supplier_list')
    
    # ถ้าไม่ใช่ POST ให้กลับไปหน้าหลัก
    return redirect('supplier_list')
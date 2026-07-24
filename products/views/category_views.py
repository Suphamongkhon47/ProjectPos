from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count

from products.models import Category
from products.forms.category_form import CategoryForm


# ===================================
# 1. รายการหมวดหมู่ทั้งหมด
# ===================================
@login_required
def category_list(request):
    """แสดงรายการหมวดหมู่ทั้งหมด"""
    
    # ดึงค่าค้นหา
    search = request.GET.get('search', '').strip()
    
    # Query หมวดหมู่ - ✅ 
    categories = Category.objects.annotate(product_count=Count('product')).order_by('name')
    
    # ✅ เก็บรายการทั้งหมดสำหรับ Dropdown
    all_categories = list(categories)
    
    # ค้นหา
    if search:
        categories = categories.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    # นับสถิติ
    total_categories = categories.count()
    total_products = sum(cat.product_count for cat in categories)
    
    # Pagination (20 รายการต่อหน้า)
    paginator = Paginator(categories, 20)
    page_number = request.GET.get('page')
    categories_page = paginator.get_page(page_number)
    
    context = {
        'categories': categories_page,
        'all_categories': all_categories,  # ✅ เพิ่มบรรทัดนี้
        'total_categories': total_categories,
        'total_products': total_products,
        'search': search,
    }
    
    return render(request, 'products/manage/category_list.html', context)


# ===================================
# 2. เพิ่มหมวดหมู่ใหม่ (AJAX)
# ===================================
@login_required
def category_create(request):
    """เพิ่มหมวดหมู่ใหม่"""
    
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        
        if form.is_valid():
            category = form.save()
            messages.success(request, f'✅ เพิ่มหมวดหมู่ "{category.name}" สำเร็จ')
            return redirect('category_list')
        else:
            # แสดง Error
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    
    return redirect('category_list')


# ===================================
# 3. แก้ไขหมวดหมู่ (AJAX)
# ===================================
@login_required
def category_edit(request, category_id):
    """แก้ไขหมวดหมู่"""
    
    category = get_object_or_404(Category, id=category_id)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        
        if form.is_valid():
            category = form.save()
            messages.success(request, f'✅ แก้ไขหมวดหมู่ "{category.name}" สำเร็จ')
            return redirect('category_list')
        else:
            # แสดง Error
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    
    return redirect('category_list')


# ===================================
# 4. ลบหมวดหมู่
# ===================================
@login_required
def category_delete(request, category_id):
    """ลบหมวดหมู่"""
    
    category = get_object_or_404(Category, id=category_id)
    
    # ✅ เช็คว่ามีสินค้าในหมวดหมู่หรือไม่ - แก้เป็น 'product'
    product_count = category.product_set.count()
    
    if product_count > 0:
        messages.error(
            request, 
            f'❌ ไม่สามารถลบได้! หมวดหมู่ "{category.name}" มีสินค้า {product_count} รายการ'
        )
        return redirect('category_list')
    
    # ลบได้
    category_name = category.name
    category.delete()
    
    messages.success(request, f'✅ ลบหมวดหมู่ "{category_name}" สำเร็จ')
    return redirect('category_list')

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from products.Services.product_service import ProductService


@login_required
def stock_inquiry(request):
    """หน้าตรวจสอบสต็อก"""
    
    # ✅ เรียกใช้ Service
    popular_models = ProductService.get_popular_models(limit=20)
    
    context = {
        'popular_models': popular_models,
    }
    
    return render(request, 'products/stock/inquiry.html', context)


@require_http_methods(["GET"])
def stock_search_api(request):
    """API ค้นหาสินค้า"""
    
    product_query = request.GET.get('product', '').strip()
    model_query = request.GET.get('model', '').strip()
    
    # ต้องมีเงื่อนไขอย่างน้อย 1 อย่าง
    if not product_query and not model_query:
        return JsonResponse({'products': []})
    
    # ✅ เรียกใช้ Service
    products = ProductService.search_products(
        product_query=product_query,
        model_query=model_query,
        limit=50
    )
    
    # แปลงเป็น JSON
    results = []
    for product in products:
        # ✅ เรียกใช้ Service
        stock_status = ProductService.get_stock_status(product)
        
        results.append({
            'id': product.id,
            'sku': product.sku,
            'name': product.name,
            'category': product.category.name if product.category else '-',
            'compatible_models': product.compatible_models or '-',
            'quantity': stock_status['quantity'],
            'selling_price': float(product.selling_price),
            'stock_status': stock_status,
            'unit': product.unit,  # ✅ เพิ่มหน่วยนับ (เช่น ชิ้น, อัน)
            'selling_price': float(product.selling_price or 0),
            'wholesale_price': float(product.wholesale_price or 0),
        })
    
    return JsonResponse({
        'success': True,
        'count': len(results),
        'products': results
    })


@require_http_methods(["GET"])
def popular_models_api(request):
    """API รุ่นรถยอดนิยม"""
    
    # ✅ เรียกใช้ Service
    models = ProductService.get_popular_models(limit=20)
    
    return JsonResponse({
        'success': True,
        'models': models
    })
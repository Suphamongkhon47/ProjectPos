import calendar
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Q, DecimalField, ExpressionWrapper
from django.utils import timezone
from datetime import datetime, time
from products.models import TransactionItem, Category, Product

@login_required
def product_sales_report(request):
    """
    รายงานยอดขายแยกตามสินค้า (Update: เพิ่มการดึงข้อมูลราคา ทุน/ขาย/ส่ง)
    """
    if not request.user.is_superuser:
        return render(request, 'products/permission_denied.html', {
            'perm_key': 'Superuser Only (เฉพาะเจ้าของร้าน)',
        }, status=403)
    # 1. รับค่า Filter
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    category_id = request.GET.get('category', '')
    search = request.GET.get('search', '').strip()
    
    if not date_from or not date_to:
        today = timezone.now()
        year = today.year
        month = today.month
        
        # หาวันสุดท้ายของเดือนนั้นๆ
        last_day = calendar.monthrange(year, month)[1]
        
        # สร้าง String วันที่ในรูปแบบ YYYY-MM-DD เพื่อส่งให้ HTML Input
        date_from = f"{year}-{month:02d}-01"
        date_to = f"{year}-{month:02d}-{last_day}"
    # 1. แปลง String เป็น Timezone Aware Datetime
    start_date_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
    end_date_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
    start_aware = timezone.make_aware(datetime.combine(start_date_obj, time.min))
    end_aware = timezone.make_aware(datetime.combine(end_date_obj, time.max))
    
    # 2. Query Items
    # ✅ แก้ไข: ใช้ __date__gte + __date__lte แทน __range
    items = TransactionItem.objects.filter(
        transaction__doc_type='SALE',
        transaction__status='POSTED',
        transaction__transaction_date__range=(start_aware, end_aware),
        product__isnull=False
    )

    if category_id: items = items.filter(product__category_id=category_id)
    if search:
        items = items.filter(Q(product__name__icontains=search) | Q(product__sku__icontains=search))

    # 3. Group By Product
    report_data = items.values(
        'product__id', 
        'product__sku', 
        'product__name', 
        'product__unit',
        'product__category__name',
        'product__quantity',
        'product__is_bundle',
        # ✅ เพิ่ม: ดึงข้อมูลราคามาแสดง
        'product__cost_price',      # ราคาทุน
        'product__selling_price',   # ราคาขาย
        'product__wholesale_price'  # ราคาส่ง
    ).annotate(
        total_qty=Sum('quantity'),
        total_sales=Sum('line_total'),
        total_cost=Sum(
            ExpressionWrapper(
                F('quantity') * F('cost_price'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )
    ).order_by('-total_qty')

    # 4. Loop คำนวณและสรุป
    total_sales_sum = 0
    total_profit_sum = 0
    total_qty_sum = 0
    
    final_data = []
    
    # Pre-fetch Products
    product_ids = [item['product__id'] for item in report_data if item['product__is_bundle']]
    bundle_map = {}
    if product_ids:
        bundles = Product.objects.filter(id__in=product_ids)
        for b in bundles:
            bundle_map[b.id] = b

    for item in report_data:
        sales = item['total_sales'] or 0
        cost = item['total_cost'] or 0
        qty = item['total_qty'] or 0
        profit = sales - cost
        
        # --- Logic คำนวณสต็อก Bundle ---
        real_stock = item['product__quantity']
        
        if item['product__is_bundle']:
            product_obj = bundle_map.get(item['product__id'])
            if product_obj:
                components = None
                if hasattr(product_obj, 'bundle_components'):
                    components = product_obj.bundle_components.all()
                elif hasattr(product_obj, 'bundlecomponent_set'):
                    components = product_obj.bundlecomponent_set.all()
                
                if components and components.exists():
                    max_buildable = []
                    for comp in components:
                        child_stock = 0
                        qty_needed = 1
                        
                        if hasattr(comp, 'product'): 
                            child_stock = comp.product.quantity
                            if hasattr(comp, 'quantity'): qty_needed = comp.quantity
                        elif hasattr(comp, 'component'):
                            child_stock = comp.component.quantity
                            if hasattr(comp, 'quantity'): qty_needed = comp.quantity
                        else:
                            child_stock = comp.quantity
                            qty_needed = 1
                        
                        if qty_needed > 0:
                            max_buildable.append(int(child_stock // qty_needed))
                        else:
                            max_buildable.append(0)
                    
                    real_stock = min(max_buildable) if max_buildable else 0
        
        item['real_stock'] = real_stock
        item['profit'] = profit
        final_data.append(item)
        
        total_sales_sum += sales
        total_profit_sum += profit
        total_qty_sum += qty

    best_seller = final_data[0]['product__name'] if final_data else "-"
    categories = Category.objects.order_by('name')
    
    context = {
        'report_data': final_data,
        'summary': {
            'total_sales': total_sales_sum,
            'total_profit': total_profit_sum,
            'total_qty': total_qty_sum,
            'best_seller': best_seller
        },
        'categories': categories,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,
        'category_id': category_id,
    }

    return render(request, 'products/reports/product_sales_report.html', context)
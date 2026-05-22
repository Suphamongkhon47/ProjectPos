import calendar
from django.db.models import Sum, F, DecimalField, Avg, Count, Case, When, Q, ExpressionWrapper
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from datetime import datetime, time
from django.utils import timezone
from products.models import Transaction, TransactionItem
from django.core.paginator import Paginator

@login_required
def sales_type_report(request):
    """
    รายงานขายปลีก-ส่ง (แก้ไข Error: ใช้ DecimalField และ ExpressionWrapper)
    """
    
    # รับค่าจาก URL Parameters
    sale_type = request.GET.get('sale_type', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    status = request.GET.get('status', '')
    payment_method = request.GET.get('payment_method', '')
    search = request.GET.get('search', '')
    user_id = request.GET.get('user_id', '')
    
    # ===================================
    # 1. หา Sale IDs แยกตามประเภท
    # ===================================
    
    # 1.1 Sale IDs ที่เป็นขายปลีก
    retail_items = TransactionItem.objects.filter(product__isnull=False).annotate(
        diff_to_retail=Case(
            When(unit_price__gte=F('product__selling_price'), then=F('unit_price') - F('product__selling_price')),
            default=F('product__selling_price') - F('unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        ),
        diff_to_wholesale=Case(
            When(unit_price__gte=F('product__wholesale_price'), then=F('unit_price') - F('product__wholesale_price')),
            default=F('product__wholesale_price') - F('unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).filter(diff_to_retail__lte=F('diff_to_wholesale'))
    
    retail_sale_ids = retail_items.values_list('transaction_id', flat=True).distinct()
    
    # 1.2 Sale IDs ที่เป็นขายส่ง
    wholesale_items = TransactionItem.objects.filter(product__isnull=False).annotate(
        diff_to_retail=Case(
            When(unit_price__gte=F('product__selling_price'), then=F('unit_price') - F('product__selling_price')),
            default=F('product__selling_price') - F('unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        ),
        diff_to_wholesale=Case(
            When(unit_price__gte=F('product__wholesale_price'), then=F('unit_price') - F('product__wholesale_price')),
            default=F('product__wholesale_price') - F('unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).filter(diff_to_wholesale__lt=F('diff_to_retail'))
    
    wholesale_sale_ids = wholesale_items.values_list('transaction_id', flat=True).distinct()
    
    # ===================================
    # 2. Query เริ่มต้น
    # ===================================
    sales = Transaction.objects.filter(doc_type='SALE')
    
    items_query = TransactionItem.objects.filter(product__isnull=False) # Default
    
    if sale_type == 'retail':
        sales = sales.filter(id__in=retail_sale_ids)
        items_query = retail_items
    elif sale_type == 'wholesale':
        sales = sales.filter(id__in=wholesale_sale_ids)
        items_query = wholesale_items
    
    sales = sales.select_related('created_by').order_by('-transaction_date')
    
    # ===================================
    # 3. กรองตามสิทธิ์ & User
    # ===================================
    if request.user.is_superuser:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.all()
        if user_id:
            sales = sales.filter(created_by_id=user_id)
    else:
        sales = sales.filter(created_by=request.user)
        users = []
    
    # ===================================
    # 4. กรองตามวันที่
    # ===================================
    today = timezone.localdate()
    
    if not date_from or not date_to:
        today = timezone.now()
        year = today.year
        month = today.month
        
        # หาวันสุดท้ายของเดือนนั้นๆ
        last_day = calendar.monthrange(year, month)[1]
        
        # สร้าง String วันที่ในรูปแบบ YYYY-MM-DD เพื่อส่งให้ HTML Input
        date_from = f"{year}-{month:02d}-01"
        date_to = f"{year}-{month:02d}-{last_day}"
    start_date_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
    end_date_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
    start_aware = timezone.make_aware(datetime.combine(start_date_obj, time.min))
    end_aware = timezone.make_aware(datetime.combine(end_date_obj, time.max))
    
    # ✅ แก้ไข: ใช้ __date__gte + __date__lte แทน __range
    sales = sales.filter(
        transaction_date__range=(start_aware, end_aware)
    )
    
    # ===================================
    # 5. กรองตามเงื่อนไขอื่นๆ
    # ===================================
    if status: sales = sales.filter(status=status)
    if payment_method: sales = sales.filter(payment__method=payment_method)
    if search:
        sales = sales.filter(Q(doc_no__icontains=search) | Q(remark__icontains=search))
    
    # ===================================
    # 6. สรุปสถิติ (เฉพาะ POSTED)
    # ===================================
    posted_sales = sales.filter(status='POSTED')
    
    summary = posted_sales.aggregate(
        total_sales=Sum('grand_total'),
        total_discount=Sum('discount_amount'),
        avg_sale=Avg('grand_total'),
        count=Count('id')
    )
    
    # ดึงรายการสินค้าทั้งหมดที่อยู่ในบิลที่ Posted (เพื่อคำนวณต้นทุน)
    items_in_posted = items_query.filter(transaction__in=posted_sales)
    
    # ✅ FIX: ใช้ ExpressionWrapper + DecimalField เพื่อความแม่นยำและแก้ Error
    cost_summary = items_in_posted.aggregate(
        total_cost=Sum(
            ExpressionWrapper(
                F('quantity') * F('cost_price'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        ),
        total_qty=Sum('quantity'),
        total_items=Count('id')
    )
    
    total_sales_val = summary['total_sales'] or 0
    total_cost_val = cost_summary['total_cost'] or 0
    
    # คำนวณกำไร
    total_profit = total_sales_val - total_cost_val
    
    summary['total_quantity'] = cost_summary['total_qty'] or 0
    summary['total_items'] = cost_summary['total_items'] or 0
    summary['total_profit'] = total_profit
    
    # ===================================
    # 7. สถิติตามวิธีชำระเงิน
    # ===================================
    payment_summary = posted_sales.values('payment__method').annotate(
        total=Sum('grand_total'),
        count=Count('id')
    ).order_by('-total')
    
    # ===================================
    # 8. Top 10 สินค้าขายดี
    # ===================================
    top_products = items_in_posted.values(
        'product__id', 'product__sku', 'product__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_amount=Sum('line_total'),
        count=Count('id')
    ).order_by('-total_qty')[:10]
    
    # ===================================
    # 9. สถิติแยกตามประเภท (Helper Function)
    # ===================================
    def calculate_subset_stats(subset_ids):
        """Helper Function คำนวณยอดขาย + กำไร ของกลุ่มย่อย"""
        # ✅ แก้ไข: ใช้ __date__gte + __date__lte แทน __range
        subset_sales = Transaction.objects.filter(
            doc_type='SALE',
            status='POSTED',
            id__in=subset_ids,
            transaction_date__date__gte=date_from,
            transaction_date__date__lte=date_to
        )
        
        if request.user.is_superuser and user_id:
            subset_sales = subset_sales.filter(created_by_id=user_id)
        elif not request.user.is_superuser:
            subset_sales = subset_sales.filter(created_by=request.user)
            
        stats = subset_sales.aggregate(
            total=Sum('grand_total'),
            count=Count('id')
        )
        
        # คำนวณต้นทุนกลุ่มย่อย
        subset_items = TransactionItem.objects.filter(transaction__in=subset_sales)
        
        # ✅ FIX: ใช้ ExpressionWrapper แบบเดียวกัน
        subset_cost_data = subset_items.aggregate(
            cost=Sum(
                ExpressionWrapper(
                    F('quantity') * F('cost_price'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )
        subset_cost = subset_cost_data['cost'] or 0
        
        total_val = stats['total'] or 0
        stats['profit'] = total_val - subset_cost
        return stats

    retail_stats = calculate_subset_stats(retail_sale_ids)
    wholesale_stats = calculate_subset_stats(wholesale_sale_ids)
    
    # ===================================
    # 10. Pagination
    # ===================================
    paginator = Paginator(sales, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # ===================================
    # 11. Context
    # ===================================
    context = {
        'sales': page_obj,
        'summary': summary,
        'payment_summary': payment_summary,
        'top_products': top_products,
        'retail_stats': retail_stats,
        'wholesale_stats': wholesale_stats,
        'date_from': date_from,
        'date_to': date_to,
        'status': status,
        'payment_method': payment_method,
        'search': search,
        'users': users,
        'selected_user_id': user_id,
        'is_owner': request.user.is_superuser,
        'sale_type': sale_type,
    }
    
    return render(request, 'products/reports/sales_type_report.html', context)
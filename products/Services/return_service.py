"""
Return Service: Business Logic สำหรับการรับคืนสินค้า

แยก Logic ออกจาก Views และ Models เพื่อ:
- ง่ายต่อการทดสอบ (Testing)
- ง่ายต่อการนำกลับมาใช้ (Reusable)
- ง่ายต่อการบำรุงรักษา (Maintainable)
"""

from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q
from decimal import Decimal
from datetime import datetime, timedelta

# ✅ แก้ Circular Import: import เฉพาะที่จำเป็น
from products.models import Transaction, TransactionItem, Product , StockMovement


# ===================================
# 1. Validate: เช็คความพร้อมในการคืน
# ===================================
def validate_return_eligibility(sale, max_days=7):
    """
    ตรวจสอบว่าบิลนี้สามารถรับคืนได้หรือไม่
    
    Rules:
    1. ต้องเป็นบิลขาย (doc_type='SALE')
    2. สถานะต้องเป็น POSTED
    3. ไม่เกิน X วัน (default 7 วัน)
    4. ไม่ถูกยกเลิกแล้ว
    
    Args:
        sale: Sale object
        max_days: จำนวนวันสูงสุด (default 7)
    
    Raises:
        ValueError: ถ้าไม่ผ่านเงื่อนไข
    
    Returns:
        True: ถ้าผ่านทุกเงื่อนไข
    """
    
    # Rule 1: ต้องเป็นบิลขาย
    if sale.doc_type != 'SALE':
        raise ValueError(
            f"ไม่สามารถรับคืนได้\n"
            f"เลขที่ {sale.doc_no} ไม่ใช่บิลขาย"
        )
    
    # Rule 2: สถานะต้องเป็น POSTED
    if sale.status != 'POSTED':
        status_display = {
            'DRAFT': 'ร่าง',
            'CANCELLED': 'ยกเลิก'
        }.get(sale.status, sale.status)
        
        raise ValueError(
            f"ไม่สามารถรับคืนได้\n"
            f"บิลนี้อยู่ในสถานะ: {status_display}\n"
            f"รับคืนได้เฉพาะบิลที่ยืนยันแล้วเท่านั้น"
        )
    
    # Rule 3: ไม่เกินจำนวนวันที่กำหนด
    days_passed = (timezone.now() - sale.transaction_date).days
    
    if days_passed > max_days:
        raise ValueError(
            f"ไม่สามารถรับคืนได้\n"
            f"บิลนี้ขายเมื่อ: {sale.transaction_date.strftime('%d/%m/%Y')}\n"
            f"ผ่านมาแล้ว: {days_passed} วัน\n"
            f"รับคืนได้ภายใน: {max_days} วัน"
        )
    
    # Rule 4: เช็คว่ามีรายการที่ยังคืนไม่หมดหรือไม่
    original_items = sale.items.all()
    
    if not original_items.exists():
        raise ValueError(
            f"ไม่สามารถรับคืนได้\n"
            f"บิลนี้ไม่มีรายการสินค้า"
        )
    
    # เช็คว่าคืนหมดแล้วหรือยัง
    returned_items = get_returned_items_summary(sale.doc_no)
    
    all_returned = True
    for item in original_items:
        returned_qty = returned_items.get(item.product_id, 0)
        if returned_qty < item.quantity:
            all_returned = False
            break
    
    if all_returned:
        raise ValueError(
            f"ไม่สามารถรับคืนได้\n"
            f"สินค้าในบิลนี้ถูกคืนหมดแล้ว"
        )
    
    return True


# ===================================
# 2. Helper: คำนวณจำนวนที่คืนไปแล้ว
# ===================================
def get_returned_items_summary(ref_doc_no):
    """
    คำนวณว่าบิลนี้มีสินค้าอะไรถูกคืนไปแล้วบ้าง
    
    Args:
        ref_doc_no: เลขที่บิลเดิม (เช่น SALE-001)
    
    Returns:
        dict: {product_id: total_returned_quantity}
    """
    
    returns = Transaction.objects.filter(
        doc_type='RETURN',
        ref_doc_no=ref_doc_no,
        status='POSTED'
    )
    
    returned_summary = {}
    
    for ret in returns:
        for item in ret.items.select_related('product'):
            product_id = item.product_id
            returned_summary[product_id] = returned_summary.get(product_id, 0) + item.quantity
    
    return returned_summary


# ===================================
# 3. สร้างบิลรับคืน (Transaction)
# ===================================
def create_return_transaction(
    user,
    ref_doc_no,
    items_data,
    return_reason='other',
    return_note='',
    discount_amount=0,
    doc_no=None
):
    """
    สร้างบิลรับคืนพร้อมรายการสินค้า
    
    Args:
        user: User object
        ref_doc_no: เลขที่บิลเดิม (SALE-xxx)
        items_data: [{'product_id': 1, 'quantity': 2}, ...]
        return_reason: เหตุผล (damaged/change_mind/wrong_item/size_wrong/other)
        return_note: หมายเหตุ
        discount_amount: ส่วนลดที่คืน
        doc_no: เลขที่บิลรับคืน (RET-xxx)
    
    Returns:
        Sale object (doc_type='RETURN')
    """
    
    if not items_data:
        raise ValueError("ไม่มีรายการสินค้าที่จะคืน")
    
    try:
        with transaction.atomic():
            
            # ✅ ค้นหาบิลเดิม
            try:
                original_sale = Transaction.objects.get(
                    doc_no=ref_doc_no,
                    doc_type='SALE',
                    status='POSTED'
                )
            except Transaction.DoesNotExist:
                raise ValueError(f"ไม่พบบิลเลขที่: {ref_doc_no}")
            
            # ✅ Validate: เช็คความพร้อม
            validate_return_eligibility(original_sale)
            
            # ✅ ดึงข้อมูลที่คืนไปแล้ว
            already_returned = get_returned_items_summary(ref_doc_no)
            
            # ✅ สร้างบิลรับคืน
            return_sale = Transaction.objects.create(
                doc_no=doc_no,
                doc_type='RETURN',
                ref_doc_no=ref_doc_no,
                status='DRAFT',
                discount_amount=Decimal(str(discount_amount)),
                remark=f"เหตุผล: {return_reason}\n{return_note}",
                created_by=user,
            )
            
            # ✅ เพิ่มรายการสินค้าที่คืน
            total_amount = Decimal('0')
            
            for item_data in items_data:
                
                # ดึงสินค้า
                try:
                    product = Product.objects.select_related('category').get(
                        id=item_data['product_id'],
                        is_active=True
                    )
                except Product.DoesNotExist:
                    raise ValueError(f"ไม่พบสินค้า ID {item_data['product_id']}")
                
                # จำนวนที่จะคืน
                return_qty = Decimal(str(item_data['quantity']))
                
                if return_qty <= 0:
                    raise ValueError(f"จำนวนคืนของ {product.name} ต้องมากกว่า 0")
                
                # ✅ ค้นหารายการในบิลเดิม
                try:
                    original_item = original_sale.items.get(product=product)
                except TransactionItem.DoesNotExist:
                    raise ValueError(
                        f"ไม่พบสินค้า {product.name} ในบิลเดิม"
                    )
                
                # ✅ เช็คว่าคืนได้หรือไม่
                already_returned_qty = already_returned.get(product.id, 0)
                remaining_qty = original_item.quantity - already_returned_qty
                
                if return_qty > remaining_qty:
                    raise ValueError(
                        f"ไม่สามารถคืน {product.name} ได้\n"
                        f"ซื้อไป: {original_item.quantity} {product.unit}\n"
                        f"คืนไปแล้ว: {already_returned_qty} {product.unit}\n"
                        f"เหลือให้คืน: {remaining_qty} {product.unit}\n"
                        f"ต้องการคืน: {return_qty} {product.unit} (เกิน!)"
                    )
                
                # ✅ สร้างรายการคืน (ใช้ราคาและต้นทุนจากบิลเดิม)
                line_total = return_qty * original_item.unit_price
                
                TransactionItem.objects.create(
                    transaction=return_sale,
                    product=product,
                    quantity=return_qty,
                    unit_price=original_item.unit_price,
                    cost_price=original_item.cost_price,
                    line_total=line_total,
                    unit_type=original_item.unit_type or 'ชิ้น',      
                    display_sku=original_item.display_sku or product.sku,  
                    bundle_items=original_item.bundle_items
                )
                
                total_amount += line_total
            
            # ✅ คำนวณยอดรวม (เป็นลบเพราะคืนเงิน)
            return_sale.total_amount = -abs(total_amount)
            return_sale.grand_total = -abs(total_amount - Decimal(str(discount_amount)))
            return_sale.save(update_fields=['total_amount', 'grand_total'])
            
            return return_sale
            
    except Exception as e:
        raise ValueError(f"ไม่สามารถสร้างบิลรับคืนได้: {str(e)}")


# ===================================
# 4. ยืนยันบิลรับคืน (คืนสต็อก)
# ===================================
def post_return(return_sale):
    """
    ยืนยันบิลรับคืน → คืนสต็อกเข้าคลัง
    
    Args:
        return_sale: Sale object (doc_type='RETURN')
    
    Returns:
        True
    """
    
    # ✅ แก้ Circular Import: import ภายในฟังก์ชัน
    
    if return_sale.doc_type != 'RETURN':
        raise ValueError("ไม่ใช่บิลรับคืน")
    
    if return_sale.status == 'POSTED':
        return True
    
    if return_sale.status == 'CANCELLED':
        raise ValueError("ไม่สามารถยืนยันบิลที่ยกเลิกแล้ว")
    
    try:
        with transaction.atomic():
            
            # ✅ คืนสต็อก
            for item in return_sale.items.select_related('product').all():
                
                # ⭐ ถ้ามี bundle_items → คืนทุก SKU
                if item.bundle_items:
                    for product_id in item.bundle_items:
                        product = Product.objects.select_for_update().get(id=product_id)
                        product.quantity += int(item.quantity)
                        product.save(update_fields=['quantity'])
                        
                        StockMovement.objects.create(
                            product=product,
                            movement_type='IN',
                            quantity=item.quantity,
                            unit_cost=item.cost_price,
                            balance_after=product.quantity,
                            reference=return_sale.doc_no,
                            note=f"รับคืน{item.unit_type} {return_sale.ref_doc_no}"
                        )
                else:
                    # คืนปกติ
                    product = Product.objects.select_for_update().get(id=item.product.id)
                    product.quantity += int(item.quantity)
                    product.save(update_fields=['quantity'])
                    
                    StockMovement.objects.create(
                        product=item.product,
                        movement_type='IN',
                        quantity=item.quantity,
                        unit_cost=item.cost_price,
                        balance_after=product.quantity,
                        reference=return_sale.doc_no,
                        note=f"รับคืนจากบิล: {return_sale.ref_doc_no}"
                    )
            
            # เปลี่ยนสถานะ
            return_sale.status = 'POSTED'
            return_sale.transaction_date = timezone.now()
            return_sale.save(update_fields=['status', 'transaction_date'])
            
            return True
            
    except Exception as e:
        raise ValueError(f"ไม่สามารถยืนยันบิลรับคืนได้: {str(e)}")


# ===================================
# 5. ยกเลิกบิลรับคืน (ไม่แนะนำ!)
# ===================================
def cancel_return(return_sale):
    """
    ยกเลิกบิลรับคืน → ตัดสต็อกออกอีกครั้ง
    
    ⚠️ คำเตือน:
    - การยกเลิกบิลรับคืนจะทำให้สต็อกถูกตัดออกอีกครั้ง
    - เงินที่คืนต้องเรียกคืนจากลูกค้า
    - อาจสร้างความสับสน
    - แนะนำให้สร้างบิลขายใหม่แทนการยกเลิก
    
    Args:
        return_sale: Sale object (doc_type='RETURN')
    
    Returns:
        True
    """
    
    if return_sale.doc_type != 'RETURN':
        raise ValueError("ไม่ใช่บิลรับคืน")
    
    if return_sale.status == 'CANCELLED':
        return True
    
    if return_sale.status != 'POSTED':
        raise ValueError("สามารถยกเลิกได้เฉพาะบิลที่ยืนยันแล้ว")
    
    try:
        with transaction.atomic():
            
            # ⚠️ ตัดสต็อกออกอีกครั้ง (เพราะเคยคืนเข้าไปแล้ว)
            for item in return_sale.items.select_related('product').all():
                
                # ⭐ ถ้ามี bundle_items → ตัดทุก SKU
                if item.bundle_items:
                    for product_id in item.bundle_items:
                        product = Product.objects.select_for_update().get(id=product_id)
                        
                        if product.quantity < item.quantity:
                            raise ValueError(f"สต็อก {product.name} ไม่พอ")
                        
                        product.quantity -= int(item.quantity)
                        product.save(update_fields=['quantity'])
                        
                        StockMovement.objects.create(
                            product=product,
                            movement_type='OUT',
                            quantity=item.quantity,
                            unit_cost=item.cost_price,
                            balance_after=product.quantity,
                            reference=f'CANCEL-{return_sale.doc_no}',
                            note=f"ยกเลิกการรับคืน{item.unit_type}"
                        )
                else:
                    # ตัดปกติ
                    product = Product.objects.select_for_update().get(id=item.product.id)
                    
                    if product.quantity < item.quantity:
                        raise ValueError(f"สต็อก {product.name} ไม่พอ")
                    
                    product.quantity -= int(item.quantity)
                    product.save(update_fields=['quantity'])
                    
                    StockMovement.objects.create(
                        product=item.product,
                        movement_type='OUT',
                        quantity=item.quantity,
                        unit_cost=item.cost_price,
                        balance_after=product.quantity,
                        reference=f'CANCEL-{return_sale.doc_no}',
                        note=f"ยกเลิกการรับคืน"
                    )
            
            # เปลี่ยนสถานะ
            return_sale.status = 'CANCELLED'
            return_sale.save(update_fields=['status'])
            
            # ยกเลิก Payment
            if hasattr(return_sale, 'payment'):
                return_sale.payment.status = 'void'
                return_sale.payment.save(update_fields=['status'])
            
            return True
            
    except Exception as e:
        raise ValueError(f"ไม่สามารถยกเลิกบิลรับคืนได้: {str(e)}")


# ===================================
# 6. ฟังก์ชันเสริม
# ===================================
def get_return_summary(return_sale):
    """
    สรุปข้อมูลบิลรับคืน
    
    Args:
        return_sale: Sale object (doc_type='RETURN')
    
    Returns:
        dict: สรุปข้อมูล
    """
    
    if return_sale.doc_type != 'RETURN':
        raise ValueError("ไม่ใช่บิลรับคืน")
    
    items = return_sale.items.select_related('product').all()
    
    total_items = items.count()
    total_quantity = sum(item.quantity for item in items)
    
    return {
        'doc_no': return_sale.doc_no,
        'ref_doc_no': return_sale.ref_doc_no,
        'sale_date': return_sale.transaction_date,
        'status': return_sale.get_status_display(),
        'total_items': total_items,
        'total_quantity': float(total_quantity),
        'total_amount': float(abs(return_sale.total_amount)),
        'discount_amount': float(return_sale.discount_amount),
        'grand_total': float(abs(return_sale.grand_total)),
        'refund_amount': float(abs(return_sale.grand_total)),
    }


def validate_return_items(ref_doc_no, items_data):
    """
    ตรวจสอบรายการสินค้าที่จะคืนก่อนสร้างบิล
    
    Args:
        ref_doc_no: เลขที่บิลเดิม
        items_data: list of dict
    
    Returns:
        tuple: (is_valid, errors)
    """
    
    errors = []
    
    if not items_data:
        errors.append("ไม่มีรายการสินค้าที่จะคืน")
        return False, errors
    
    # ค้นหาบิลเดิม
    try:
        original_sale = Transaction.objects.get(
            doc_no=ref_doc_no,
            doc_type='SALE',
            status='POSTED'
        )
    except Transaction.DoesNotExist:
        errors.append(f"ไม่พบบิล: {ref_doc_no}")
        return False, errors
    
    # เช็คความพร้อม
    try:
        validate_return_eligibility(original_sale)
    except ValueError as e:
        errors.append(str(e))
        return False, errors
    
    # ดึงข้อมูลที่คืนไปแล้ว
    already_returned = get_returned_items_summary(ref_doc_no)
    
    # เช็คแต่ละรายการ
    for i, item in enumerate(items_data):
        
        # ตรวจสอบ product_id
        if 'product_id' not in item:
            errors.append(f"รายการที่ {i+1}: ไม่มี product_id")
            continue
        
        # ตรวจสอบว่ามีสินค้าหรือไม่
        try:
            product = Product.objects.get(id=item['product_id'], is_active=True)
        except Product.DoesNotExist:
            errors.append(f"รายการที่ {i+1}: ไม่พบสินค้า ID {item['product_id']}")
            continue
        
        # ตรวจสอบจำนวน
        if 'quantity' not in item or float(item['quantity']) <= 0:
            errors.append(f"รายการที่ {i+1} ({product.name}): จำนวนไม่ถูกต้อง")
            continue
        
        # ตรวจสอบว่ามีในบิลเดิมหรือไม่
        try:
            original_item = original_sale.items.get(product=product)
        except TransactionItem.DoesNotExist:
            errors.append(f"รายการที่ {i+1} ({product.name}): ไม่มีในบิลเดิม")
            continue
        
        # ตรวจสอบจำนวนที่คืนได้
        return_qty = Decimal(str(item['quantity']))
        already_returned_qty = already_returned.get(product.id, 0)
        remaining_qty = original_item.quantity - already_returned_qty
        
        if return_qty > remaining_qty:
            errors.append(
                f"รายการที่ {i+1} ({product.name}): "
                f"คืนได้สูงสุด {remaining_qty} {product.unit} "
                f"(คืนไปแล้ว {already_returned_qty})"
            )
    
    return len(errors) == 0, errors


def get_returnable_items(ref_doc_no):
    """
    ดึงรายการสินค้าที่สามารถคืนได้จากบิล
    
    Args:
        ref_doc_no: เลขที่บิลเดิม
    
    Returns:
        list: รายการสินค้าที่คืนได้
    """
    
    try:
        original_sale = Transaction.objects.get(
            doc_no=ref_doc_no,
            doc_type='SALE',
            status='POSTED'
        )
    except Transaction.DoesNotExist:
        return []
    
    # เช็คความพร้อม
    try:
        validate_return_eligibility(original_sale)
    except ValueError:
        return []
    
    # ดึงข้อมูลที่คืนไปแล้ว
    already_returned = get_returned_items_summary(ref_doc_no)
    
    # สร้างรายการที่คืนได้
    returnable = []
    
    for item in original_sale.items.select_related('product'):
        already_returned_qty = already_returned.get(item.product_id, 0)
        remaining_qty = item.quantity - already_returned_qty
        
        if remaining_qty > 0:
            returnable.append({
                'product_id': item.product.id,
                'sku': item.product.sku,
                'name': item.product.name,
                'unit': item.product.unit,
                'original_quantity': float(item.quantity),
                'already_returned': float(already_returned_qty),
                'remaining_quantity': float(remaining_qty),
                'unit_price': float(item.unit_price),
                'cost_price': float(item.cost_price),
            })
    
    return returnable


def calculate_refund_amount(ref_doc_no, items_data, discount_return=0):
    """
    คำนวณยอดเงินที่จะคืน
    
    Args:
        ref_doc_no: เลขที่บิลเดิม
        items_data: [{'product_id': 1, 'quantity': 2}, ...]
        discount_return: ส่วนลดที่คืน
    
    Returns:
        Decimal: ยอดเงินที่คืน
    """
    
    try:
        original_sale = Transaction.objects.get(
            doc_no=ref_doc_no,
            doc_type='SALE',
            status='POSTED'
        )
    except Transaction.DoesNotExist:
        return Decimal('0')
    
    total = Decimal('0')
    
    for item_data in items_data:
        try:
            original_item = original_sale.items.get(product_id=item_data['product_id'])
            quantity = Decimal(str(item_data['quantity']))
            total += original_item.unit_price * quantity
        except TransactionItem.DoesNotExist:
            continue
    
    refund_amount = total - Decimal(str(discount_return))
    
    return abs(refund_amount)
from django.utils import timezone
from django.db import transaction as db_transaction # ✅ ตั้งชื่อ alias กันชื่อซ้ำกับ Model Transaction
from decimal import Decimal
from products.models import (
    Transaction, TransactionItem, Product, StockMovement
)
from products.Services.payment_service import PaymentService

# ===================================
# 1. สร้างบิลขาย (Transaction)
# ===================================
def create_sale_transaction(user, items_data, price_type='retail', discount_amount=0, remark='', doc_no=None, doc_type='SALE', ref_doc_no='', status='HOLD', sale_id=None):
    if not items_data:
        raise ValueError("ไม่มีรายการสินค้า")
    
    try:
        with db_transaction.atomic():
            # 1.1 สร้าง/แก้ไข Header
            if sale_id:
                try:
                    sale = Transaction.objects.get(id=sale_id)
                    sale.items.all().delete()
                    sale.doc_type = doc_type
                    sale.ref_doc_no = ref_doc_no
                    sale.status = status
                    sale.discount_amount = Decimal(str(discount_amount))
                    sale.remark = remark
                    sale.updated_at = timezone.now()
                    sale.save()
                except Transaction.DoesNotExist:
                    raise ValueError("ไม่พบข้อมูลบิลที่ต้องการแก้ไข")
            else:
                sale = Transaction.objects.create(
                    doc_no=doc_no,
                    doc_type=doc_type,
                    ref_doc_no=ref_doc_no,
                    status=status,
                    discount_amount=Decimal(str(discount_amount)),
                    remark=remark,
                    created_by=user,
                )
            
            # 1.2 เพิ่มรายการสินค้า
            total_amount = Decimal('0')
            
            for item_data in items_data:
                try:
                    product = Product.objects.select_related('category').get(id=item_data['product_id'], is_active=True)
                except Product.DoesNotExist:
                    raise ValueError(f"ไม่พบสินค้า ID {item_data['product_id']}")
                
                unit_type = item_data.get('unit_type', 'ชิ้น')
                display_sku = product.sku
                bundle_items = item_data.get('bundle_items', [])
                
                # ถ้าหน้าจอไม่ได้ส่งมา ให้ลองเช็คจาก Database (สินค้าชุดปกติ)
                if not bundle_items and product.is_bundle:
                    bundle_items = list(product.bundle_components.values_list('id', flat=True))
                
                # ✅ LOGIC ใหม่: ใช้ bundle_components แทน bundle_group
                if product.is_bundle:
                    # ดึง ID ลูกๆ มาเก็บไว้ตัดสต็อก (Snapshot)
                    bundle_items = list(product.bundle_components.values_list('id', flat=True))

                # แปลงจำนวน
                quantity = Decimal(str(item_data['quantity']))
                if quantity <= 0: raise ValueError(f"จำนวนสินค้า {product.name} ไม่ถูกต้อง")
                
                # กำหนดราคา
                if 'custom_price' in item_data and item_data['custom_price'] is not None:
                    unit_price = Decimal(str(item_data['custom_price']))
                else:
                    unit_price = product.wholesale_price if price_type == 'wholesale' else product.selling_price
                
                # ✅ เช็คสต็อก (เฉพาะสินค้าปกติ)
                if doc_type == 'SALE' and not product.is_bundle:
                    current_stock = Decimal(str(product.quantity or 0))
                    if current_stock < quantity:
                        raise ValueError(f"สินค้า {product.name} มีสต็อกไม่พอ (เหลือ {current_stock:g} {product.unit})")
                elif doc_type == 'SALE' and product.is_bundle:
                    # ถ้าหน้าจอส่ง list ลูกมาใช้จากหน้าจอ ถ้าไม่มีดึงจาก DB
                    check_items = bundle_items if bundle_items else product.bundle_components.all()
                    
                    for item_ref in check_items:
                        # กรณีเป็น ID (จากหน้าจอ/values_list)
                        if isinstance(item_ref, int): 
                            comp = Product.objects.get(id=item_ref)
                        else: # กรณีเป็น Object (จาก .all())
                            comp = item_ref
                            
                        # คำนวณ: 1 ชุดใช้ลูก 1 ชิ้น * จำนวนชุดที่ขาย
                        req_qty = quantity 
                        if comp.quantity < req_qty:
                             raise ValueError(f"สินค้าในชุด '{comp.name}' มีสต็อกไม่พอ (เหลือ {comp.quantity:g} ชิ้น)")
                # คำนวณยอด
                line_total = quantity * unit_price
                total_amount += line_total
                
                # สร้างรายการ
                TransactionItem.objects.create(
                    transaction=sale,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    cost_price=product.cost_price,
                    line_total=line_total,
                    unit_type=unit_type,
                    display_sku=display_sku,
                    bundle_items=bundle_items # ✅ บันทึกสูตรไว้ตัดสต็อก
                )
            
            # 1.3 อัปเดตท้ายบิล
            sale.total_amount = total_amount
            sale.grand_total = total_amount - sale.discount_amount
            sale.save(update_fields=['total_amount', 'grand_total'])
            
            return sale
            
    except Exception as e:
        raise e

# ===================================
# 2. ยืนยันบิลขาย (ตัดสต็อก)
# ===================================
def post_sale(sale_obj):
    if sale_obj.status == 'POSTED': return True
    if sale_obj.status == 'CANCELLED': raise ValueError("ไม่สามารถยืนยันบิลที่ยกเลิกแล้ว")
    
    try:
        with db_transaction.atomic():
            for item in sale_obj.items.select_related('product').all():
                
                # ⭐ ตัดสต็อก: ถ้ามี bundle_items ให้ตัดลูก
                if item.bundle_items:
                    for product_id in item.bundle_items:
                        product = Product.objects.select_for_update().get(id=product_id)
                        
                        item_qty = Decimal(str(item.quantity)) # ขาย 1 คู่ ตัดลูก 1 ชิ้น
                        current_stock = Decimal(str(product.quantity or 0))
                        
                        if current_stock < item_qty:
                            raise ValueError(f"สินค้าในชุด {item.product.name} ({product.name}) สต็อกไม่พอ")
                        
                        product.quantity -= int(item_qty)
                        product.save(update_fields=['quantity'])
                        
                        StockMovement.objects.create(
                            product=product,
                            movement_type='OUT',
                            quantity=item.quantity,
                            unit_cost=item.cost_price,
                            balance_after=product.quantity,
                            reference=sale_obj.doc_no,
                            note=f"ขายชุด {item.product.sku}"
                        )
                else:
                    # ตัดสต็อกสินค้าปกติ
                    product = Product.objects.select_for_update().get(id=item.product.id)
                    item_qty = Decimal(str(item.quantity))
                    
                    if product.quantity < item_qty:
                        raise ValueError(f"สินค้า {product.name} สต็อกไม่พอ")
                    
                    product.quantity -= int(item_qty)
                    product.save(update_fields=['quantity'])
                    
                    StockMovement.objects.create(
                        product=item.product,
                        movement_type='OUT',
                        quantity=item.quantity,
                        unit_cost=item.cost_price,
                        balance_after=product.quantity,
                        reference=sale_obj.doc_no,
                        note=f"ขายปลีก"
                    )
            
            sale_obj.status = 'POSTED'
            if hasattr(sale_obj, 'transaction_date'):
                sale_obj.transaction_date = timezone.now()
                sale_obj.save(update_fields=['status', 'transaction_date'])
            else:
                sale_obj.save(update_fields=['status'])
            return True
            
    except Exception as e:
        raise ValueError(f"ยืนยันบิลไม่สำเร็จ: {str(e)}")
# ===================================
# 3. ยกเลิกบิลขาย (คืนสต็อก)
# ===================================
def cancel_sale(sale_obj):
    """
    ยกเลิกบิลขาย -> คืนสต็อก (Revert Sale)
    """
    if sale_obj.status == 'CANCELLED':
        return True
    
    # ถ้ายังไม่ POSTED คือยังไม่ตัดของ ก็แค่เปลี่ยนสถานะ
    if sale_obj.status != 'POSTED':
        sale_obj.status = 'CANCELLED'
        sale_obj.save(update_fields=['status'])
        return True
    
    try:
        with db_transaction.atomic():
            for item in sale_obj.items.all():
                qty = item.quantity
                
                # ✅ LOGIC ใหม่: เช็คว่ารายการนี้มีสูตร Bundle หรือไม่ (จาก Snapshot)
                # รองรับทั้งสินค้าชุดปกติ และ สินค้าจับคู่หน้างาน
                if item.bundle_items:
                    # วนลูปคืนสต็อกให้ลูกๆ ตาม ID ที่บันทึกไว้
                    for child_id in item.bundle_items:
                        try:
                            # ล็อคแถวเพื่อป้องกัน Race Condition
                            child = Product.objects.select_for_update().get(id=child_id)
                            
                            # คืนสต็อก (IN)
                            child.quantity = (child.quantity or 0) + int(qty)
                            child.save(update_fields=['quantity'])
                            
                            # บันทึก Movement
                            StockMovement.objects.create(
                                product=child,
                                movement_type='IN',
                                quantity=qty,
                                unit_cost=child.cost_price,
                                balance_after=child.quantity,
                                reference=f'CANCEL-{sale_obj.doc_no}',
                                note=f"ยกเลิกบิลขาย {sale_obj.doc_no} (คืนชุด {item.display_sku})"
                            )
                        except Product.DoesNotExist:
                            pass # ถ้าสินค้าลูกถูกลบไปแล้ว ให้ข้าม
                            
                # ✅ กรณีสินค้าปกติ -> คืนให้ตัวมันเอง
                else:
                    product = Product.objects.select_for_update().get(id=item.product.id)
                    product.quantity = (product.quantity or 0) + int(qty)
                    product.save(update_fields=['quantity'])
                    
                    StockMovement.objects.create(
                        product=product,
                        movement_type='IN',
                        quantity=qty,
                        unit_cost=item.cost_price,
                        balance_after=product.quantity,
                        reference=f'CANCEL-{sale_obj.doc_no}',
                        note=f"ยกเลิกบิลขาย {sale_obj.doc_no}"
                    )
            
            # เปลี่ยนสถานะบิล
            sale_obj.status = 'CANCELLED'
            sale_obj.save(update_fields=['status'])
            
            # ยกเลิก Payment (ถ้ามี)
            if hasattr(sale_obj, 'payment') and sale_obj.payment:
                sale_obj.payment.status = 'void'
                sale_obj.payment.save(update_fields=['status'])
            
            return True
            
    except Exception as e:
        raise ValueError(f"ไม่สามารถยกเลิกบิลได้: {str(e)}")

# ===================================
# 4. ฟังก์ชันเสริม (Wrapper)
# ===================================
def create_payment(sale_obj, method='cash', received=None, note=''):
    """
    Wrapper function เรียก PaymentService
    """
    return PaymentService.create_payment(
        sale=sale_obj,
        method=method,
        received=received,
        note=note
    )

def validate_sale_items(items_data):
    """
    Validate ข้อมูลสินค้าเบื้องต้น
    """
    errors = []
    if not items_data:
        errors.append("ไม่มีรายการสินค้า")
        return False, errors
    
    for i, item in enumerate(items_data):
        if 'product_id' not in item:
            errors.append(f"รายการที่ {i+1}: ไม่มี product_id")
            continue
            
        try:
            Decimal(str(item.get('quantity', 0)))
        except:
            errors.append(f"รายการที่ {i+1}: จำนวนสินค้าไม่ถูกต้อง")
    
    return len(errors) == 0, errors
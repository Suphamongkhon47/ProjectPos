"""
products/views/helpers.py
Helper Functions สำหรับการนำเข้าสินค้า
รองรับ: แปลงหน่วยซื้อ → หน่วยสต็อก + แยก SKU ตาม bundle_type

ราคา Logic:
- cost_price บน Product → ไม่ overwrite ที่นี่ เพราะ post_purchase จะ Weighted Average ให้เอง
- selling_price / wholesale_price → overwrite ล่าสุด (ราคาขาย คือ ราคา "ตอนนี้")
"""

from decimal import Decimal
from urllib import request
from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import datetime
from django.contrib.auth import get_user_model

# Import Models
from products.models import (
    Product,
    Supplier, Purchase, PurchaseItem,
)

# ✅ Import Service
from products.Services.purchase_service import post_purchase

User = get_user_model()


def _D(v, default=Decimal("0")):
    """แปลงค่าเป็น Decimal อย่างปลอดภัย"""
    try:
        if v is None or v == "":
            return default
        return Decimal(str(v))
    except:
        return default


def _stage(session):
    """ดึงข้อมูลตะกร้าสินค้าจาก Session"""
    return session.setdefault("import_stage", [])


def _remove_row(request, stage, redirect_to):
    """ลบแถวออกจากตารางชั่วคราว"""
    idx = int(request.POST.get("index", "-1"))
    if 0 <= idx < len(stage):
        stage.pop(idx)
        request.session.modified = True
        messages.success(request, "🗑️ ลบรายการเรียบร้อย")
    return redirect(redirect_to)


def _clear_all(request, redirect_to):
    """ล้างตารางทั้งหมด"""
    request.session["import_stage"] = []
    request.session.modified = True
    messages.success(request, "🗑️ ล้างข้อมูลทั้งหมดแล้ว")
    return redirect(redirect_to)


def _generate_purchase_doc_no():
    """สร้างเลขที่เอกสาร PO-YYYYMMDD-XXX"""
    today = datetime.now()
    prefix = f"PO-{today.strftime('%Y%m%d')}"
    
    last_purchase = Purchase.objects.filter(
        doc_no__startswith=prefix
    ).order_by("-doc_no").first()
    
    if last_purchase:
        try:
            last_num = int(last_purchase.doc_no.split("-")[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    
    return f"{prefix}-{new_num:03d}"


def _commit_to_database(request, stage, redirect_to):
    """
    บันทึกข้อมูลลงฐานข้อมูลจริง
    
    ขั้นตอน:
    1. สร้าง Purchase (DRAFT)
    2. สร้าง/อัปเดต Product (รองรับ bundle_type)
       - selling_price / wholesale_price → overwrite ล่าสุด
       - cost_price → ไม่ overwrite ที่นี่ เพราะ post_purchase จะ Weighted Average ให้เอง
    3. สร้าง PurchaseItem (เก็บ unit_cost จากไฟล์/ฟอร์ม)
    4. เรียก post_purchase() → Service จะ คำนวณ Weighted Average + เพิ่มสต็อก
    """
    if not stage:
        messages.error(request, "❌ ไม่มีข้อมูลในรายการ")
        return redirect(redirect_to)
    
    # 1. เตรียม User และ Supplier
    user = request.user if request.user.is_authenticated else User.objects.filter(is_superuser=True).first()
    
    # ดึง Supplier จากรายการแรก
    first_row = stage[0]
    supplier_id = first_row.get('supplier_id')
    supplier = None
    
    if supplier_id:
        supplier = Supplier.objects.filter(id=supplier_id).first()
        
    if not supplier:
        supplier, _ = Supplier.objects.get_or_create(
            name="General Supplier",
            defaults={"address": "-"}
        )

    created_count = 0
    updated_count = 0
    total_amount = Decimal("0")

    try:
        with transaction.atomic():
            # 2. สร้างหัวเอกสาร Purchase (DRAFT)
            doc_no = _generate_purchase_doc_no()
            purchase = Purchase.objects.create(
                doc_no=doc_no,
                supplier=supplier,
                purchase_date=timezone.now(),
                status='DRAFT',
                created_by=user,
                remark=f"Import Ref: {first_row.get('reference', '-')}"
            )

            # 3. วนลูปสินค้า
            for row in stage:
                sku = row.get('sku', '').strip()
                name = row.get('name', '').strip()
                
                # แปลงตัวเลข
                qty = _D(row.get('quantity'))       # จำนวนที่ซื้อ (เป็นหน่วยซื้อ เช่น คู่/กล่อง)
                cost = _D(row.get('cost_price'))    # ทุนต่อหน่วยซื้อ
                price = _D(row.get('selling_price'))
                wholesale = _D(row.get('wholesale_price'))
                
                # ข้อมูลหน่วย
                unit = row.get('unit', 'ชิ้น')
                items_per_unit = int(row.get('items_per_purchase_unit', 1))
                purchase_unit_name = row.get('purchase_unit_name', unit)
                bundle_type = row.get('bundle_type', 'SAME')
                
                # ===================================================
                # กรณี L-R หรือ F-R → สร้าง แม่ + ลูก 2 ตัว
                # ===================================================
                if bundle_type in ['L-R', 'F-R']:
                    suffix_1 = 'L' if bundle_type == 'L-R' else 'F'
                    suffix_2 = 'R'
                    name_1 = f"{name} ({'ซ้าย' if bundle_type == 'L-R' else 'หน้า'})"
                    name_2 = f"{name} ({'ขวา' if bundle_type == 'L-R' else 'หลัง'})"
                    
                    # ราคาต่อข้าง (หาร 2)
                    price_per_side = price / 2
                    wholesale_per_side = wholesale / 2
                    
                    # ── ลูก defaults พื้นฐาน ──
                    # ⭐ ไม่มี cost_price ตรงนี้ เพราะ post_purchase จะ Weighted Average ให้
                    child_base = {
                        'category_id': row.get('category_id'),
                        'unit': 'ชิ้น',
                        'base_name': name,
                        'items_per_purchase_unit': 1,
                        'purchase_unit_name': '',
                        'allow_partial_sale': True,
                        'bundle_group': sku,
                        'is_bundle': False,
                        'selling_price': price_per_side,
                        'wholesale_price': wholesale_per_side,
                        'compatible_models': row.get('compatible_models', ''),
                        'is_active': True,
                        'primary_supplier': supplier,
                    }
                    
                    # ลูก 1 (ซ้าย/หน้า)
                    d1 = child_base.copy()
                    d1['name'] = name_1
                    d1['bundle_type'] = suffix_1
                    product_1, created_1 = Product.objects.update_or_create(
                        sku=f"{sku}-{suffix_1}", defaults=d1
                    )
                    # สำหรับสินค้าใหม่ ให้ set cost_price เริ่มต้นเลย
                    # (Weighted Average จะทำงานถูกต้องเมื่อมีสต็อกเดิมอยู่แล้ว)
                    if created_1:
                        product_1.cost_price = cost / 2
                        product_1.save(update_fields=['cost_price'])
                        created_count += 1
                    else:
                        updated_count += 1
                    
                    # ลูก 2 (ขวา/หลัง)
                    d2 = child_base.copy()
                    d2['name'] = name_2
                    d2['bundle_type'] = 'R'
                    product_2, created_2 = Product.objects.update_or_create(
                        sku=f"{sku}-{suffix_2}", defaults=d2
                    )
                    if created_2:
                        product_2.cost_price = cost / 2
                        product_2.save(update_fields=['cost_price'])
                        created_count += 1
                    else:
                        updated_count += 1
                    
                    # ── แม่ (Parent bundle) ──
                    # ⭐ แม่ cost_price เก็บ full cost (แม่ไม่มีสต็อกเอง แค่เป็น reference)
                    parent_defaults = {
                        'name': name,
                        'category_id': row.get('category_id'),
                        'base_name': name,
                        'unit': 'ชุด',
                        'bundle_type': bundle_type,
                        'is_bundle': True,
                        'items_per_purchase_unit': items_per_unit,  # ✅ ใช้ค่าจริงจากไฟล์ (เผื่อซื้อเป็นลัง)
                        'purchase_unit_name': purchase_unit_name,
                        'bundle_group': sku,
                        'cost_price': cost,            # แม่เก็บทุนเต็ม (ใช้แค่ reference)
                        'selling_price': price,
                        'wholesale_price': wholesale,
                        'compatible_models': row.get('compatible_models', ''),
                        'is_active': True,
                        'primary_supplier': supplier,
                    }
                    parent_product, created_parent = Product.objects.update_or_create(
                        sku=sku, defaults=parent_defaults
                    )
                    # เชื่อม bundle_components
                    parent_product.bundle_components.set([product_1, product_2])
                    
                    if created_parent: created_count += 1
                    else: updated_count += 1
                    
                    # ── PurchaseItem → บิลใช้ตัวแม่ ──
                    # post_purchase จะเห็นว่า แม่ is_bundle=True
                    # แล้วกระจายสต็อกให้ ลูกๆ พร้อม Weighted Average
                    line_total = qty * cost
                    total_amount += line_total
                    
                    PurchaseItem.objects.create(
                        purchase=purchase,
                        product=parent_product,
                        quantity=qty,
                        unit_cost=cost,
                        line_total=line_total,
                        actual_stock=qty * items_per_unit,  # ✅ คำนวณจำนวนชุดจริงที่รับเข้า
                    )
                
                # ===================================================
                # กรณีปกติ (SAME) → สร้าง/อัปเดต Product คนเดียว
                # ===================================================
                else:
                    # คำนวณต้นทุนต่อชิ้น (สำหรับ สินค้าใหม่)
                    cost_per_piece = cost / items_per_unit if items_per_unit > 0 else cost
                    
                    # ⭐ defaults ไม่มี cost_price
                    # เพราะ post_purchase จะ Weighted Average ให้เอง
                    defaults = {
                        'name': name,
                        'category_id': row.get('category_id'),
                        'unit': unit,
                        'items_per_purchase_unit': items_per_unit,
                        'purchase_unit_name': purchase_unit_name,
                        'allow_partial_sale': True,
                        'bundle_type': 'SAME',
                        'selling_price': price,
                        'wholesale_price': wholesale,
                        'compatible_models': row.get('compatible_models', ''),
                        'is_active': True,
                        'primary_supplier': supplier,
                    }
                    
                    # สร้าง/อัปเดต Product
                    if sku:
                        product, created = Product.objects.update_or_create(
                            sku=sku, defaults=defaults
                        )
                    else:
                        product = Product.objects.create(**defaults)
                        created = True

                    # สำหรับสินค้าใหม่ ให้ set cost_price เริ่มต้นเลย
                    if created:
                        product.cost_price = cost_per_piece
                        product.save(update_fields=['cost_price'])
                        created_count += 1
                    else:
                        updated_count += 1

                    # สร้าง PurchaseItem
                    # unit_cost เก็บทุนต่อหน่วยซื้อ (เช่น ต่อกล่อง)
                    # post_purchase จะ หาร items_per_purchase_unit เอง
                    line_total = qty * cost
                    total_amount += line_total
                    
                    item = PurchaseItem.objects.create(
                        purchase=purchase,
                        product=product,
                        quantity=qty,
                        unit_cost=cost,
                    )
                    
                    item.actual_stock = qty * items_per_unit
                    item.save(update_fields=['actual_stock'])
            
            purchase.grand_total = total_amount          # ← 314
            purchase.save(update_fields=['grand_total'])
            # 4. เรียก Service → จะ คำนวณ Weighted Average + เพิ่มสต็อก
            if post_purchase(purchase):
                messages.success(request, f"✅ บันทึกสำเร็จ! {doc_no} (สินค้าใหม่ {created_count}, เก่า {updated_count})")
            else:
                messages.warning(request, "⚠️ บันทึก Draft แล้ว แต่ยังไม่ตัดสต็อก")

            # เคลียร์ Session
            request.session['import_stage'] = []
            request.session.modified = True
            
            # เก็บ ID บิลล่าสุด
            request.session['last_purchase_id'] = purchase.id

    except Exception as e:
        messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")
        return redirect(redirect_to)

    return redirect('purchase_report')
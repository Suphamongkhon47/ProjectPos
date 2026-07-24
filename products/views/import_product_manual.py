"""
products/views/import_product_manual.py
หน้านำเข้าสินค้าแบบกรอกมือ
รองรับ: แปลงหน่วยซื้อ → หน่วยสต็อก
"""

from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from products.models import Category, Supplier
from .helpers import _D, _stage, _remove_row, _clear_all, _commit_to_database


@login_required
def import_manual(request):
    """นำเข้าสินค้าแบบกรอกเอง"""
    
    if not request.user.is_superuser:
        return render(request, 'products/permission_denied.html', {
            'perm_key': 'Superuser Only (เฉพาะเจ้าของร้าน)',
        }, status=403)
        
    categories = Category.objects.order_by("name")
    suppliers = Supplier.objects.order_by("name")
    stage = _stage(request.session)
    
    if request.method == "GET":
        edit_data = None
        edit_index = request.GET.get("edit")
        
        if edit_index is not None:
            try:
                idx = int(edit_index)
                if 0 <= idx < len(stage):
                    edit_data = stage[idx]
                    stage.pop(idx)
                    request.session.modified = True
            except:
                pass
        
        return render(request, "products/stock/import_manual.html", {
            "categories": categories,
            "suppliers": suppliers,
            "stage": stage,
            "total_rows": len(stage),
            "edit_data": edit_data,
        })
    
    # POST Request
    action = request.POST.get("action")
    
    if action == "add_row":
        return _add_row_manual(request, stage)
    elif action == "remove_row":
        return _remove_row(request, stage, "import_product_manual")
    elif action == "clear_all":
        return _clear_all(request, "import_product_manual")
    elif action == "commit":
        return _commit_to_database(request, stage, "import_product_manual")
    
    return redirect("import_product_manual")


def _add_row_manual(request, stage):
    """
    ฟังก์ชันย่อย: รับค่าจากฟอร์มลง Session
    """
    try:
        # 1. ข้อมูลพื้นฐาน
        category_id = request.POST.get("category")
        raw_sku = (request.POST.get("sku") or "").strip().upper()
        
        sku = raw_sku
        
        name = (request.POST.get("name") or "").strip()
        
        # 2. ราคา (ต่อหน่วยซื้อ)
        cost_price = _D(request.POST.get("cost_price"))       # ทุนต่อกล่อง
        selling_price = _D(request.POST.get("selling_price")) # ราคาขายต่อชิ้น
        wholesale_price = _D(request.POST.get("wholesale_price"))
        
        # 3. ✅ จัดการหน่วย (Logic สำคัญ)
        quantity = _D(request.POST.get("quantity"))  # จำนวนที่ซื้อ (เช่น 10)
        selected_unit = request.POST.get("unit") or "ชิ้น" # หน่วยที่เลือก (เช่น กล่อง)
        
        # ตัวคูณ (เช่น 4)
        items_per_purchase_unit = int(request.POST.get("items_per_purchase_unit") or 1)
        bundle_type = request.POST.get("bundle_type") or "SAME"
        
        # กำหนด Base Unit และ Purchase Unit Name
        if items_per_purchase_unit > 1:
            # กรณีซื้อยกลัง/คู่ -> หน่วยหลักสต็อกควรเป็น "ชิ้น"
            base_unit = "ชิ้น"
            purchase_unit_name = selected_unit 
        else:
            # กรณีซื้อปลีก -> หน่วยหลักตามที่เลือกเลย
            base_unit = selected_unit
            purchase_unit_name = selected_unit
        
        # 4. ข้อมูลเพิ่มเติม
        compatible_models = (request.POST.get("compatible_models") or "").strip()
        created_by = (request.POST.get("created_by") or request.user.username).strip()
        reference = str(request.POST.get("reference") or "MANUAL-IMPORT").strip()
        supplier_id = request.POST.get("supplier") or None
        
        # 5. Validation
        if not category_id or not name or quantity <= 0:
            messages.error(request, "❌ กรุณากรอก: หมวดหมู่, ชื่อสินค้า, และจำนวน")
            return redirect("import_product_manual")
        
        # 6. ดึงชื่อหมวดหมู่
        category_name = "-"
        if category_id:
            try:
                category_name = Category.objects.get(id=category_id).name
            except:
                pass

        # 7. ✅ เก็บลง Session (ระวังเรื่อง Key ให้ตรงกับ Helper)
        item = {
            "category_id": int(category_id),
            "category_name": category_name,
            "sku": sku,
            "name": name,
            "compatible_models": compatible_models,
            
            # ราคาเก็บเป็น String เพื่อกัน Error เวลา Serialize ลง Session
            "cost_price": str(cost_price),
            "selling_price": str(selling_price),
            "wholesale_price": str(wholesale_price),
            
            # ✅ ข้อมูลหน่วยที่ปรับจูนแล้ว
            "quantity": str(quantity),           # จำนวนซื้อ (10)
            "unit": base_unit,                   # หน่วยสต็อก (ชิ้น)
            "items_per_purchase_unit": items_per_purchase_unit, # ตัวคูณ (4)
            "purchase_unit_name": purchase_unit_name,           # ชื่อหน่วยซื้อ (กล่อง)
            "bundle_type": bundle_type,              # ประเภทชุดแยกชุด
            
            "created_by": created_by,
            "reference": reference,
            "supplier_id": int(supplier_id) if supplier_id else None,
        }
        
        stage.append(item)
        request.session.modified = True
        
        # ข้อความแจ้งเตือนให้ชัดเจน
        if items_per_purchase_unit > 1:
            msg = f"✅ เพิ่ม: {name} (ซื้อ {quantity} {purchase_unit_name} x {items_per_purchase_unit} = {quantity * items_per_purchase_unit} {base_unit})"
        else:
            msg = f"✅ เพิ่ม: {name} ({quantity} {base_unit})"
            
        messages.success(request, msg)
        
    except Exception as e:
        messages.error(request, f"❌ เกิดข้อผิดพลาด: {e}")
        
    return redirect("import_product_manual")
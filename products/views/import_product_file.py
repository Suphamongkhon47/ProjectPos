"""
View: นำเข้าสินค้าจากไฟล์ Excel/CSV (Version รองรับหน่วยซื้อ + bundle_type)

ฟีเจอร์:
- รองรับ Excel (.xlsx, .xls) และ CSV
- รองรับ ชิ้น/หน่วย และหน่วยซื้อ
- รองรับ bundle_type (L-R, F-R) จากไฟล์
- คำนวณต้นทุนต่อชิ้นอัตโนมัติ
- Preview ข้อมูลก่อนบันทึก
"""

from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib import messages
import pandas as pd
from django.contrib.auth.decorators import login_required
from products.models import Category, Supplier, Product
from .helpers import _D, _stage, _clear_all, _commit_to_database

@login_required
def import_product_file(request):
    """หน้าหลัก - นำเข้าสินค้าจากไฟล์"""
    
    # โหลด Master Data
    categories = Category.objects.order_by("name")
    suppliers = Supplier.objects.order_by("name")
    
    # โหลดข้อมูล Staging
    stage = _stage(request.session)
    
    # ===== GET: แสดงหน้าอัปโหลด =====
    if request.method == "GET":
        # Reset ถ้ามีการขอ
        if request.GET.get("reset"):
            request.session["import_stage"] = []
            request.session.modified = True
            return redirect("import_product_file")
        
        return render(request, "products/stock/import_file.html", {
            "categories": categories,
            "suppliers": suppliers,
            "stage": stage,
            "total_rows": len(stage),
        })
    
    # ===== POST: ประมวลผล =====
    action = request.POST.get("action")
    
    if action == "upload_file":
        return _upload_file(request, stage)
    elif action == "clear_all":
        return _clear_all(request, "import_product_file")
    elif action == "commit":
        return _commit_to_database(request, stage, "import_product_file")
    
    return redirect("import_product_file")


def _upload_file(request, stage):
    """
    อัปโหลดและประมวลผลไฟล์
    
    คอลัมน์ที่ต้องมี:
    - SKU
    - ชื่อสินค้า
    - หมวดหมู่
    - ราคาทุน (ต่อหน่วยซื้อ)
    - ราคาขาย (ต่อชิ้น)
    - จำนวน
    
    คอลัมน์ไม่บังคับ:
    - รุ่นรถที่ใช้ได้
    - ราคาส่ง
    - หน่วย
    - ชิ้น/หน่วย
    - หน่วยซื้อ
    - bundle_type          ← ใส่ L-R หรือ F-R สำหรับสินค้าคู่
    - ผู้นำเข้า
    - ซัพพลายเออร์
    - เลขที่อ้างอิง
    """
    
    uploaded_file = request.FILES.get("file")
    default_created_by = request.POST.get("created_by", "").strip()
    default_supplier_id = request.POST.get("supplier", None)
    
    if not uploaded_file:
        messages.error(request, "❌ กรุณาเลือกไฟล์")
        return redirect("import_product_file")
    
    try:
        # ===== 1. อ่านไฟล์ =====
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            messages.error(request, "❌ รองรับเฉพาะไฟล์ .xlsx, .xls, .csv")
            return redirect("import_product_file")
        
        # ===== 2. Validate คอลัมน์ที่จำเป็น =====
        required_cols = ['SKU', 'ชื่อสินค้า', 'หมวดหมู่', 'ราคาทุน', 'ราคาขาย', 'จำนวน']
        missing = [col for col in required_cols if col not in df.columns]
        
        if missing:
            messages.error(request, f"❌ ไฟล์ขาดคอลัมน์: {', '.join(missing)}")
            return redirect("import_product_file")
        
        # ===== 3. แปลงเป็น Staging =====
        added_count = 0
        error_count = 0
        
        for idx, row in df.iterrows():
            try:
                # Skip แถวว่าง
                if pd.isna(row['SKU']) or pd.isna(row['ชื่อสินค้า']):
                    continue
                
                # ===== 3.1 หาหมวดหมู่ =====
                category_name = str(row['หมวดหมู่']).strip()
                try:
                    category = Category.objects.get(name__iexact=category_name)
                    category_id = category.id
                except Category.DoesNotExist:
                    messages.warning(request, f"⚠️ แถว {idx+2}: ไม่พบหมวดหมู่ '{category_name}' (ข้าม)")
                    error_count += 1
                    continue
                
                # ===== 3.2 จัดการ Supplier =====
                row_supplier_id = None
                supplier_name = str(row.get('ซัพพลายเออร์', '')).strip() if not pd.isna(row.get('ซัพพลายเออร์')) else ''
                
                if supplier_name:
                    try:
                        supplier = Supplier.objects.get(name__iexact=supplier_name)
                        row_supplier_id = supplier.id
                    except Supplier.DoesNotExist:
                        messages.warning(request, f"⚠️ แถว {idx+2}: ไม่พบซัพพลายเออร์ '{supplier_name}' (ใช้ default)")
                
                # ถ้าไม่มีในไฟล์ ใช้ default
                if not row_supplier_id and default_supplier_id:
                    row_supplier_id = int(default_supplier_id)
                
                # ===== 3.3 ข้อมูลพื้นฐาน =====
                sku = str(row['SKU']).strip().upper()
                name = str(row['ชื่อสินค้า']).strip()
                
                # รุ่นรถ
                compatible_models = str(row.get('รุ่นรถที่ใช้ได้', '')).strip() if not pd.isna(row.get('รุ่นรถที่ใช้ได้')) else ''
                
                # หน่วย (จากไฟล์หรือ default)
                sales_unit = str(row.get('หน่วย', 'ชิ้น')).strip() if not pd.isna(row.get('หน่วย')) else 'ชิ้น'
                
                # ชิ้น/หน่วย (default = 1)
                items_per_unit = 1
                if 'ชิ้น/หน่วย' in df.columns and not pd.isna(row.get('ชิ้น/หน่วย')):
                    try:
                        items_per_unit = int(float(row['ชิ้น/หน่วย']))
                        if items_per_unit < 1:
                            items_per_unit = 1
                    except:
                        items_per_unit = 1
                
                # หน่วยซื้อ (จากไฟล์หรือ default)
                purchase_unit_name = str(row.get('หน่วยซื้อ', '')).strip() if not pd.isna(row.get('หน่วยซื้อ')) else ''
                
                # กำหนด Base Unit และ Purchase Unit Name
                if items_per_unit > 1:
                    base_unit = "ชิ้น"
                    if not purchase_unit_name:
                        purchase_unit_name = sales_unit if sales_unit != "ชิ้น" else "ชุด"
                else:
                    base_unit = sales_unit
                    if not purchase_unit_name:
                        purchase_unit_name = sales_unit
                
                # ===== 3.4 bundle_type =====
                # อ่านจากไฟล์ ถ้ามี column bundle_type
                # ค่าที่รับ: L-R, F-R (นอกนั้นเป็น SAME)
                bundle_type = 'SAME'
                if 'bundle_type' in df.columns and not pd.isna(row.get('bundle_type')):
                    raw_bt = str(row['bundle_type']).strip().upper()
                    if raw_bt in ['L-R', 'F-R']:
                        bundle_type = raw_bt
                
                # ===== 3.5 ราคา =====
                cost_price = float(row['ราคาทุน']) if not pd.isna(row['ราคาทุน']) else 0
                selling_price = float(row['ราคาขาย']) if not pd.isna(row['ราคาขาย']) else 0
                wholesale_price = float(row.get('ราคาส่ง', 0)) if not pd.isna(row.get('ราคาส่ง')) else 0
                
                # จำนวน
                quantity = float(row['จำนวน']) if not pd.isna(row['จำนวน']) else 0
                
                # ผู้นำเข้า
                file_created_by = str(row.get('ผู้นำเข้า', '')).strip() if not pd.isna(row.get('ผู้นำเข้า')) else default_created_by
                
                # เลขที่อ้างอิง
                reference = str(row.get('เลขที่อ้างอิง', 'FILE-IMPORT')).strip() if not pd.isna(row.get('เลขที่อ้างอิง')) else 'FILE-IMPORT'
                
                # ===== 3.6 Validate =====
                if not sku or not name or quantity <= 0:
                    messages.warning(request, f"⚠️ แถว {idx+2}: ข้อมูลไม่ครบหรือจำนวน ≤ 0 (ข้าม)")
                    error_count += 1
                    continue
                
                if cost_price < 0 or selling_price < 0:
                    messages.warning(request, f"⚠️ แถว {idx+2}: ราคาต้องไม่ติดลบ (ข้าม)")
                    error_count += 1
                    continue
                
                # ===== 3.7 เพิ่มลง Staging =====
                stage.append({
                    "category_id": category_id,
                    "category_name": category_name,
                    "sku": sku,
                    "name": name,
                    "compatible_models": compatible_models,
                    "bundle_type": bundle_type,                  # ← L-R / F-R / SAME
                    
                    # ข้อมูลหน่วย
                    "unit": base_unit,                           # หน่วยสต็อก (ชิ้น)
                    "items_per_purchase_unit": items_per_unit,   # ตัวคูณ (เช่น 4 สำหรับกล่อง)
                    "purchase_unit_name": purchase_unit_name,    # ชื่อหน่วยซื้อ (เช่น กล่อง)
                    
                    # ราคา (เก็บเป็น String เพื่อกัน Error Serialize)
                    "cost_price": str(cost_price),
                    "selling_price": str(selling_price),
                    "wholesale_price": str(wholesale_price),
                    "quantity": str(quantity),
                    
                    "created_by": file_created_by,
                    "reference": reference,
                    "supplier_id": row_supplier_id,
                })
                added_count += 1
                
            except Exception as e:
                messages.warning(request, f"⚠️ แถว {idx+2}: {str(e)} (ข้าม)")
                error_count += 1
                continue
        
        # บันทึก Session
        request.session.modified = True
        
        # ===== 4. สรุปผล =====
        if added_count > 0:
            messages.success(request, f"✅ อัปโหลดสำเร็จ: {added_count} รายการ")
        if error_count > 0:
            messages.warning(request, f"⚠️ ข้าม/ผิดพลาด: {error_count} รายการ")
        if added_count == 0:
            messages.error(request, "❌ ไม่สามารถนำเข้าข้อมูลได้")
        
    except Exception as e:
        messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")
    
    return redirect("import_product_file")
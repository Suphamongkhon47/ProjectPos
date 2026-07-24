# 📝 Project Notes — Pos-Project (อ่านไฟล์นี้ก่อนเพื่อเข้าใจโปรเจกต์เร็วๆ)

> ไฟล์นี้เป็นโน้ตสรุปสำหรับ Claude (หรือใครก็ตามที่มาช่วยดูโค้ด) ให้เข้าใจภาพรวมโปรเจกต์ได้เร็ว โดยไม่ต้องไล่อ่านทุกไฟล์ใหม่ทุกครั้ง
> อัปเดตล่าสุด: ตรวจสอบโค้ดจริงแล้ว (กรกฎาคม 2026)

## ภาพรวม
ระบบ POS (จุดขายหน้าร้าน) สำหรับธุรกิจขายอะไหล่รถยนต์ — เป็น Capstone Project จบการศึกษา
Stack: **Python (Django 5.2.7) + MySQL + Tailwind CSS (django-tailwind) + Git**
ภาษาในโค้ด/UI: ไทยล้วน (variable/verbose_name ภาษาไทยเยอะ)

## โครงสร้างหลัก
- `pos_system/` — settings, urls หลักของโปรเจกต์ Django (settings.py ใช้ MySQL, Tailwind, Channels/Daphne)
- `accounts/` — ระบบ login/logout (Django session-based auth ปกติ ไม่ใช่ JWT) + จัดการพนักงาน (Employee model ผูกกับ User แบบ OneToOne, มี avatar เก็บเป็น Base64, position แบ่งแค่ STAFF กับ superuser=เจ้าของร้าน)
- `products/` — แอปหลักของระบบ แบ่งเป็น:
  - `models/` — catalog.py (Product, Category, Supplier), inventory.py (StockMovement), Transaction.py, payment.py, purchase.py, system_setting.py
  - `Services/` — business logic แยกออกจาก views (sale_service.py, payment_service.py, purchase_service.py, return_service.py, product_service.py)
  - `views/` — แบ่งย่อยตามฟีเจอร์ (dashboard, sales, returns, stock_views, supplier_view, category_views ฯลฯ)
  - `urls.py` — รวม endpoint ทั้งหมด, มี `api/...` หลายจุดแต่เป็น Django view ธรรมดา return JSON (ไม่ได้ใช้ Django REST Framework — ไม่มี `rest_framework` ใน INSTALLED_APPS)
- `theme/` — Tailwind CSS app (django-tailwind)

## จุดเด่นทางเทคนิคที่ตรวจสอบแล้วว่ามีจริง (ใช้ตอนเขียนเรซูเม่ได้)
1. **คำนวณสต็อกซับซ้อน** — `StockMovement` model เก็บ snapshot (unit_cost, balance_after) ทุกครั้งที่มีการเคลื่อนไหวสต็อก (IN/OUT/ADJ)
2. **Bundle product** — สินค้าชุด (เช่น โช้คอัพคู่ซ้าย-ขวา) ตัด/คืนสต็อกจากสินค้าลูกหลายตัวพร้อมกันได้ (`bundle_components`, M2M self-referencing)
3. **Atomic transaction + race condition protection** — ใช้ `db_transaction.atomic()` และ `select_for_update()` ตอนตัด/คืนสต็อก
4. **ระบบพักบิล (Held Bills)** — ไม่ใช่ shopping cart ทั่วไป แต่เป็นระบบพักบิล-เรียกคืนบิล (`held-bills`, `resume`, `discard` API)
5. **Soft delete อัจฉริยะ** — `Product.delete()` เช็คว่าสินค้าเคยขายหรือเป็นส่วนหนึ่งของ bundle ไหม ถ้าใช่จะ soft-delete (ปิดการใช้งาน) แทนการลบจริง
6. **Auto-generate SKU** — สร้างรหัสสินค้าอัตโนมัติตาม prefix ของหมวดหมู่ เช่น BRK-001, ENG-001

## สิ่งที่ควร "ระวัง" ตอนเขียนเรซูเม่ (อย่า over-claim)
- ❌ อย่าเขียนว่า "RESTful API" เพราะไม่ได้ใช้ DRF จริง → ใช้คำว่า "JSON API endpoints" หรือ "AJAX-based API" แทน
- ❌ อย่าเขียนว่า "JWT Authentication" → เป็น Django session-based auth ธรรมดา
- ❌ Employee role มีแค่ STAFF เดียว (เจ้าของร้านใช้ is_superuser) ไม่ใช่ระบบ role หลายระดับ

## ไฟล์ที่ควรเปิดดูก่อนถ้าจะแก้/วิเคราะห์ต่อ
- ดู business logic: `products/Services/sale_service.py` (ฟังก์ชันหลัก: create_sale_transaction, post_sale, cancel_sale)
- ดู routing ทั้งหมด: `products/urls.py`, `accounts/urls.py`
- ดู models ทั้งหมด: `products/models/*.py`
- ดู settings/config: `pos_system/settings.py`

## TODO / ของที่ยังไม่ได้ตรวจ (ถ้าจะดูต่อ)
- ยังไม่ได้ดู `products/views/` ในรายละเอียดทุกไฟล์
- ยังไม่ได้ดู git log/commit history เพื่อยืนยันความสม่ำเสมอของการใช้ Git
- ยังไม่ได้ดู templates/ (frontend จริง) เพื่อยืนยัน Responsive Design

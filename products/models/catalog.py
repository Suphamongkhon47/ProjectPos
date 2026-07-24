
from django.db import models
from products.models.Transaction import TransactionItem 
import uuid




# ------------------------
# 1. Category
# ------------------------
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อหมวดหมู่")
    name_en = models.CharField(max_length=100, blank=True, verbose_name="ชื่อภาษาอังกฤษ")
    code = models.CharField(max_length=10, unique=True, default='GEN', verbose_name="รหัสย่อ (3 ตัวอักษร)")
    description = models.TextField(blank=True, verbose_name="รายละเอียด")

    class Meta:
        db_table = "categories"
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.code} - {self.name}" if self.code else self.name


# ------------------------
# 2. Supplier
# ------------------------
class Supplier(models.Model):
    name = models.CharField(max_length=200, verbose_name="ชื่อร้านค้า/บริษัท")
    phone = models.CharField(max_length=20, blank=True, verbose_name="เบอร์โทร")
    address = models.TextField(blank=True, verbose_name="ที่อยู่")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "suppliers"

    def __str__(self):
        return self.name




# ------------------------
# 4. Product
# ------------------------
class Product(models.Model):
    
    BUNDLE_TYPE_CHOICES = [
        ('SAME', 'เหมือนกันหมด'),
        ('L-R', 'ซ้าย-ขวา'),
        ('F-R', 'หน้า-หลัง'),
    ]
    # FK เชื่อมโยง
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่")
    primary_supplier = models.ForeignKey('Supplier', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ซัพพลายเออร์")

    # ข้อมูลหลัก
    sku = models.CharField(max_length=50, unique=True, blank=True, verbose_name="รหัสสินค้า (SKU)")
    name = models.CharField(max_length=200, db_index=True, verbose_name="ชื่อสินค้า")
    base_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="ชื่อสินค้า (กลาง)")
    description = models.TextField(blank=True, verbose_name="รายละเอียด")
    
    # หน่วยนับ
    unit = models.CharField(max_length=50, default="ชิ้น", verbose_name="หน่วยนับ")
    bundle_type = models.CharField(max_length=10,choices=BUNDLE_TYPE_CHOICES,default='SAME',verbose_name="ประเภทชุด")
    bundle_group = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    is_bundle = models.BooleanField(default=False, verbose_name="เป็นสินค้าชุด")
    bundle_components = models.ManyToManyField('self', symmetrical=False, blank=True, verbose_name="สินค้าในชุด (Components)")
    # ราคา
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาทุนปัจจุบัน")
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาขาย")
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาขายส่ง")
    
    # การค้นหา
    compatible_models = models.CharField(max_length=255, blank=True, verbose_name="รุ่นรถที่ใช้ได้")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="คงเหลือ")
    
    min_stock = models.DecimalField(max_digits=12, decimal_places=2, default=5, verbose_name="สต็อกขั้นต่ำ")
    items_per_purchase_unit = models.IntegerField(default=1, verbose_name="จำนวนชิ้นต่อหน่วยซื้อ")
    purchase_unit_name = models.CharField(max_length=20, blank=True, verbose_name="หน่วยซื้อ")
    allow_partial_sale = models.BooleanField(default=True, verbose_name="อนุญาตให้แบ่งขาย")
    # สถานะ
    is_active = models.BooleanField(default=True, verbose_name="เปิดขาย")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"

    def save(self, *args, **kwargs):
        # สร้าง SKU อัตโนมัติ (ใช้ category.code)
        if not self.sku:
            # 1. สร้าง Prefix จาก category.code
            if self.category and self.category.code:
                prefix = self.category.code.upper()
            else:
                prefix = "GEN"  # General (ไม่มีหมวดหมู่)
            
            # 2. หาเลขล่าสุดของ Prefix นี้
            last_product = Product.objects.filter(
                sku__startswith=f"{prefix}-"
            ).order_by('-sku').first()
            
            if last_product:
                try:
                    # แยกเลขออกจาก SKU เช่น "BRK-005" -> 5
                    last_number = int(last_product.sku.split('-')[1])
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    # ถ้าแปลงไม่ได้ ให้เริ่มที่ 1
                    new_number = 1
            else:
                # ถ้ายังไม่มี Prefix นี้เลย เริ่มที่ 1
                new_number = 1
            
            # 3. สร้าง SKU: BRK-001, ENG-001, GEN-001
            self.sku = f"{prefix}-{new_number:03d}"
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def delete(self, *args, **kwargs):
        
        # 1. เช็คว่ามี FK หรือไม่ (เคยขายหรือยัง)
        has_sales = TransactionItem.objects.filter(product_id=self.id).exists()
        
        # 2. เช็คว่าเป็นส่วนประกอบใน Bundle หรือไม่
        in_bundles = False
        if not has_sales:
             in_bundles = TransactionItem.objects.filter(bundle_items__contains=self.id).exists()

        if has_sales or in_bundles:
            # 🔴 ถ้ามีประวัติ -> แค่ปิดการใช้งาน (Soft Delete)
            if self.is_active:
                self.is_active = False
                self.save(update_fields=['is_active'])
                # คืนค่าบอกว่าไม่ได้ลบนะ
                return False, {"msg": f"สินค้า {self.sku} เคยขายแล้ว ระบบได้ทำการ 'ปิดการใช้งาน' แทนการลบ"}
        else:
            # 🟢 ถ้าสินค้าใหม่ซิงๆ -> ลบจริง (Hard Delete)
            super().delete(*args, **kwargs)
            return True, {"msg": f"ลบสินค้า {self.sku} ถาวรเรียบร้อย"}



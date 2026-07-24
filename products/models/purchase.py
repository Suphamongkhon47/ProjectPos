from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth import get_user_model

from django.utils import timezone


User = get_user_model()



# ------------------------
# Purchase (หัวเอกสารรับเข้า)
# ------------------------
class Purchase(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'ร่าง'),
        ('POSTED', 'ยืนยันรับของ'),
        ('CANCELLED', 'ยกเลิก'),
    ]

    doc_no = models.CharField(max_length=50, unique=True, verbose_name="เลขที่เอกสาร")
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, verbose_name="ซื้อจาก")
    purchase_date = models.DateTimeField(default=timezone.now, verbose_name="วันที่ซื้อ")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ยอดรวม")
    remark = models.TextField(blank=True, verbose_name="หมายเหตุ")
    
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "purchases"
        ordering = ['-purchase_date']

    def __str__(self):
        return f"{self.doc_no} - {self.grand_total} ฿"
    
    def calculate_totals(self):
        """คำนวณยอดรวม"""
        from django.db.models import Sum
        total = self.items.aggregate(total=Sum('line_total'))['total'] or Decimal('0')
        self.grand_total = total
        self.save(update_fields=['grand_total'])
    
    def post(self):
        """ยืนยันรับของ (เพิ่มสต็อก)"""
        from products.Services.purchase_service import post_purchase
        return post_purchase(self)
    
    def cancel(self):
        """ยกเลิก (ลดสต็อก)"""
        from products.Services.purchase_service import cancel_purchase
        return cancel_purchase(self)

# ========================
# PurchaseItem (รายการสินค้า)
# ========================
class PurchaseItem(models.Model):
    purchase = models.ForeignKey('Purchase', on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="จำนวน")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="ทุนต่อหน่วย (บาท)")
    actual_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0,verbose_name="เพิ่มสต็อก (ชิ้น)")
    
    # คำนวณยอดรวมบรรทัด (optional เก็บไว้ช่วยดูง่าย)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "purchase_items"

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_cost
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.purchase.doc_no} - {self.product.name} ({self.quantity} {self.product.unit})"
    
    
    

from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.db.models import Sum



from django.utils import timezone
from datetime import datetime

User = get_user_model()


# ------------------------
# Transaction 
# ------------------------
class Transaction(models.Model):
    
    # ✅ 1. เพิ่มตัวเลือกประเภทเอกสาร
    DOC_TYPE_CHOICES = [
        ('SALE', 'บิลขายปกติ'),
        ('RETURN', 'รับคืน'),
    ]
    
    STATUS_CHOICES = [
        ('HOLD', 'พักบิล'),
        ('POSTED', 'ขายแล้ว'),
        ('CANCELLED', 'ยกเลิก'),
    ]
    doc_type = models.CharField(max_length=10, choices=DOC_TYPE_CHOICES, default='SALE', db_index=True, verbose_name="ประเภทเอกสาร")
    ref_doc_no = models.CharField(max_length=50, blank=True, verbose_name="อ้างอิงเลขที่บิลเดิม")
    doc_no = models.CharField(max_length=50, unique=True, blank=True, verbose_name="เลขที่บิล")
    transaction_date = models.DateTimeField(default=timezone.now, db_index=True)
    
    # ✅ เพิ่ม: ยอดเงิน
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ยอดรวม")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ส่วนลด")
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ยอดสุทธิ")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='HOLD', db_index=True)
    remark = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # ✅ เพิ่ม

    class Meta:
        db_table = "Transaction"
        ordering = ['transaction_date']

    def __str__(self):
        type_label = "คืน" if self.doc_type == 'RETURN' else "ขาย"
        return f"[{type_label}] {self.doc_no} - {self.grand_total:,.2f} ฿"
    
    

    def save(self, *args, **kwargs):
        if not self.doc_no:
            today_str = datetime.now().strftime('%y%m%d')
            prefix = 'RET' if self.doc_type == 'RETURN' else 'SALE'
            last_sale = Transaction.objects.filter(doc_no__startswith=f'{prefix}-{today_str}').order_by('doc_no').last()
            
            if last_sale:
                last_id = int(last_sale.doc_no.split('-')[-1])
                new_id = last_id + 1
            else:
                new_id = 1
            self.doc_no = f"{prefix}-{today_str}-{new_id:04d}"
        super().save(*args, **kwargs)

    def calculate_totals(self):
        total = self.items.aggregate(total=Sum('line_total'))['total'] or Decimal('0')
        self.total_amount = total
        self.grand_total = total - self.discount_amount
        self.save(update_fields=['total_amount', 'grand_total'])

    def post(self):
        """ยืนยันบิล (เรียก Service)"""
        from products.Services.sale_service import post_sale
        return post_sale(self)
    
    def cancel(self):
        """ยกเลิกบิล (เรียก Service)"""
        from products.Services.sale_service import cancel_sale
        return cancel_sale(self)

# ------------------------
# TransactionItem (รายการขาย)
# ------------------------
class TransactionItem(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1,verbose_name="จำนวน")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="ราคาขาย")
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="ต้นทุน")
    
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0,verbose_name="รวม")
    unit_type = models.CharField(max_length=20, default='ชิ้น',verbose_name='หน่วยขาย')
    display_sku = models.CharField(max_length=50, blank=True, verbose_name='SKU ที่แสดง')
    bundle_items = models.JSONField(null=True, blank=True, verbose_name='รายการสินค้าในชุด')

    class Meta:
        db_table = "Transaction_items"

    def __str__(self):
        return f"{self.transaction.doc_no} - {self.product.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        # ตั้งค่าราคาถ้ายังไม่มี
        if not self.id:
            if self.unit_price is None:
                self.unit_price = self.product.selling_price
            if self.cost_price is None:
                self.cost_price = self.product.cost_price
        
        # ✅ คำนวณยอดรวม
        self.line_total = self.quantity * self.unit_price
        
        super().save(*args, **kwargs)
    
    @property
    def profit(self):
        """กำไรต่อรายการ"""
        return (self.unit_price - self.cost_price) * self.quantity
    
    @property
    def profit_margin(self):
        """Profit Margin (%)"""
        if self.unit_price == 0:
            return 0
        return (self.profit / self.line_total * 100)
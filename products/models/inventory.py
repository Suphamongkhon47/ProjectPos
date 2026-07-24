from django.db import models

# ------------------------
# Stock Movement
# ------------------------
class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('IN', 'รับเข้า'),
        ('OUT', 'ขายออก'),
        ('ADJ', 'ปรับยอด'),
    ]

    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_TYPES, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="จำนวนที่ขยับ")
    
    # Snapshot สำคัญ
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ต้นทุนต่อหน่วย")
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="คงเหลือหลังทำรายการ")
    
    reference = models.CharField(max_length=100, blank=True, db_index=True, verbose_name="อ้างอิงเอกสาร")
    note = models.TextField(blank=True, null=True, verbose_name="หมายเหตุ") 
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "stock_movements"
        ordering = ['-created_at']
    
    def __str__(self):
        sign = "+" if self.movement_type == 'IN' else "-"
        return f"[{self.movement_type}] {self.product.sku} {sign}{self.quantity}"
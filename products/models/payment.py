from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model


User = get_user_model()


# ========================
# Payment (การรับชำระเงิน)
# ========================
class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'เงินสด'),
        ('qr', 'QR Code'),
        ('transfer', 'โอนเงิน'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'รอตรวจสอบ'),
        ('confirmed', 'ยืนยันแล้ว'),
        ('void', 'ยกเลิก'),
    ]

    transaction = models.OneToOneField('Transaction', on_delete=models.CASCADE, related_name='payment')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash',verbose_name="วิธีชำระเงิน")
    
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ยอดที่ต้องชำระ")
    
    # ✅ เพิ่ม: สำหรับเงินสด
    received = models.DecimalField(max_digits=12, decimal_places=2, default=0,verbose_name="เงินที่รับ")
    change = models.DecimalField(max_digits=12, decimal_places=2, default=0,verbose_name="เงินทอน")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    
    note = models.TextField(blank=True,verbose_name="หมายเหตุ")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction.doc_no} - {self.get_method_display()}"

    def save(self, *args, **kwargs):
        if self.method == 'cash':
            received = self.received or Decimal('0')
            amount = self.amount or Decimal('0')
            self.change = received - amount
        else:
            self.change = Decimal('0')
        super().save(*args, **kwargs)
        

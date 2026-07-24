import base64
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # ==============================
    # 👤 1. ข้อมูลส่วนตัว
    # ==============================
    nickname = models.CharField(max_length=50, verbose_name="ชื่อเล่น")
    
    # เก็บรูปเป็น Base64
    avatar = models.TextField(blank=True, default="", verbose_name="รูปโปรไฟล์ (Base64)")
    
    phone = models.CharField(max_length=15, blank=True, verbose_name="เบอร์โทรศัพท์")
    address = models.TextField(blank=True, verbose_name="ที่อยู่")

    # ==============================
    # 🛡️ 2. กำหนดสิทธิ์
    # ==============================
    # เหลือแค่ STAFF (พนักงาน) อย่างเดียว
    # (ส่วนเจ้าของร้านจะใช้ is_superuser ในตาราง User แทน)
    POSITION_CHOICES = [
        ('STAFF', 'พนักงาน'),       
    ]
    position = models.CharField(max_length=10, choices=POSITION_CHOICES, default='STAFF', verbose_name="ตำแหน่ง")

    def __str__(self):
        role = "เจ้าของร้าน" if self.user.is_superuser else "พนักงาน"
        return f"{self.nickname} ({role})"
    
    def set_avatar_from_file(self, image_file):
        """ฟังก์ชันช่วยแปลงไฟล์รูป -> ข้อความ Base64"""
        if image_file:
            image_data = image_file.read()
            encoded_string = base64.b64encode(image_data).decode('utf-8')
            self.avatar = f"data:image/jpeg;base64,{encoded_string}"

# ==============================
# ⚡ Signals
# ==============================
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Employee.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except Employee.DoesNotExist:
        Employee.objects.create(user=instance)
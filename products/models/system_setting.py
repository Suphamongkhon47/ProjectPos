"""
models/system_setting.py
— เก็บ config ของระบบ แบบ key-value
— เปลี่ยนค่าได้จากหน้า UI โดยไม่ต้อง deploy ใหม่
"""

from django.db import models


# ===================================================
# Default values (ใช้เป็น seed ตอน migrate)
# ===================================================
SYSTEM_SETTINGS_DEFAULTS = {
    "store_name":           "ร้านขายอะไหล่ยนต์",
    "store_phone":          "",
    "store_address":        "",
    "receipt_footer":       "ขอบคุณที่ใช้บริการ",
}

# Meta สำหรับ UI (label, placeholder, type)
SYSTEM_SETTINGS_META = {
    "store_name": {
        "label": "ชื่อร้านค้า",
        "placeholder": "เช่น ร้านขายอะไหล่ยนต์",
        "type": "text"
    },
    "store_phone": {
        "label": "เบอร์โทร",
        "placeholder": "เช่น 083-475-5649",
        "type": "text"
    },
    "store_address": {
        "label": "ที่อยู่ร้าน",
        "placeholder": "เช่น 123 ถนนรามคำแหง กรุงเทพมหานคร",
        "type": "textarea"
    },
    "receipt_footer": {
        "label": "ข้อความท้ายบิล",
        "placeholder": "เช่น ขอบคุณที่ใช้บริการ",
        "type": "text"
    },
}


class SystemSetting(models.Model):
    key   = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField(blank=True, default="")

    class Meta:
        db_table = "system_settings"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    # ─── Helper class methods ───────────────────────────
    @classmethod
    def get(cls, key, default=None):
        """ดึง value จาก key — ถ้าไม่มี return default"""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default if default is not None else SYSTEM_SETTINGS_DEFAULTS.get(key, "")

    @classmethod
    def set(cls, key, value):
        """บันทึก key-value (upsert)"""
        obj, _ = cls.objects.update_or_create(key=key, defaults={"value": str(value)})
        return obj

    @classmethod
    def get_all(cls):
        """ดึง dict ทั้งหมด — ใช้สำหรับ render หน้า settings"""
        rows = {row.key: row.value for row in cls.objects.all()}
        # merge กับ defaults (เพื่อให้ key ใหม่ที่ยัง migrate ไม่ done ก็มี)
        result = dict(SYSTEM_SETTINGS_DEFAULTS)
        result.update(rows)
        return result

    @classmethod
    def seed_defaults(cls):
        """เรียกครั้งเดียวตอน migrate — สร้าง row จาก DEFAULTS"""
        for key, value in SYSTEM_SETTINGS_DEFAULTS.items():
            cls.objects.get_or_create(key=key, defaults={"value": value})

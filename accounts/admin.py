from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import Employee
from .forms import EmployeeAdminForm  # Import Form ที่เราสร้าง

class EmployeeInline(admin.StackedInline):
    model = Employee
    form = EmployeeAdminForm  # ✅ บังคับให้ใช้ Form พิเศษที่มีปุ่ม Upload
    can_delete = False
    verbose_name_plural = 'ข้อมูลพนักงาน'
    
    # โชว์รูปตัวอย่างในหน้าแก้ไข
    readonly_fields = ['show_avatar_preview']
    def show_avatar_preview(self, obj):
        if obj.avatar:
            # เอา Base64 มาแสดงเป็นรูป
            return format_html(f'<img src="{obj.avatar}" style="height: 100px; border-radius: 10px;" />')
        return "ไม่มีรูปภาพ"
    show_avatar_preview.short_description = "ตัวอย่างรูปปัจจุบัน"

class UserAdmin(BaseUserAdmin):
    inlines = (EmployeeInline,)
    list_display = ('username', 'get_nickname', 'get_position', 'is_staff')
    
    def get_nickname(self, obj):
        return obj.profile.nickname
    get_nickname.short_description = 'ชื่อเล่น'

    def get_position(self, obj):
        return obj.profile.get_position_display()
    get_position.short_description = 'ตำแหน่ง'

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
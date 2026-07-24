"""
views/receipt_settings_views.py
— หน้าตั้งค่าบิล/ใบเสร็จ (GET แสดง, POST บันทึก)
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from products.models.system_setting import SystemSetting, SYSTEM_SETTINGS_META


@login_required
def receipt_settings(request):
    """หน้าตั้งค่าบิล/ใบเสร็จ"""
    
    if not request.user.is_superuser:
        return render(request, 'products/permission_denied.html', {
            'perm_key': 'Superuser Only (เฉพาะเจ้าของร้าน)',
        }, status=403)
        
    if request.method == 'POST':
        # บันทึกทุก key ที่มี META
        for key, meta in SYSTEM_SETTINGS_META.items():
            if meta['type'] == 'checkbox':
                # Checkbox: มี = true, ไม่มี = false
                value = 'true' if request.POST.get(key) else 'false'
            else:
                # Text/Textarea
                value = request.POST.get(key, "").strip()
            
            SystemSetting.set(key, value)
        
        messages.success(request, "✅ บันทึกการตั้งค่าบิลเรียบร้อย")
        return redirect('receipt_settings')

    # GET — ดึงค่าทั้งหมด
    current = SystemSetting.get_all()

    # เรียง fields เป็น list สำหรับ template
    fields = []
    for key, meta in SYSTEM_SETTINGS_META.items():
        field = {
            "key":         key,
            "label":       meta["label"],
            "type":        meta["type"],
            "placeholder": meta.get("placeholder", ""),
            "value":       current.get(key, ""),
        }
        
        # Checkbox: แปลง "true"/"false" เป็น boolean
        if meta['type'] == 'checkbox':
            field['checked'] = (current.get(key, "false").lower() == "true")
        
        fields.append(field)

    return render(request, 'products/settings/receipt_settings.html', {
        "fields": fields,
    })

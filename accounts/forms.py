from django import forms
from .models import Employee

class EmployeeAdminForm(forms.ModelForm):
    # สร้างช่อง Upload ขึ้นมาลอยๆ (ไม่ลง DB โดยตรง)
    avatar_file = forms.ImageField(required=False, label="อัปโหลดรูปโปรไฟล์ (เลือกไฟล์ใหม่)")

    class Meta:
        model = Employee
        fields = '__all__'
        # ซ่อน field avatar ที่เป็นตัวหนังสือยาวๆ ไม่ให้รกตา
        widgets = {
            'avatar': forms.HiddenInput(),
        }

    def save(self, commit=True):
        # 1. ดึงข้อมูลพนักงานออกมา
        employee = super().save(commit=False)
        
        # 2. เช็คว่ามีการอัปโหลดไฟล์ใหม่มาไหม?
        uploaded_file = self.cleaned_data.get('avatar_file')
        if uploaded_file:
            # ถ้ามี ให้แปลงเป็น Base64 แล้วยัดใส่ field avatar
            employee.set_avatar_from_file(uploaded_file)
            
        if commit:
            employee.save()
        return employee
from django import forms
from products.models import Category


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        # ✅ เพิ่ม code และ name_en เข้าไปใน fields
        fields = ['code', 'name', 'name_en', 'description']
        
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'input input-bordered w-full uppercase font-mono', # ใส่ font-mono ให้ดูเป็นรหัส
                'placeholder': 'เช่น: ENG, BRK (3 ตัวอักษร)',
                'maxlength': '10'
            }),
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'เช่น: เครื่องยนต์, ระบบเบรก',
            }),
            'name_en': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'เช่น: Engine, Brake System (ไม่บังคับ)',
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'รายละเอียดเพิ่มเติม...',
            }),
        }
        
        labels = {
            'code': '🔖 รหัสย่อ',
            'name': '📝 ชื่อหมวดหมู่ (ไทย)',
            'name_en': '🇬🇧 ชื่อหมวดหมู่ (อังกฤษ)',
            'description': '📄 รายละเอียด',
        }
    
    def clean_name(self):
        """ตรวจสอบชื่อหมวดหมู่"""
        name = self.cleaned_data.get('name', '').strip()
        
        # ต้องไม่ว่าง
        if not name:
            raise forms.ValidationError('❌ กรุณาระบุชื่อหมวดหมู่')
        
        # อย่างน้อย 2 ตัวอักษร
        if len(name) < 2:
            raise forms.ValidationError('❌ ชื่อหมวดหมู่ต้องมีอย่างน้อย 2 ตัวอักษร')
        
        # เช็คชื่อซ้ำ (case-insensitive)
        existing = Category.objects.filter(name__iexact=name)
        
        # ถ้าเป็นการแก้ไข → ยกเว้นตัวเอง
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        
        if existing.exists():
            raise forms.ValidationError(f'❌ หมวดหมู่ "{name}" มีอยู่ในระบบแล้ว')
        
        return name
    
    def clean_description(self):
        """ทำความสะอาด description"""
        description = self.cleaned_data.get('description', '').strip()
        return description
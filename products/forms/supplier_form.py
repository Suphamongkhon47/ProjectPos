# products/forms.py
"""
Django Forms สำหรับจัดการข้อมูล
เพิ่ม SupplierForm ลงในไฟล์นี้
"""

# ... imports และ Forms อื่นๆ ที่มีอยู่แล้ว ...
# from django import forms
# from products.models import Product, Category, Supplier
# 
# class ProductForm(forms.ModelForm):
#     ...
# 
# class CategoryForm(forms.ModelForm):
#     ...


# ===================================================
# ⬇️ เพิ่ม SupplierForm ใหม่ (Copy ส่วนนี้)
# ===================================================

from django import forms

from products.models.catalog import Supplier



class SupplierForm(forms.ModelForm):
    """
    Form สำหรับเพิ่ม/แก้ไขซัพพลายเออร์
    """
    
    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'address']
        
        # กำหนด Widgets (รูปแบบ HTML)
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'เช่น ABC Auto Parts Co., Ltd.'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'เช่น 081-234-5678'
            }),
            'address': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'placeholder': 'ที่อยู่เต็ม เช่น 123 ถ.พระราม4 แขวงทุ่งมหาเมฆ เขตสาทร กรุงเทพฯ 10120',
                'rows': 4
            }),
        }
        
        # กำหนด Labels (ภาษาไทย)
        labels = {
            'name': 'ชื่อร้าน/บริษัท',
            'phone': 'เบอร์โทรศัพท์',
            'address': 'ที่อยู่',
        }
        
        # กำหนด Help Text (คำแนะนำ)
        help_texts = {
            'name': 'ชื่อเต็มของร้านค้าหรือบริษัท',
            'phone': 'เบอร์ติดต่อหลัก (สามารถเว้นว่างได้)',
            'address': 'ที่อยู่สำหรับจัดส่งเอกสารและติดต่อ (สามารถเว้นว่างได้)',
        }
    
    def clean_name(self):
        """
        ตรวจสอบชื่อซัพพลายเออร์
        """
        name = self.cleaned_data.get('name')
        
        # ตรวจสอบว่ากรอกหรือไม่
        if not name or name.strip() == '':
            raise forms.ValidationError('❌ กรุณากรอกชื่อร้าน/บริษัท')
        
        # ตรวจสอบความยาว
        if len(name) < 2:
            raise forms.ValidationError('❌ ชื่อต้องมีอย่างน้อย 2 ตัวอักษร')
        
        # ตรวจสอบชื่อซ้ำ (ถ้าเป็นการเพิ่มใหม่)
        if not self.instance.pk:  # ถ้าไม่มี pk = เพิ่มใหม่
            if Supplier.objects.filter(name__iexact=name).exists():
                raise forms.ValidationError(f'❌ มีซัพพลายเออร์ชื่อ "{name}" อยู่แล้ว')
        else:  # ถ้ามี pk = แก้ไข
            # ตรวจสอบว่าชื่อซ้ำกับร้านอื่นไหม (ไม่รวมตัวเอง)
            if Supplier.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(f'❌ มีซัพพลายเออร์ชื่อ "{name}" อยู่แล้ว')
        
        return name.strip()
    
    def clean_phone(self):
        """
        ตรวจสอบเบอร์โทรศัพท์
        """
        phone = self.cleaned_data.get('phone')
        
        # ถ้าไม่กรอก ให้ผ่านได้ (blank=True)
        if not phone or phone.strip() == '':
            return ''
        
        # ลบช่องว่างและขีด
        phone = phone.replace(' ', '').replace('-', '')
        
        # ตรวจสอบว่าเป็นตัวเลขหรือไม่
        if not phone.replace('+', '').isdigit():
            raise forms.ValidationError('❌ เบอร์โทรต้องเป็นตัวเลขเท่านั้น')
        
        # ตรวจสอบความยาว (เบอร์ไทย 9-10 หลัก)
        if len(phone) < 9 or len(phone) > 13:
            raise forms.ValidationError('❌ เบอร์โทรไม่ถูกต้อง (ควรมี 9-10 หลัก)')
        
        return phone
    
    def clean_address(self):
        """
        ตรวจสอบที่อยู่
        """
        address = self.cleaned_data.get('address')
        
        # ถ้าไม่กรอก ให้ผ่านได้ (blank=True)
        if not address:
            return ''
        
        return address.strip()
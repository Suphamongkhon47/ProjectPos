"""
Custom Template Filters สำหรับ Django
วางไฟล์นี้ใน: products/templatetags/custom_filters.py
"""

from django import template
from decimal import Decimal

register = template.Library()


@register.filter(name='abs')
def abs_value(value):
    """
    แปลงค่าเป็นบวกเสมอ (Absolute Value)
    
    ตัวอย่าง:
        {{ -200|abs }}  → 200
        {{ 100|abs }}   → 100
        {{ -50.5|abs }} → 50.5
    """
    try:
        if value is None:
            return 0
        
        # แปลงเป็น Decimal แล้วใช้ abs
        return abs(Decimal(str(value)))
        
    except (ValueError, TypeError, Exception):
        return 0


@register.filter(name='abs_int')
def abs_int_value(value):
    """
    แปลงค่าเป็นบวก (เลขจำนวนเต็ม)
    
    ตัวอย่าง:
        {{ -200|abs_int }}  → 200
        {{ -50.9|abs_int }} → 50
    """
    try:
        if value is None:
            return 0
        
        return abs(int(float(value)))
        
    except (ValueError, TypeError, Exception):
        return 0


@register.filter(name='abs_float')
def abs_float_value(value):
    """
    แปลงค่าเป็นบวก (ทศนิยม)
    
    ตัวอย่าง:
        {{ -200.50|abs_float }}  → 200.5
        {{ 100.99|abs_float }}   → 100.99
    """
    try:
        if value is None:
            return 0.0
        
        return abs(float(value))
        
    except (ValueError, TypeError, Exception):
        return 0.0
    
@register.filter(name='mul')
def mul(value, arg):
    """
    คูณตัวเลข (Multiplication)
    ตัวอย่าง: {{ quantity|mul:price }}
    """
    try:
        if value is None or arg is None:
            return 0
        # แปลงเป็น Decimal เพื่อความแม่นยำทางบัญชี
        return Decimal(str(value)) * Decimal(str(arg))
    except (ValueError, TypeError, Exception):
        return 0
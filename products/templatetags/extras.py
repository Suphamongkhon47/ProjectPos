# products/templatetags/extras.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """ใช้เพื่อดึงค่าจาก dict ใน template"""
    if dictionary is None:
        return None
    return dictionary.get(key)
from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    ดึงค่าจาก dict ใน Django template
    
    Usage: {{ my_dict|get_item:"key" }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter(name='get_price')
def get_price(product, tier_code):
    """
    ดึงราคาจาก ProductPrice ตาม PriceTier code
    
    Usage: {{ product|get_price:"T1" }}
    """
    try:
        from products.models import ProductPrice
        price_obj = ProductPrice.objects.filter(
            product=product,
            price_tier__code=tier_code,
            is_active=True
        ).first()
        
        return price_obj.price if price_obj else None
    except Exception:
        return None
    
# ===================================
# วิธีใช้ใน Template:
# 
# 1. โหลด filters:
#    {% load product_filters %}
# 
# 2. ใช้งาน get_item (สำหรับ dict):
#    {{ product.price_dict|get_item:tier.code }}
# 
# 3. ใช้งาน get_price (Query จาก DB):
#    {{ product|get_price:tier.code }}
# ===================================
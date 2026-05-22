# products/services/product_service.py

from typing import List, Optional
from collections import Counter
from django.db.models import Q, QuerySet

from products.models import Product


class ProductService:
    """
    Service: Business Logic สำหรับสินค้า
    ไม่มี Database Structure - แค่ Logic การทำงาน
    """
    
    @staticmethod
    def get_popular_models(limit: int = 20) -> List[str]:
        """
        ดึงรุ่นรถยอดนิยม
        
        Args:
            limit: จำนวนที่ต้องการ (default: 20)
            
        Returns:
            List รุ่นรถที่ใช้บ่อย
        """
        all_models = []
        
        # ดึงข้อมูล
        products = Product.objects.exclude(compatible_models__isnull=True
        ).exclude(
            compatible_models=''
        ).values_list('compatible_models', flat=True)
        
        # แยกแต่ละรุ่น
        for compatible in products:
            models = [
                m.strip().title() 
                for m in compatible.split(',') 
                if m.strip()
            ]
            all_models.extend(models)
        
        # นับความถี่
        counter = Counter(all_models)
        
        return [model for model, count in counter.most_common(limit)]
    
    @staticmethod
    def get_compatible_models_list(product: Product) -> List[str]:
        """
        แปลง compatible_models จาก String เป็น List
        
        Args:
            product: Product instance
            
        Returns:
            List ของรุ่นรถ
        """
        if not product.compatible_models:
            return []
        
        return [
            m.strip() 
            for m in product.compatible_models.split(',')
            if m.strip()
        ]
    
    @staticmethod
    def is_compatible_with(product: Product, model_name: str) -> bool:
        """
        เช็คว่าสินค้านี้ใช้กับรุ่นรถที่ระบุได้หรือไม่
        
        Args:
            product: Product instance
            model_name: ชื่อรุ่นรถ
            
        Returns:
            True ถ้าใช้ได้, False ถ้าใช้ไม่ได้
        """
        if not product.compatible_models:
            return False
        
        models = ProductService.get_compatible_models_list(product)
        return model_name.lower() in [m.lower() for m in models]
    
    @staticmethod
    def search_by_model(model_name: str) -> QuerySet:
        """
        ค้นหาสินค้าตามรุ่นรถ
        
        Args:
            model_name: ชื่อรุ่นรถ
            
        Returns:
            QuerySet ของสินค้า
        """
        return Product.objects.filter(
            compatible_models__icontains=model_name,
            is_active=True
        )
    
    @staticmethod
    def search_products(
        product_query: Optional[str] = None,
        model_query: Optional[str] = None,
        limit: int = 50
    ) -> QuerySet:
        """
        ค้นหาสินค้าตามชื่อและรุ่นรถ
        
        Args:
            product_query: คำค้นหาชื่อสินค้า/SKU
            model_query: คำค้นหารุ่นรถ
            limit: จำกัดจำนวนผลลัพธ์
            
        Returns:
            QuerySet ของสินค้า
        """
        products = Product.objects.filter(is_active=True)
        
        # กรองตามชื่อสินค้า
        if product_query:
            products = products.filter(
                Q(name__icontains=product_query) |
                Q(sku__icontains=product_query) |
                Q(description__icontains=product_query)
            )
        
        # กรองตามรุ่นรถ
        if model_query:
            products = products.filter(
                compatible_models__icontains=model_query
            )
        
        return products.select_related('category')[:limit]
    
    @staticmethod
    def get_stock_status(product):
        quantity = 0
        
        # ✅ 1. ถ้าเป็น Bundle คำนวณจากลูกที่น้อยที่สุด
        if product.is_bundle:
            components = product.bundle_components.all()
            if components.exists():
                min_qty = float('inf')
                for comp in components:
                    comp_qty = float(comp.quantity or 0)
                    if comp_qty < min_qty:
                        min_qty = comp_qty
                quantity = min_qty if min_qty != float('inf') else 0
            else:
                quantity = 0
        else:
            # ✅ 2. สินค้าปกติ
            quantity = float(product.quantity or 0)
            
        status = 'in_stock'
        text = 'มีสินค้า'
        badge = 'success'
        
        if quantity <= 0:
            status = 'out_of_stock'
            text = 'สินค้าหมด'
            badge = 'error'
        elif quantity <= (product.min_stock or 5):
            status = 'low_stock'
            text = 'สินค้าใกล้หมด'
            badge = 'warning'
            
        return {
            'quantity': quantity,
            'status': status,
            'label': text,
            'color': badge
        }
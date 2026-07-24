from django.core.management.base import BaseCommand
from django.db.models import Sum
from products.models import Product, StockMovement


class Command(BaseCommand):
    help = 'อัพเดทสต็อกสินค้าจาก StockMovement'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.WARNING("🔄 กำลังอัพเดทสต็อกสินค้า..."))
        self.stdout.write("=" * 60)
        
        products = Product.objects.all()
        total_count = products.count()
        updated_count = 0
        unchanged_count = 0
        
        for idx, product in enumerate(products, 1):
            # คำนวณสต็อก
            movements = StockMovement.objects.filter(product=product)
            total_in = movements.filter(movement_type='IN').aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            total_out = movements.filter(movement_type='OUT').aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            new_stock = total_in - total_out
            old_stock = product.stock_quantity if hasattr(product, 'stock_quantity') else 0
            
            # อัพเดท
            if old_stock != new_stock:
                product.stock_quantity = new_stock
                product.save(update_fields=['stock_quantity'])
                updated_count += 1
                
                self.stdout.write(
                    f"  [{idx}/{total_count}] ✅ {product.sku:20s} | "
                    f"เดิม: {old_stock:>8.2f} → ใหม่: {new_stock:>8.2f}"
                )
            else:
                unchanged_count += 1
                if options.get('verbosity', 1) >= 2:
                    self.stdout.write(
                        f"  [{idx}/{total_count}] ⏭️  {product.sku:20s} | "
                        f"ไม่เปลี่ยนแปลง: {old_stock:>8.2f}"
                    )
        
        # สรุปผล
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ อัพเดทสต็อกเสร็จสิ้น"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"📊 สินค้าทั้งหมด:      {total_count:>5} รายการ")
        self.stdout.write(self.style.SUCCESS(f"✅ อัพเดทแล้ว:        {updated_count:>5} รายการ"))
        self.stdout.write(f"⏭️  ไม่เปลี่ยนแปลง:    {unchanged_count:>5} รายการ")
        self.stdout.write("=" * 60)
        
        if updated_count == 0:
            self.stdout.write(self.style.WARNING("ℹ️  ไม่มีรายการที่ต้องอัพเดท"))
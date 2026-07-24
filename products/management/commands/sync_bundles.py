from django.core.management.base import BaseCommand
from django.db import transaction
from products.models import Product

class Command(BaseCommand):
    help = 'จับคู่สินค้า Bundle จาก bundle_group ลง bundle_components'

    def handle(self, *args, **kwargs):
        self.stdout.write("⏳ กำลังเริ่มตรวจสอบและจับคู่สินค้า...")

        # 1. หาสินค้าที่เป็นตัวแม่ (เฉพาะประเภทชุด L-R หรือ F-R เท่านั้น)
        # และต้องมีรหัสกลุ่ม (bundle_group)
        bundles = Product.objects.filter(
            bundle_type__in=['L-R', 'F-R']
        ).exclude(bundle_group__isnull=True).exclude(bundle_group='')
        
        updated_count = 0

        for parent in bundles:
            group = parent.bundle_group
            
            # 2. หาตัวลูก (L หรือ R) ที่อยู่ในกลุ่มเดียวกัน
            # ⭐ Safety Check:
            # - ต้องไม่ใช่ตัวมันเอง (parent.id)
            # - ต้องไม่ใช่สินค้าประเภทชุด (L-R) ตัวอื่น (ป้องกันแม่จับแม่เป็นลูก)
            children = Product.objects.filter(
                bundle_group=group
            ).exclude(
                id=parent.id
            ).exclude(
                bundle_type__in=['L-R', 'F-R']
            )
            
            if children.exists():
                with transaction.atomic():
                    # 3. บันทึกลง ManyToMany (ทับของเดิม)
                    parent.bundle_components.set(children)
                    
                    # 4. บังคับเปิด is_bundle เป็น True
                    parent.is_bundle = True
                    parent.save(update_fields=['is_bundle'])
                
                names = ", ".join([f"{c.sku}({c.bundle_type})" for c in children])
                self.stdout.write(self.style.SUCCESS(f'✅ [{group}] จับคู่แม่ {parent.sku} -> ลูก: [{names}]'))
                updated_count += 1
            else:
                self.stdout.write(self.style.WARNING(f'⚠️ [{group}] {parent.sku} ไม่พบสินค้าลูกในกลุ่ม (ข้าม)'))

        self.stdout.write(self.style.SUCCESS(f'\n✨ ดำเนินการเสร็จสิ้น! จับคู่สำเร็จทั้งหมด {updated_count} รายการ'))
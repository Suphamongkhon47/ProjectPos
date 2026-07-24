"""
Django Management Command สำหรับเติมข้อมูลหมวดหมู่

วิธีใช้งาน:
    python manage.py seed_categories
"""

from django.core.management.base import BaseCommand
from products.models import Category


class Command(BaseCommand):
    help = 'เติมข้อมูลหมวดหมู่ 8 หมวดเริ่มต้น'

    def handle(self, *args, **options):
        categories = [
            {
                'name': 'ระบบเครื่องยนต์',
                'name_en': 'Engine System',
                'code': 'ENG',
                'description': 'เครื่องยนต์ เกียร์ คลัช ไอเสีย ระบายความร้อน เชื้อเพลิง'
            },
            {
                'name': 'ช่วงล่าง',
                'name_en': 'Suspension',
                'code': 'SUS',
                'description': 'โช้คอัพ ลูกหมาก พวงมาลัย ล้อยาง'
            },
            {
                'name': 'ระบบเบรก',
                'name_en': 'Brake System',
                'code': 'BRK',
                'description': 'ผ้าเบรก จานเบรก แม่ปั๊มเบรก'
            },
            {
                'name': 'ระบบไฟฟ้า',
                'name_en': 'Electrical System',
                'code': 'ELE',
                'description': 'แบตเตอรี่ หลอดไฟ ไดชาร์จ ไดสตาร์ท เซนเซอร์'
            },
            {
                'name': 'ตัวถัง',
                'name_en': 'Body Parts',
                'code': 'BDY',
                'description': 'กันชน กระจก ใบปัดน้ำฝน ประตู'
            },
            {
                'name': 'ภายในรถ',
                'name_en': 'Interior',
                'code': 'INT',
                'description': 'พรมปูพื้น ผ้าหุ้มเบาะ อุปกรณ์ตกแต่ง'
            },
            {
                'name': 'น้ำมันเคมีภัณฑ์',
                'name_en': 'Fluids & Chemicals',
                'code': 'FLD',
                'description': 'น้ำมันเครื่อง น้ำมันเกียร์ น้ำยาต่างๆ จารบี'
            },
            {
                'name': 'เครื่องมือ',
                'name_en': 'Tools',
                'code': 'TOL',
                'description': 'ประแจ ไขควง แม่แรง อุปกรณ์ซ่อม'
            }
        ]

        created_count = 0
        skipped_count = 0

        for cat_data in categories:
            category, created = Category.objects.get_or_create(
                code=cat_data['code'],
                defaults={
                    'name': cat_data['name'],
                    'name_en': cat_data['name_en'],
                    'description': cat_data['description']
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✅ สร้าง: {category.code} - {category.name}')
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'⚠️  มีอยู่แล้ว: {category.code} - {category.name}')
                )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'📊 สรุป: สร้างใหม่ {created_count} หมวด, มีอยู่แล้ว {skipped_count} หมวด'))

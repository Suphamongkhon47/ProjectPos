"""
Payment Service: จัดการ Payment และ QR Code PromptPay
Pure Python - ไม่ต้อง Compile
"""

import qrcode
import base64
from io import BytesIO
from decimal import Decimal
from django.db import transaction
from django.conf import settings  # ← เพิ่มบรรทัดนี้
from products.models import Payment


# ===================================
# 1. CRC16 Calculation
# ===================================

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
        crc &= 0xFFFF
    return crc


# ===================================
# 2. PromptPay Payload Generation
# ===================================

def create_promptpay_payload(identifier, amount=None):
    """
    สร้าง PromptPay Payload (EMV QR Code)
    
    Args:
        identifier: เบอร์มือถือ (66xxxxxxxx) หรือ เลขบัตรประชาชน
        amount: จำนวนเงิน (float)
    
    Returns:
        str: Payload String
    """
    
    # 1. เริ่มต้นโครงสร้าง
    payload = "000201" 
    payload += "010212" if amount else "010211" # 12=มียอดเงิน, 11=ไม่มี
    
    # 2. ข้อมูลร้านค้า (Tag 29)
    # -------------------------------------------------------
    merchant_id = "0016A000000677010111" # AID ของ PromptPay
    
    identifier = str(identifier).strip().replace('-', '')
    
    # เช็คว่าเป็นเบอร์โทร หรือ บัตรประชาชน
    if len(identifier) == 10 and identifier.startswith('0'):
        # เบอร์โทร: เปลี่ยน 08x -> 00668x
        formatted_id = f"0066{identifier[1:]}"
        # Tag 01 คือ เบอร์มือถือ
        merchant_id += f"01{len(formatted_id):02d}{formatted_id}"
        
    elif len(identifier) == 13:
        # บัตรประชาชน
        # Tag 02 คือ เลขบัตรปชช.
        merchant_id += f"02{len(identifier):02d}{identifier}"
        
    else:
        # กรณี E-Wallet (Tag 03) หรืออื่นๆ
        merchant_id += f"03{len(identifier):02d}{identifier}"
        
    # เอาใส่ Tag 29
    payload += f"29{len(merchant_id):02d}{merchant_id}"
    # -------------------------------------------------------
    
    # 3. สกุลเงินและประเทศ
    payload += "5303764" # 764 = THB
    payload += "5802TH"
    
    # 4. ยอดเงิน (Tag 54)
    if amount and float(amount) > 0:
        amount_str = f"{float(amount):.2f}"
        payload += f"54{len(amount_str):02d}{amount_str}"
    
    # 5. ปิดท้ายด้วย Checksum (Tag 63)
    payload += "6304"
    
    # คำนวณ CRC
    crc = crc16_ccitt(payload.encode())
    payload += f"{crc:04X}" # แปลงเป็นฐาน 16 ตัวพิมพ์ใหญ่ (เช่น A1B2)
    
    return payload


# ===================================
# 3. QR Code Generation
# ===================================

def generate_promptpay_qr(phone_number, amount, reference=''):
    """
    สร้าง QR Code PromptPay (เบอร์มือถือ)
    
    Args:
        phone_number: เบอร์มือถือ (เช่น '0812345678')
        amount: จำนวนเงิน
        reference: เลขที่อ้างอิง
    
    Returns:
        str: Base64 Image (data:image/png;base64,...)
    """
    
    try:
        # สร้าง Payload
        payload = create_promptpay_payload(
            identifier=phone_number,
            amount=float(amount) if amount else None
        )
        
        # สร้าง QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # แปลงเป็น Base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_base64}"
        
    except Exception as e:
        raise ValueError(f"ไม่สามารถสร้าง QR Code ได้: {str(e)}")


# ===================================
# 4. Payment Management
# ===================================

class PaymentService:
    """Service สำหรับจัดการ Payment"""
    
    @staticmethod
    def create_payment(sale, method='cash', received=None, note=''):
        """
        สร้างการชำระเงิน
        
        Args:
            sale: Sale object
            method: 'cash', 'qr', 'transfer'
            received: เงินที่รับ (Decimal) - สำหรับเงินสด
            note: หมายเหตุ
        
        Returns:
            Payment object
        """
        amount = sale.grand_total
        received_val = Decimal(str(received)) if (method == 'cash' and received is not None) else amount
        change_val = received_val - amount if received_val > amount else Decimal('0.00')
        
        if hasattr(sale, 'payment'):
            # มี Payment แล้ว → อัปเดต
            payment = sale.payment
            payment.method = method
            payment.amount = amount
            payment.received = received_val
            payment.note = note
            payment.status = 'confirmed'
            payment.save()
            return payment
        
        # สร้างใหม่
        payment = Payment.objects.create(
            transaction=sale,
            method=method,
            amount=amount,
            received=received_val,
            change=change_val,
            note=note,
            status='confirmed'
        )
        return payment
    
    @staticmethod
    def generate_qr_image(amount, reference=''):
        """
        สร้างรูป QR Code (Base64)
        
        ✅ ดึงเบอร์จาก Settings แทนการ Hardcode
        """
        try:
            # ✅ ดึงเบอร์จาก Settings
            SHOP_PROMPTPAY_ID = getattr(settings, 'PROMPTPAY_PHONE', '0834755649')
            
            # 1. สร้างรหัส Text
            payload = create_promptpay_payload(SHOP_PROMPTPAY_ID, float(amount))
            
            # 2. แปลง Text เป็นรูป QR
            qr = qrcode.QRCode(box_size=10, border=4)
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # 3. แปลงรูปเป็น Base64 ส่งกลับไปหน้าเว็บ
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/png;base64,{img_str}"
            
        except Exception as e:
            print(f"QR Error: {e}")
            return None
    
    @staticmethod
    def confirm_payment(payment):
        """ยืนยันการชำระเงิน"""
        if payment.status == 'confirmed':
            return payment
        
        if payment.status == 'void':
            raise ValueError("ไม่สามารถยืนยันการชำระเงินที่ยกเลิกแล้ว")
        
        with transaction.atomic():
            payment.status = 'confirmed'
            payment.save(update_fields=['status'])
        
        return payment
    
    @staticmethod
    def void_payment(payment):
        """ยกเลิกการชำระเงิน"""
        if payment.status == 'confirmed':
            raise ValueError("ไม่สามารถยกเลิกการชำระเงินที่ยืนยันแล้ว")
        
        with transaction.atomic():
            payment.status = 'void'
            payment.save(update_fields=['status'])
        
        return payment
    
    @staticmethod
    def validate_payment(payment):
        """ตรวจสอบความถูกต้องของ Payment"""
        errors = []
        
        if payment.amount <= 0:
            errors.append("จำนวนเงินต้องมากกว่า 0")
        
        if payment.method == 'cash':
            if payment.received < payment.amount:
                errors.append(
                    f"เงินที่รับไม่พอ (ต้องการ {payment.amount:.2f}, รับ {payment.received:.2f})"
                )
        
        if payment.method == 'qr' and not payment.note:
            errors.append("กรุณาระบุข้อมูลการโอน QR Code")
        
        if payment.method == 'transfer' and not payment.note:
            errors.append("กรุณาระบุข้อมูลการโอนเงิน")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def get_payment_summary(sale):
        """สรุปข้อมูลการชำระเงิน"""
        if not hasattr(sale, 'payment'):
            return {
                'has_payment': False,
                'method': None,
                'amount': 0,
                'status': None,
            }
        
        payment = sale.payment
        
        return {
            'has_payment': True,
            'method': payment.get_method_display(),
            'amount': float(payment.amount),
            'received': float(payment.received) if payment.method == 'cash' else float(payment.amount),
            'change': float(payment.change) if payment.method == 'cash' else 0,
            'status': payment.get_status_display(),
            'note': payment.note,
        }


# ===================================
# 5. Helper Functions
# ===================================

def format_payment_method(method):
    """แปลง Payment Method เป็นข้อความแสดง"""
    method_map = {
        'cash': '💵 เงินสด',
        'qr': '📱 QR Code',
        'transfer': '🏦 โอนเงิน',
    }
    return method_map.get(method, method)


def calculate_change(received, amount):
    """คำนวณเงินทอน"""
    return Decimal(str(received)) - Decimal(str(amount))
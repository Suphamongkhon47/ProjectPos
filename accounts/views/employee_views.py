"""
Employee Management Views
accounts/views.py (หรือชื่อไฟล์ที่คุณตั้งไว้)
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from accounts.models import Employee

@login_required
def employee_list(request):
    """รายชื่อพนักงานทั้งหมด"""
    
    # ถ้าไม่ใช่เจ้าของร้าน ให้เด้งไปหน้าแก้ไขข้อมูลตัวเอง
    if not request.user.is_superuser:
        messages.info(request, "คุณสามารถแก้ไขข้อมูลของตัวเองได้")
        # เช็คว่ามี profile ไหมเพื่อป้องกัน Error
        if hasattr(request.user, 'profile'):
            return redirect('employee_edit', pk=request.user.profile.id)
        else:
            return redirect('/')
    
    # รับค่าค้นหา
    search = request.GET.get('search', '')
    
    # Query ข้อมูล (ดึง User มาด้วยเพื่อลด Query Database)
    employees = Employee.objects.select_related('user').all()
    
    # กรองตาม ID ที่เลือกจาก Dropdown
    if search:
        employees = employees.filter(id=search)
    
    # เรียงลำดับ: เจ้าของร้าน (Superuser) ขึ้นก่อน, แล้วค่อยเรียงตามชื่อเล่น
    # (Django order_by boolean: False มาก่อน True, เราเลยใส่ - เพื่อให้ True มาก่อน)
    employees = employees.order_by('-user__is_superuser', 'nickname')
    
    # --- คำนวณสถิติ (ปรับใหม่ตาม Logic: Owner vs Employee) ---
    total_count = Employee.objects.count()
    owner_count = Employee.objects.filter(user__is_superuser=True).count()   # เจ้าของ
    staff_count = Employee.objects.filter(user__is_superuser=False).count()  # พนักงาน
    
    # Pagination (แบ่งหน้าละ 20 คน)
    paginator = Paginator(employees, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # รายชื่อทั้งหมดสำหรับใส่ใน Dropdown ค้นหา
    all_employees = Employee.objects.select_related('user').order_by('nickname')
    
    context = {
        'employees': page_obj,
        'search': search,
        'total_count': total_count,
        'manager_count': owner_count,  # ใช้ตัวแปรเดิมใน HTML แต่ค่าคือ Owner Count
        'staff_count': staff_count,    # ใช้ตัวแปรเดิมใน HTML แต่ค่าคือ Staff Count
        'all_employees': all_employees,
    }
    
    return render(request, 'accounts/employees/employee_list.html', context)


@login_required
def employee_add(request):
    """เพิ่มพนักงานใหม่ (Default = Manager/พนักงาน)"""
    
    # ตรวจสอบสิทธิ์: เฉพาะ Superuser
    if not request.user.is_superuser:
        messages.error(request, "คุณไม่มีสิทธิ์เพิ่มพนักงาน")
        return redirect('employee_list')
    
    if request.method == 'POST':
        # รับค่าจาก Form
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        nickname = request.POST.get('nickname', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        avatar_file = request.FILES.get('avatar')
        
        # Validate ข้อมูล
        errors = []
        if not username: errors.append("กรุณาระบุ Username")
        elif User.objects.filter(username=username).exists(): errors.append("Username นี้ถูกใช้แล้ว")
        
        if not password: errors.append("กรุณาระบุรหัสผ่าน")
        elif len(password) < 4: errors.append("รหัสผ่านต้องมีอย่างน้อย 4 ตัวอักษร")
        elif password != confirm_password: errors.append("รหัสผ่านไม่ตรงกัน")
        
        if not first_name: errors.append("กรุณาระบุชื่อ")
        if not nickname: errors.append("กรุณาระบุชื่อเล่น")
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/employees/employee_form.html', {
                'form_data': request.POST, 'is_edit': False
            })
        
        # 1. สร้าง User (Django Auth)
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        # ตั้งเป็นพนักงาน (is_staff = True)
        user.is_staff = True
        user.save()
        
        # 2. สร้าง/อัปเดต Employee Profile
        # (ปกติ Signal จะ create ให้แล้ว แต่เรา safe ไว้ check อีกที)
        if hasattr(user, 'profile'):
            employee = user.profile
        else:
            employee = Employee.objects.create(user=user)
            
        employee.nickname = nickname
        employee.phone = phone
        employee.address = address
        employee.position = 'STAFF'  # บังคับเป็น STAFF (พนักงาน)
        
        if avatar_file:
            employee.set_avatar_from_file(avatar_file)
        
        employee.save()
        
        messages.success(request, f"✅ เพิ่มพนักงาน {nickname} เรียบร้อย")
        return redirect('employee_list')
    
    # GET Request
    return render(request, 'accounts/employees/employee_form.html', {
        'form_data': {}, 'is_edit': False
    })


@login_required
def employee_edit(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    
    # Check Permission
    if not request.user.is_superuser:
        if employee.user != request.user:
            messages.error(request, "คุณไม่มีสิทธิ์แก้ไขข้อมูลคนอื่น")
            return redirect('employee_list')
    
    if request.method == 'POST':
        # 1. จัดการ Role (Superuser Only)
        if request.user.is_superuser:
            role_selection = request.POST.get('role_selection')
            user_obj = employee.user
            if role_selection == 'OWNER':
                user_obj.is_superuser = True
                user_obj.is_staff = True
            elif role_selection == 'EMPLOYEE':
                if user_obj == request.user:
                    messages.warning(request, "⚠️ ไม่สามารถปลดสิทธิ์ตัวเองได้")
                else:
                    user_obj.is_superuser = False
                    user_obj.is_staff = False
            user_obj.save()

        # 2. ข้อมูลทั่วไป
        user = employee.user
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        
        # 3. เปลี่ยนรหัสผ่าน (ถ้าติ๊ก)
        change_pass = request.POST.get('change_password') == 'on'
        new_pass = request.POST.get('new_password')
        confirm_pass = request.POST.get('confirm_password')
        
        if change_pass and new_pass:
            if new_pass != confirm_pass:
                messages.error(request, "❌ รหัสผ่านใหม่ไม่ตรงกัน")
                return redirect('employee_edit', pk=pk)
            user.set_password(new_pass) # เปลี่ยนรหัสทันที
            messages.success(request, "🔐 เปลี่ยนรหัสผ่านเรียบร้อย")
            
        user.save()

        # 4. ข้อมูล Employee & รูปภาพ
        employee.nickname = request.POST.get('nickname', '').strip()
        employee.phone = request.POST.get('phone', '').strip()
        employee.address = request.POST.get('address', '').strip()
        
        # ✅ รับไฟล์รูปภาพ
        avatar_file = request.FILES.get('avatar')
        if avatar_file:
            employee.set_avatar_from_file(avatar_file)
            
        employee.save()
        
        messages.success(request, f"✅ บันทึกข้อมูล {employee.nickname} เรียบร้อย")
        if request.user.is_superuser:
            return redirect('employee_list')
        else:
            return redirect('employee_edit', pk=pk)

    # GET Request
    context = {
        'employee': employee,
        'is_edit': True,
        'form_data': {
            'first_name': employee.user.first_name,
            'last_name': employee.user.last_name,
            'nickname': employee.nickname,
            'phone': employee.phone,
            'address': employee.address,
            'avatar': employee.avatar, # ส่งรูปไปโชว์
        }
    }
    return render(request, 'accounts/employees/employee_form.html', context)


@login_required
def employee_delete(request, pk):
    """ลบพนักงาน (เฉพาะ Superuser)"""
    
    if not request.user.is_superuser:
        messages.error(request, "คุณไม่มีสิทธิ์ลบพนักงาน")
        return redirect('employee_list')
    
    employee = get_object_or_404(Employee, pk=pk)
    
    # ห้ามลบตัวเอง
    if employee.user == request.user:
        messages.error(request, "ไม่สามารถลบตัวเองได้")
        return redirect('employee_list')
    
    if request.method == 'POST':
        name = f"{employee.nickname}"
        # ลบ User -> Cascade จะลบ Employee ให้เอง
        employee.user.delete()
        messages.success(request, f"🗑️ ลบพนักงาน {name} เรียบร้อย")
        return redirect('employee_list')
    
    return render(request, 'accounts/employees/employee_delete.html', {'employee': employee})
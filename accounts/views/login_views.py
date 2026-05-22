# ===================================
# ไฟล์: accounts/views.py
# ===================================

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages


# ===================================
# Login
# ===================================
def login_view(request):
    """หน้าเข้าสู่ระบบ"""
    # ถ้า login แล้ว redirect ไป POS
    if request.user.is_authenticated:
        return redirect('home_dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        # ตรวจสอบ
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Login สำเร็จ
            login(request, user)
            # Redirect ไปหน้าที่ต้องการ (หรือหน้าที่เคยอยู่ก่อน login)
            next_url = request.GET.get('next') or 'home_dashboard'
            return redirect(next_url)
        else:
            # Login ไม่สำเร็จ
            messages.error(request, 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
    return render(request, 'accounts/login.html')


# ===================================
# Logout
# ===================================
@login_required
def logout_view(request):
    """ออกจากระบบ"""
    
    logout(request)
    messages.success(request, 'ออกจากระบบสำเร็จ')
    return redirect('login')



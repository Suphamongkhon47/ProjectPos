from django.conf.urls.static import static
from django.urls import path
import os
from .views import( login_views,employee_views)
from pos_system import settings
from . import views




urlpatterns = [
    # Login/Logout
    path('login/', login_views.login_view, name='login'),
    path('logout/', login_views.logout_view, name='logout'),
      
    path('employees/', employee_views.employee_list, name='employee_list'),
    path('employees/add/', employee_views.employee_add, name='employee_add'),
    path('employees/<int:pk>/edit/', employee_views.employee_edit, name='employee_edit'),
    path('employees/<int:pk>/delete/', employee_views.employee_delete, name='employee_delete'),
]


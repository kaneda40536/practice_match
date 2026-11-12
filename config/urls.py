from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('schools/', include('schools.urls')), 
    path('facilities/', include('facilities.urls')),
    path('matching/', include('matching.urls')), 
    path('', lambda request: redirect('login')),  # ★ 'accounts:login' から 'login' に変更！
]
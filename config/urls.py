from django.contrib import admin
from django.urls import path, include
from accounts.views import EntryView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('schools/', include('schools.urls')), 
    path('facilities/', include('facilities.urls')),
    path('matching/', include('matching.urls')), 
    path('', EntryView.as_view(), name='entry'),   # 最初の画面（アカウントIDの入力）
]
from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.custom_logout_view, name='logout'),
    path('board/home/', views.BoardHomeView.as_view(), name='board_home'),
    path('teacher/home/', views.TeacherHomeView.as_view(), name='teacher_home'),

    # 学校アカウント管理
    path('board/school-accounts/', views.SchoolAccountListView.as_view(), name='school_account_list'),
    path('board/school-accounts/add/', views.SchoolAccountCreateView.as_view(), name='school_account_add'),
    path('board/school-accounts/<int:pk>/password/', views.SchoolAccountPasswordView.as_view(), name='school_account_password'),
    path('board/school-accounts/<int:pk>/toggle/', views.SchoolAccountToggleView.as_view(), name='school_account_toggle'),
]
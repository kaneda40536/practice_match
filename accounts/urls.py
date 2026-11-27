from django.urls import path
from . import views

urlpatterns = [
    # ログイン・新規登録
    path('login/', views.ClubLoginView.as_view(), name='login'),
    path('login/board/', views.BoardLoginView.as_view(), name='board_login'),
    path('login/advisor/', views.AdvisorLoginView.as_view(), name='advisor_login'),
    path('register/advisor/', views.AdvisorRegisterView.as_view(), name='advisor_register'),
    path('register/club/', views.ClubAccountRegisterView.as_view(), name='club_account_register'),
    path('logout/', views.custom_logout_view, name='logout'),

    # ホーム
    path('board/home/', views.BoardHomeView.as_view(), name='board_home'),
    path('teacher/home/', views.TeacherHomeView.as_view(), name='teacher_home'),
    path('advisor/home/', views.AdvisorHomeView.as_view(), name='advisor_home'),

    # 管理者アカウントの作成（教育委員会）
    path('board/admin-accounts/add/', views.AdminAccountCreateView.as_view(), name='admin_account_create'),

    # 学校アカウント管理（教育委員会）
    path('board/school-accounts/', views.SchoolAccountListView.as_view(), name='school_account_list'),
    path('board/school-accounts/add/', views.SchoolAccountFormView.as_view(), name='school_account_add'),
    path('board/school-accounts/<int:pk>/edit/', views.SchoolAccountFormView.as_view(), name='school_account_edit'),
    path('board/school-accounts/<int:pk>/toggle/', views.SchoolAccountToggleView.as_view(), name='school_account_toggle'),
    path('board/school-accounts/<int:pk>/delete/', views.SchoolAccountDeleteView.as_view(), name='school_account_delete'),
]

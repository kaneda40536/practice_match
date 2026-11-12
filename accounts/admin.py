from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("追加情報", {"fields": ("role", "school")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("追加情報", {"fields": ("role", "school")}),
    )
    list_display = ("username", "role", "school", "is_active")
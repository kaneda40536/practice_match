from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from schools.forms import ADDRESS_HELP, SchoolLocationMixin
from schools.models import School
from .models import User


class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(label="学校ID")

    error_messages = {
        "invalid_login": "学校IDまたはパスワードが正しくありません。",
        "inactive": "このアカウントは無効です。",
    }


class SchoolAccountCreateForm(SchoolLocationMixin, forms.ModelForm):
    """学校（School）と、その学校のログインアカウント（User）を同時に作るフォーム"""

    username = forms.CharField(
        label="学校ID",
        max_length=150,
        help_text="ログイン時に入力するIDです。半角英数字で入力してください。",
    )
    password1 = forms.CharField(label="パスワード", widget=forms.PasswordInput)
    password2 = forms.CharField(label="パスワード（確認）", widget=forms.PasswordInput)

    class Meta:
        model = School
        fields = ["name", "area", "address"]
        help_texts = {"address": ADDRESS_HELP}

    def clean_name(self):
        name = self.cleaned_data["name"]
        if School.objects.filter(name=name).exists():
            raise forms.ValidationError("同じ名前の学校がすでに登録されています。")
        return name

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("この学校IDはすでに使われています。")
        return username

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2:
            if password1 != password2:
                self.add_error("password2", "パスワードが一致しません。")
            else:
                try:
                    validate_password(password1)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        school = super().save()
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password1"],
            role=User.Role.TEACHER,
            school=school,
        )
        return user
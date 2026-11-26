from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from config.form_messages import RequiredMessageMixin
from schools.forms import ADDRESS_HELP, SchoolCreateForm
from schools.models import Club, School, Sport
from .models import User


class ClubLoginForm(RequiredMessageMixin, forms.Form):
    """部活動アカウントのログイン（学校ID＋部活動ID＋パスワード）

    LoginView から使えるように、AuthenticationForm と同じ形（request を受け取り、
    get_user() でログインするユーザーを返す）にしている。
    """

    school_code = forms.CharField(label="学校ID", max_length=30)
    club_code = forms.CharField(label="部活動ID", max_length=30)
    password = forms.CharField(label="パスワード", strip=False, widget=forms.PasswordInput)

    error_messages = {
        "invalid_login": "学校ID・部活動ID・パスワードのいずれかが正しくありません。",
        "inactive": "このアカウントは無効です。",
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        school_code = self.cleaned_data.get("school_code", "").strip()
        club_code = self.cleaned_data.get("club_code", "").strip()
        password = self.cleaned_data.get("password")
        if school_code and club_code and password:
            account = User.objects.filter(
                role=User.Role.TEACHER,
                club__school__code=school_code, club__code=club_code,
            ).first()
            # アカウントが見つからなくてもパスワードの確認は行う（かかる時間で有無が分からないように）
            self.user_cache = authenticate(
                self.request, username=account.username if account else "", password=password)
            if self.user_cache is None:
                raise forms.ValidationError(self.error_messages["invalid_login"], code="invalid_login")
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class BoardLoginForm(RequiredMessageMixin, AuthenticationForm):
    """教育委員会（管理者）のログイン。部活動アカウントではログインできない"""

    username = forms.CharField(label="管理者ID")

    error_messages = {
        "invalid_login": "管理者IDまたはパスワードが正しくありません。",
        "inactive": "このアカウントは無効です。",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_superuser or user.role == User.Role.BOARD):
            raise forms.ValidationError(self.error_messages["invalid_login"], code="invalid_login")


def validate_new_password(form, user=None):
    """password1 と password2 が一致し、パスワードの決まりを満たしているかを確かめる"""
    cleaned = form.cleaned_data
    password1 = cleaned.get("password1")
    password2 = cleaned.get("password2")
    if password1 and password2:
        if password1 != password2:
            form.add_error("password2", "パスワードが一致しません。")
        else:
            try:
                validate_password(password1, user)
            except forms.ValidationError as e:
                form.add_error("password1", e)


class ClubAccountCreateForm(RequiredMessageMixin, forms.ModelForm):
    """教育委員会が、部活動（Club）と、その部活動のログインアカウント（User）を同時に作るフォーム。

    学校は、登録済みの学校から選ぶか、その場で新しい学校（学校名・学校ID・所在地）を登録する。
    """

    new_school_name = forms.CharField(label="新しい学校の学校名", required=False, max_length=100)
    new_school_code = forms.CharField(
        label="新しい学校の学校ID", required=False, max_length=30,
        help_text="ログイン時に入力するIDです。半角英数字で入力してください。")
    new_school_address = forms.CharField(
        label="新しい学校の所在地", required=False, max_length=200, help_text=ADDRESS_HELP)
    password1 = forms.CharField(label="パスワード", widget=forms.PasswordInput)
    password2 = forms.CharField(label="パスワード（確認）", widget=forms.PasswordInput)

    field_order = [
        "school", "new_school_name", "new_school_code", "new_school_address",
        "sport", "gender", "code", "password1", "password2",
    ]

    class Meta:
        model = Club
        fields = ["school", "sport", "gender", "code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_form = None
        self.fields["school"].required = False
        self.fields["school"].queryset = School.objects.order_by("name")
        self.fields["school"].label_from_instance = lambda s: f"{s.name}（学校ID：{s.code}）"
        self.fields["school"].empty_label = "＋ 新しい学校を登録する"
        self.fields["school"].help_text = "登録済みの学校を選ぶか、「新しい学校を登録する」を選んで学校の情報を入力してください。"
        self.fields["sport"].queryset = Sport.objects.order_by("name")
        self.fields["sport"].label_from_instance = lambda s: f"{s.display_icon} {s.name}"
        self.fields["sport"].empty_label = "競技を選択してください"
        self.fields["gender"].choices = [("", "区分を選択してください")] + list(Club.Gender.choices)

    def clean(self):
        cleaned = super().clean()
        school = cleaned.get("school")
        if school is None and "school" not in self.errors:
            self.clean_new_school(cleaned)

        sport = cleaned.get("sport")
        gender = cleaned.get("gender")
        code = cleaned.get("code")
        if school and sport and gender and Club.objects.filter(
                school=school, sport=sport, gender=gender).exists():
            self.add_error(None, "この学校には、同じ競技・区分の部活動がすでに登録されています。")
        if school and code and Club.objects.filter(school=school, code=code).exists():
            self.add_error("code", "この部活動IDは、この学校ですでに使われています。")
        validate_new_password(self)
        return cleaned

    def clean_new_school(self, cleaned):
        """新しい学校の入力を、学校の登録フォームで確かめる（住所から位置も求める）"""
        self.school_form = SchoolCreateForm({
            "name": cleaned.get("new_school_name", ""),
            "code": cleaned.get("new_school_code", ""),
            "address": cleaned.get("new_school_address", ""),
        })
        if not self.school_form.is_valid():
            for name, errors in self.school_form.errors.items():
                self.add_error(f"new_school_{name}" if name != "__all__" else None, errors)

    # 重なりの確認は clean() で分かりやすいメッセージにしているので、Django の確認は行わない
    def validate_unique(self):
        pass

    def validate_constraints(self):
        pass

    @transaction.atomic
    def save(self, commit=True):
        club = super().save(commit=False)
        if self.school_form is not None:
            club.school = self.school_form.save()
        club.save()
        return User.objects.create_user(
            username=User.username_for(club),
            password=self.cleaned_data["password1"],
            role=User.Role.TEACHER,
            club=club,
        )


class ClubPasswordForm(RequiredMessageMixin, SetPasswordForm):
    """教育委員会が、部活動アカウントのパスワードを再設定するフォーム"""

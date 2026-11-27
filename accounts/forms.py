"""ログイン・アカウント登録のフォーム

画面（デザインの HTML）の入力欄の name に合わせて、項目名を付けている。
  入口            ：account_id
  管理者ログイン  ：account_id / password
  学校側ログイン  ：school_id / club_id / password
  顧問ログイン    ：school_id / name / password
  顧問の新規登録  ：school_id / school_password / name / password / password_confirm
  部活動の新規登録：school_id / login_id / password / password_confirm
"""
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password

from config.form_messages import RequiredMessageMixin
from schools.models import Club, Sport, login_code_validator
from .models import User


def check_new_password(form, user=None, name="password", confirm="password_confirm"):
    """パスワードと確認用が一致し、パスワードの決まりを満たしているかを確かめる"""
    password = form.cleaned_data.get(name)
    password_confirm = form.cleaned_data.get(confirm)
    if password and password_confirm:
        if password != password_confirm:
            form.add_error(confirm, "パスワードが一致しません。")
        else:
            try:
                validate_password(password, user)
            except forms.ValidationError as e:
                form.add_error(name, e)


def school_account_for(school_id):
    """学校IDから、学校情報が登録されている学校アカウントを探す（なければ None）"""
    return (
        User.objects.filter(role=User.Role.SCHOOL, username=school_id, school_profile__isnull=False)
        .select_related("school_profile").first()
    )


# ---------- ログイン ----------

class LoginFormBase(RequiredMessageMixin, forms.Form):
    """LoginView から使えるように、AuthenticationForm と同じ形（request を受け取り、
    get_user() でログインするユーザーを返す）にしたログインフォームの土台"""

    password = forms.CharField(label="パスワード", strip=False, widget=forms.PasswordInput)
    invalid_message = "入力内容が正しくありません。"

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def find_account(self, cleaned):
        """入力からログインするアカウントを探す（見つからなければ None）"""
        raise NotImplementedError

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        account = self.find_account(cleaned)
        # アカウントが見つからなくてもパスワードの確認は行う（かかる時間で有無が分からないように）
        user = authenticate(
            self.request, username=account.username if account else "", password=cleaned["password"])
        if user is None or not self.is_allowed(user):
            raise forms.ValidationError(self.invalid_message, code="invalid_login")
        self.user_cache = user
        return cleaned

    def is_allowed(self, user):
        return True

    def get_user(self):
        return self.user_cache


def school_is_active(school):
    """学校アカウントが利用停止なら、その学校の顧問・部活動もログインできない"""
    return school is not None and school.account.is_active


class BoardLoginForm(LoginFormBase):
    """管理者ログイン（管理者ID＋パスワード）"""

    account_id = forms.CharField(label="管理者ID", max_length=150)
    field_order = ["account_id", "password"]
    invalid_message = "管理者IDまたはパスワードが正しくありません。"

    def find_account(self, cleaned):
        return User.objects.filter(username=cleaned["account_id"].strip()).first()

    def is_allowed(self, user):
        return user.is_superuser or user.role == User.Role.BOARD


class ClubLoginForm(LoginFormBase):
    """学校側ログイン（学校ID＋部活ID＋パスワード）。部活動アカウントでログインする"""

    school_id = forms.CharField(label="学校ID", max_length=150)
    club_id = forms.CharField(label="部活ID", max_length=30)
    field_order = ["school_id", "club_id", "password"]
    invalid_message = "学校ID・部活ID・パスワードのいずれかが正しくありません。"

    def find_account(self, cleaned):
        return User.objects.filter(
            role=User.Role.CLUB,
            club__school__account__username=cleaned["school_id"].strip(),
            club__code=cleaned["club_id"].strip(),
        ).first()

    def is_allowed(self, user):
        return school_is_active(user.club.school)


class AdvisorLoginForm(LoginFormBase):
    """顧問ログイン（学校ID＋顧問名＋パスワード）"""

    school_id = forms.CharField(label="学校ID", max_length=150)
    name = forms.CharField(label="顧問名", max_length=100)
    field_order = ["school_id", "name", "password"]
    invalid_message = "学校ID・顧問名・パスワードのいずれかが正しくありません。"

    def find_account(self, cleaned):
        return User.objects.filter(
            role=User.Role.TEACHER,
            school__account__username=cleaned["school_id"].strip(),
            advisor_name=cleaned["name"].strip(),
        ).first()

    def is_allowed(self, user):
        return school_is_active(user.school)


class EntryForm(RequiredMessageMixin, forms.Form):
    """最初の画面：アカウントIDから、管理者ログインと学校側ログインのどちらに進むかを決める"""

    account_id = forms.CharField(label="アカウントID", max_length=150)

    def clean_account_id(self):
        account_id = self.cleaned_data["account_id"].strip()
        user = User.objects.filter(username=account_id).first()
        if user and (user.is_superuser or user.role == User.Role.BOARD):
            self.destination = "board"
        elif school_account_for(account_id):
            self.destination = "school"
        else:
            raise forms.ValidationError("このIDのアカウントは見つかりませんでした。管理者ID、または学校IDを入力してください。")
        return account_id


# ---------- 新規登録（ログインしていない人が使う） ----------

class AdvisorRegisterForm(RequiredMessageMixin, forms.Form):
    """顧問アカウントの新規登録。教育委員会から伝えられた学校IDと学校パスワードで確認する"""

    school_id = forms.CharField(label="学校ID", max_length=150)
    school_password = forms.CharField(label="学校パスワード", strip=False, widget=forms.PasswordInput)
    name = forms.CharField(label="顧問名", max_length=100)
    password = forms.CharField(label="パスワード", strip=False, widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="パスワード（確認）", strip=False, widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        school_id = cleaned.get("school_id", "").strip()
        school_password = cleaned.get("school_password")
        self.school = None
        if school_id and school_password:
            account = school_account_for(school_id)
            if account is None or not account.is_active or not account.check_password(school_password):
                self.add_error(None, "学校IDまたは学校パスワードが正しくありません。")
            else:
                self.school = account.school_profile
        name = cleaned.get("name", "").strip()
        if self.school and name and User.objects.filter(
                role=User.Role.TEACHER, school=self.school, advisor_name=name).exists():
            self.add_error("name", "この顧問名は、この学校ですでに登録されています。")
        check_new_password(self, User(username=name, advisor_name=name))
        return cleaned

    def save(self):
        return User.objects.create_user(
            username=User.new_advisor_username(),
            password=self.cleaned_data["password"],
            role=User.Role.TEACHER,
            school=self.school,
            advisor_name=self.cleaned_data["name"].strip(),
        )


class ClubAccountRegisterForm(RequiredMessageMixin, forms.Form):
    """部活動アカウントの新規登録。顧問が部活動管理で作った（学校ID・部活ID）を、一度だけ登録できる"""

    school_id = forms.CharField(label="学校ID", max_length=150)
    login_id = forms.CharField(label="部活ID", max_length=30)
    password = forms.CharField(label="パスワード", strip=False, widget=forms.PasswordInput)
    password_confirm = forms.CharField(label="パスワード（確認）", strip=False, widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        school_id = cleaned.get("school_id", "").strip()
        login_id = cleaned.get("login_id", "").strip()
        self.club = None
        if school_id and login_id:
            club = Club.objects.filter(
                school__account__username=school_id, code=login_id).select_related("school__account").first()
            if club is None or not club.school.account.is_active:
                self.add_error(None, "学校IDと部活IDの組み合わせが見つかりません。顧問に部活IDを確認してください。")
            elif User.objects.filter(club=club).exists():
                self.add_error(None, "この部活動のアカウントは、すでに登録されています。")
            else:
                self.club = club
        check_new_password(self, User(username=login_id))
        return cleaned

    def save(self):
        return User.objects.create_user(
            username=User.username_for(self.club),
            password=self.cleaned_data["password"],
            role=User.Role.CLUB,
            club=self.club,
        )


# ---------- 管理者が使うフォーム ----------

class AccountIdPasswordForm(RequiredMessageMixin, forms.Form):
    """ID＋パスワード（確認つき）のアカウントを作る・変えるフォームの土台（管理者・学校アカウント）

    account を渡すと編集。編集のときは、パスワードが空欄なら変更しない。
    """

    account_id = forms.CharField(label="ID", max_length=150, validators=[login_code_validator])
    password = forms.CharField(label="パスワード", strip=False, widget=forms.PasswordInput, required=False)
    password_confirm = forms.CharField(
        label="パスワード（確認）", strip=False, widget=forms.PasswordInput, required=False)
    role = None
    used_message = "このIDはすでに使われています。"

    def __init__(self, *args, account=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        if account is None:
            self.fields["password"].required = True
            self.fields["password_confirm"].required = True
            self.fields["password"].error_messages["required"] = "パスワードを入力してください。"
            self.fields["password_confirm"].error_messages["required"] = "パスワード（確認）を入力してください。"
        else:
            self.initial.setdefault("account_id", account.username)

    def clean_account_id(self):
        account_id = self.cleaned_data["account_id"].strip()
        others = User.objects.filter(username=account_id)
        if self.account is not None:
            others = others.exclude(pk=self.account.pk)
        if others.exists():
            raise forms.ValidationError(self.used_message)
        return account_id

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") or cleaned.get("password_confirm") or self.account is None:
            if cleaned.get("password") and not cleaned.get("password_confirm"):
                self.add_error("password_confirm", "パスワード（確認）を入力してください。")
            check_new_password(self, User(username=cleaned.get("account_id", "")))
        return cleaned

    def save(self):
        account = self.account or User(role=self.role)
        account.username = self.cleaned_data["account_id"]
        if self.cleaned_data.get("password"):
            account.set_password(self.cleaned_data["password"])
        account.save()
        return account


class AdminAccountForm(AccountIdPasswordForm):
    """管理者アカウントの新規作成（ログイン中の管理者だけが使える）"""
    role = User.Role.BOARD
    used_message = "この管理者IDはすでに使われています。"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account_id"].label = "管理者ID"


class SchoolAccountForm(AccountIdPasswordForm):
    """学校アカウント（学校ID＋パスワード）の作成・編集"""
    role = User.Role.SCHOOL
    used_message = "この学校IDはすでに使われています。"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account_id"].label = "学校ID"


# ---------- 顧問が使うフォーム ----------

class AdvisorClubForm(RequiredMessageMixin, forms.ModelForm):
    """顧問が、自校の部活動（競技・男女区分・部活ID）を登録・編集するフォーム"""

    class Meta:
        model = Club
        fields = ["sport", "gender", "code"]
        labels = {"gender": "男女区分"}

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.instance.school = school
        self.fields["sport"].queryset = Sport.objects.order_by("name")
        self.fields["sport"].label_from_instance = lambda s: f"{s.display_icon} {s.name}"
        self.fields["sport"].empty_label = "競技種目を選択してください"
        self.fields["gender"].choices = [("", "男女区分を選択してください")] + list(Club.Gender.choices)

    def clean(self):
        cleaned = super().clean()
        clubs = Club.objects.filter(school=self.school).exclude(pk=self.instance.pk)
        sport, gender, code = cleaned.get("sport"), cleaned.get("gender"), cleaned.get("code")
        if sport and gender and clubs.filter(sport=sport, gender=gender).exists():
            self.add_error(None, "この競技・男女区分の部活動は、すでに登録されています。")
        if code and clubs.filter(code=code).exists():
            self.add_error("code", "この部活IDは、この学校ですでに使われています。")
        return cleaned

    # 重なりの確認は clean() で分かりやすいメッセージにしているので、Django の確認は行わない
    def validate_unique(self):
        pass

    def validate_constraints(self):
        pass


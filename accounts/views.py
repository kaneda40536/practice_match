from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView, ListView, TemplateView, View

from .forms import (
    AdminAccountForm, AdvisorLoginForm, AdvisorRegisterForm, BoardLoginForm,
    ClubAccountRegisterForm, ClubLoginForm, EntryForm, SchoolAccountForm,
)
from .models import User
from schools.models import Club, School
from facilities.models import Facility
from matching.models import Message, PracticeMatch


# ---------- アカウントの種類 ----------

def is_board(user):
    """教育委員会の管理者かどうか（スーパーユーザーも含む）"""
    return user.is_superuser or user.role == User.Role.BOARD


def is_club_account(user):
    """部活動が設定されている、部活動のアカウントかどうか"""
    return user.role == User.Role.CLUB and user.club_id is not None


def is_advisor(user):
    """学校が設定されている、顧問のアカウントかどうか"""
    return user.role == User.Role.TEACHER and user.school_id is not None


def home_url_for(user):
    """そのユーザーのホーム画面。ホームのないアカウント（学校アカウントなど）は None"""
    if is_board(user):
        return reverse("board_home")
    if is_club_account(user):
        return reverse("teacher_home")
    if is_advisor(user):
        return reverse("advisor_home")
    return None


def form_error_message(form):
    """画面の上に1行で出すエラー（デザインでは、エラーを1か所にまとめて表示する）"""
    missing = [
        str(field.label) for name, field in form.fields.items()
        if field.required and name in form.errors and not str(form.data.get(name, "")).strip()
    ]
    if missing:
        joiner = "と" if len(missing) <= 2 else "・"
        return joiner.join(missing) + "を入力してください。"
    for error in form.non_field_errors():
        return error
    for name in form.fields:
        if name in form.errors:
            return form.errors[name][0]
    return "入力内容を確認してください。"


class SingleErrorFormMixin:
    """入力に誤りがあるとき、エラーを1行（error）にして画面に渡す"""

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form, error=form_error_message(form)))


# ---------- 入口・ログイン・ログアウト ----------

class EntryView(SingleErrorFormMixin, FormView):
    """最初の画面。アカウントIDを入れると、管理者ログインか学校側ログインに進む"""
    form_class = EntryForm
    template_name = "auth/entry.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and home_url_for(request.user):
            return redirect(home_url_for(request.user))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        account_id = form.cleaned_data["account_id"]
        if form.destination == "board":
            return redirect(f"{reverse('board_login')}?account_id={account_id}")
        return redirect(f"{reverse('login')}?school_id={account_id}")


class DesignLoginView(SingleErrorFormMixin, LoginView):
    """ログイン画面の共通部分。URL の ?school_id= などを、入力欄に最初から入れておく"""
    redirect_authenticated_user = True
    prefill = ()

    def get_initial(self):
        initial = super().get_initial()
        for name in self.prefill:
            if self.request.GET.get(name):
                initial[name] = self.request.GET[name]
        return initial

    def get_success_url(self):
        return self.get_redirect_url() or home_url_for(self.request.user) or reverse("entry")


class BoardLoginView(DesignLoginView):
    """管理者ログイン（管理者ID＋パスワード）"""
    form_class = BoardLoginForm
    template_name = "auth/admin_login.html"
    prefill = ("account_id",)


class ClubLoginView(DesignLoginView):
    """学校側ログイン（学校ID＋部活ID＋パスワード）"""
    form_class = ClubLoginForm
    template_name = "auth/school_login.html"
    prefill = ("school_id", "club_id")


class AdvisorLoginView(DesignLoginView):
    """顧問ログイン（学校ID＋顧問名＋パスワード）"""
    form_class = AdvisorLoginForm
    template_name = "auth/advisor_login.html"
    prefill = ("school_id",)


def custom_logout_view(request):
    logout(request)
    return redirect("entry")


# ---------- 新規登録（ログインしていない人が使う） ----------

class AdvisorRegisterView(SingleErrorFormMixin, FormView):
    """顧問アカウントの新規登録"""
    form_class = AdvisorRegisterForm
    template_name = "auth/teacher_register.html"

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f"顧問アカウント（{user.advisor_name}）を登録しました。ログインしてください。")
        return redirect(f"{reverse('advisor_login')}?school_id={user.school.code}")


class ClubAccountRegisterView(SingleErrorFormMixin, FormView):
    """部活動アカウントの新規登録"""
    form_class = ClubAccountRegisterForm
    template_name = "auth/club_account_register.html"

    def form_valid(self, form):
        user = form.save()
        club = user.club
        messages.success(self.request, f"「{user.display_name}」のアカウントを登録しました。ログインしてください。")
        return redirect(f"{reverse('login')}?school_id={club.school.code}&club_id={club.code}")


# ---------- 共通の部品（ミックスイン） ----------

class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """見られない画面を開いたときに、403 の画面ではなく自分のホームに案内する

    同じブラウザの別のタブで別のアカウントにログインすると、ログイン状態が
    入れ替わる（ブラウザに保存できるログインは1つだけ）。そのため、前のタブで
    操作すると「この画面は見られない」状態になりやすいので、分かるように知らせる。
    """

    def handle_no_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return super().handle_no_permission()   # 最初の画面へ
        home = home_url_for(user)
        if home is None:
            logout(self.request)
            messages.error(self.request, "このアカウントでは、この画面を利用できません。")
            return redirect("entry")
        messages.warning(
            self.request,
            f"この画面は、いまログインしている「{user.display_name}」では開けないため、ホームに移動しました。"
            "同じブラウザの別のタブで、別のアカウントにログインしていませんか？",
        )
        return redirect(home)


class BoardRequiredMixin(RoleRequiredMixin):
    """教育委員会の管理者だけが見られる画面に付ける"""
    def test_func(self):
        return is_board(self.request.user)


class TeacherRequiredMixin(RoleRequiredMixin):
    """部活動のアカウントだけが見られる画面に付ける"""
    def test_func(self):
        return is_club_account(self.request.user)


class AdvisorRequiredMixin(RoleRequiredMixin):
    """顧問のアカウントだけが見られる画面に付ける"""
    def test_func(self):
        return is_advisor(self.request.user)


# ---------- ホーム画面（トップ） ----------
# メニューカードは accounts/menus.py の内容を context_processors.navigation が渡す

class BoardHomeView(BoardRequiredMixin, TemplateView):
    template_name = "board_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = [
            {"label": "学校アカウント", "icon": "▣", "color": "blue",
             "value": User.objects.filter(role=User.Role.SCHOOL).count(),
             "unit": "件", "note": "登録されている学校アカウント"},
            {"label": "登録学校数", "icon": "▤", "color": "green",
             "value": School.objects.count(),
             "unit": "校", "note": "学校情報が登録されている学校"},
            {"label": "部活動数", "icon": "▦", "color": "purple",
             "value": Club.objects.count(),
             "unit": "件", "note": "登録されている部活動"},
            {"label": "施設数", "icon": "⌖", "color": "orange",
             "value": Facility.objects.filter(school__isnull=True).count(),
             "unit": "件", "note": "登録されている施設"},
        ]
        return context


class TeacherHomeView(TeacherRequiredMixin, TemplateView):
    """部活動のホーム"""
    template_name = "teacher_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        club = self.request.user.club
        today = timezone.localdate()
        pending = PracticeMatch.Status.PENDING
        context["stats"] = [
            {"label": "届いた申し込み", "icon": "↓", "color": "orange",
             "value": PracticeMatch.objects.filter(opponent_club=club, status=pending).count(),
             "unit": "件", "note": "返事を待っている申し込み"},
            {"label": "申し込み中", "icon": "↑", "color": "blue",
             "value": PracticeMatch.objects.filter(applicant_club=club, status=pending).count(),
             "unit": "件", "note": "相手校の返事を待っている試合"},
            {"label": "予定の試合", "icon": "✓", "color": "green",
             "value": PracticeMatch.objects.filter(
                 Q(applicant_club=club) | Q(opponent_club=club),
                 status=PracticeMatch.Status.CONFIRMED, date__gte=today).count(),
             "unit": "件", "note": "今日以降に確定している試合"},
            {"label": "未読メッセージ", "icon": "✉", "color": "purple",
             "value": Message.unread_for(club).count(),
             "unit": "件", "note": "まだ読んでいない他校からのメッセージ"},
        ]
        return context


class AdvisorHomeView(AdvisorRequiredMixin, TemplateView):
    """顧問のホーム"""
    template_name = "advisor_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clubs = Club.objects.filter(school=self.request.user.school)
        context["stats"] = [
            {"label": "部活動", "icon": "▤", "color": "green",
             "value": clubs.count(), "unit": "件", "note": "登録されている自校の部活動"},
            {"label": "アカウント登録済み", "icon": "✓", "color": "blue",
             "value": clubs.filter(account__isnull=False).count(),
             "unit": "件", "note": "部活動アカウントが登録された部活動"},
            {"label": "アカウント未登録", "icon": "！", "color": "orange",
             "value": clubs.filter(account__isnull=True).count(),
             "unit": "件", "note": "部活IDを伝えて、登録してもらう部活動"},
        ]
        return context


# ---------- 管理者アカウントの作成（教育委員会） ----------

class AdminAccountCreateView(BoardRequiredMixin, SingleErrorFormMixin, FormView):
    """管理者アカウントの新規作成。ログイン中の管理者だけが使える"""
    form_class = AdminAccountForm
    template_name = "auth/admin_account_form.html"

    def form_valid(self, form):
        account = form.save()
        messages.success(self.request, f"管理者アカウント（{account.username}）を作成しました。")
        return redirect("board_home")


# ---------- 学校アカウント管理（教育委員会） ----------

def school_accounts():
    return User.objects.filter(role=User.Role.SCHOOL).select_related("school_profile")


class SchoolAccountListView(BoardRequiredMixin, ListView):
    """学校アカウント（学校ID＋パスワード）の一覧"""
    template_name = "school_accounts/account_list.html"
    context_object_name = "accounts"

    def get_queryset(self):
        return school_accounts().order_by("username")


class SchoolAccountFormView(BoardRequiredMixin, SingleErrorFormMixin, FormView):
    """学校アカウントの作成（pk なし）と編集（pk あり）"""
    form_class = SchoolAccountForm
    template_name = "school_accounts/account_form.html"

    def get_account(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(school_accounts(), pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["account"] = self.get_account()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        context["account"] = account
        context["page_title"] = "学校アカウントの編集" if account else "学校アカウントの作成"
        return context

    def form_valid(self, form):
        editing = form.account is not None
        account = form.save()
        messages.success(
            self.request,
            f"学校アカウント（学校ID：{account.username}）を{'更新' if editing else '作成'}しました。")
        return redirect("school_account_list")


class SchoolAccountToggleView(BoardRequiredMixin, View):
    """利用状態の変更（確認画面のあと）。利用停止にすると、その学校の顧問・部活動もログインできなくなる"""
    template_name = "school_accounts/account_toggle_confirm.html"

    def get(self, request, pk):
        account = get_object_or_404(school_accounts(), pk=pk)
        return render(request, self.template_name, {"account": account})

    def post(self, request, pk):
        account = get_object_or_404(school_accounts(), pk=pk)
        account.is_active = not account.is_active
        account.save(update_fields=["is_active"])
        state = "利用再開" if account.is_active else "利用停止"
        messages.success(request, f"学校ID「{account.username}」を{state}にしました。")
        return redirect("school_account_list")


class SchoolAccountDeleteView(BoardRequiredMixin, View):
    """学校アカウントの削除（確認画面のあと）。学校情報が登録されていれば削除できない"""
    template_name = "school_accounts/account_confirm_delete.html"

    def get(self, request, pk):
        account = get_object_or_404(school_accounts(), pk=pk)
        return render(request, self.template_name, {
            "account": account, "has_school": hasattr(account, "school_profile")})

    def post(self, request, pk):
        account = get_object_or_404(school_accounts(), pk=pk)
        if hasattr(account, "school_profile"):
            messages.error(request, "学校情報が登録されているため、この学校アカウントは削除できません。")
            return redirect("school_account_delete", pk=pk)
        username = account.username
        account.delete()
        messages.success(request, f"学校アカウント（学校ID：{username}）を削除しました。")
        return redirect("school_account_list")


# ---------- 送信の確認（CSRF）に失敗したとき ----------

def csrf_failure(request, reason=""):
    """403 の画面の代わりに、もう一度操作してもらうよう案内する

    画面を開いたあとに、同じブラウザの別のタブでログイン・ログアウトをすると、
    送信の確認に使う値が変わるため、前のタブからの送信は受け付けられなくなる。
    """
    user = request.user
    messages.error(
        request,
        "画面を開いたあとにログイン状態が変わったため、送信できませんでした。"
        "同じブラウザの別のタブで、別のアカウントにログイン（またはログアウト）していませんか？"
        "内容を確認して、もう一度操作してください。",
    )
    home = home_url_for(user) if user.is_authenticated else None
    return redirect(home or "entry")

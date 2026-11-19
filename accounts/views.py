from django.contrib import messages
from django.contrib.auth import logout

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, TemplateView, View

from .forms import CustomLoginForm, SchoolAccountCreateForm, SchoolPasswordForm
from .models import User
from schools.models import Club, School
from facilities.models import Facility
from matching.models import Message, PracticeMatch

def is_board(user):
    """教育委員会の管理者かどうか（スーパーユーザーも含む）"""
    return user.is_superuser or user.role == User.Role.BOARD


# ---------- ログイン・ログアウト ----------

class CustomLoginView(LoginView):
    form_class = CustomLoginForm
    template_name = 'login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        if is_board(self.request.user):
            return reverse_lazy('board_home')
        return reverse_lazy('teacher_home')

    def form_invalid(self, form):
        # 未入力の項目があれば、どれが未入力かを伝える（ブラウザのチェックは使わない）
        labels = {"username": "学校ID", "password": "パスワード"}
        missing = [label for name, label in labels.items()
                   if not form.data.get(name, "").strip()]
        if missing:
            error_msg = "と".join(missing) + "を入力してください。"
        elif form.non_field_errors():
            error_msg = form.non_field_errors()[0]
        else:
            error_msg = "学校IDとパスワードを入力してください。"
        return self.render_to_response(
            self.get_context_data(form=form, error=error_msg)
        )


def custom_logout_view(request):
    logout(request)
    return redirect('login')


# ---------- 共通の部品（ミックスイン） ----------

def home_url_for(user):
    """そのユーザーのホーム画面。顧問なのに学校が設定されていなければ None"""
    if is_board(user):
        return reverse_lazy("board_home")
    if user.role == User.Role.TEACHER and user.school_id is not None:
        return reverse_lazy("teacher_home")
    return None


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """見られない画面を開いたときに、403 の画面ではなく自分のホームに案内する

    同じブラウザの別のタブで別のアカウントにログインすると、ログイン状態が
    入れ替わる（ブラウザに保存できるログインは1つだけ）。そのため、前のタブで
    操作すると「この画面は見られない」状態になりやすいので、分かるように知らせる。
    """

    def handle_no_permission(self):
        user = self.request.user
        if not user.is_authenticated:
            return super().handle_no_permission()   # ログイン画面へ
        home = home_url_for(user)
        if home is None:
            logout(self.request)
            messages.error(self.request, "このアカウントには学校が設定されていません。教育委員会にお問い合わせください。")
            return redirect("login")
        messages.warning(
            self.request,
            f"この画面は、いまログインしている「{user.username}」では開けないため、ホームに移動しました。"
            "同じブラウザの別のタブで、別のアカウントにログインしていませんか？",
        )
        return redirect(home)


class BoardRequiredMixin(RoleRequiredMixin):
    """教育委員会の管理者だけが見られる画面に付ける"""
    def test_func(self):
        return is_board(self.request.user)

class TeacherRequiredMixin(RoleRequiredMixin):
    """学校が設定されている顧問だけが見られる画面に付ける"""
    def test_func(self):
        user = self.request.user
        return user.role == User.Role.TEACHER and user.school_id is not None

# ---------- ホーム画面（トップ） ----------
# メニューカードは accounts/menus.py の内容を context_processors.navigation が渡す

class BoardHomeView(BoardRequiredMixin, TemplateView):
    template_name = "board_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = [
            {"label": "学校アカウント", "icon": "▣", "color": "blue",
             "value": User.objects.filter(role=User.Role.TEACHER).count(),
             "unit": "件", "note": "登録されている学校アカウント"},
            {"label": "登録学校数", "icon": "▤", "color": "green",
             "value": School.objects.count(),
             "unit": "校", "note": "学校情報が登録されている学校"},
            {"label": "部活動数", "icon": "▦", "color": "purple",
             "value": Club.objects.count(),
             "unit": "件", "note": "登録されている部活動"},
            {"label": "施設数", "icon": "⌖", "color": "orange",
             "value": Facility.objects.count(),
             "unit": "件", "note": "登録されている施設"},
        ]
        return context

class TeacherHomeView(TeacherRequiredMixin, TemplateView):
    """顧問のホーム"""
    template_name = "teacher_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        today = timezone.localdate()
        pending = PracticeMatch.Status.PENDING
        context["stats"] = [
            {"label": "届いた申し込み", "icon": "↓", "color": "orange",
             "value": PracticeMatch.objects.filter(
                 opponent_club__school=school, status=pending).count(),
             "unit": "件", "note": "返事を待っている申し込み"},
            {"label": "申し込み中", "icon": "↑", "color": "blue",
             "value": PracticeMatch.objects.filter(
                 applicant_club__school=school, status=pending).count(),
             "unit": "件", "note": "相手校の返事を待っている試合"},
            {"label": "予定の試合", "icon": "✓", "color": "green",
             "value": PracticeMatch.objects.filter(
                 Q(applicant_club__school=school) | Q(opponent_club__school=school),
                 status=PracticeMatch.Status.CONFIRMED, date__gte=today).count(),
             "unit": "件", "note": "今日以降に確定している試合"},
            {"label": "未読メッセージ", "icon": "✉", "color": "purple",
             "value": Message.unread_for(school).count(),
             "unit": "件", "note": "まだ読んでいない他校からのメッセージ"},
        ]
        return context


# ---------- 学校アカウント管理（教育委員会） ----------

class SchoolAccountListView(BoardRequiredMixin, ListView):
    template_name = "school_accounts/account_list.html"
    context_object_name = "accounts"

    def get_queryset(self):
        return (
            User.objects.filter(role=User.Role.TEACHER)
            .select_related("school__area")
            .order_by("school__name", "username")
        )


class SchoolAccountCreateView(BoardRequiredMixin, FormView):
    form_class = SchoolAccountCreateForm
    template_name = "school_accounts/account_form.html"
    success_url = reverse_lazy("school_account_list")

    def form_valid(self, form):
        user = form.save()
        messages.success(
            self.request,
            f"「{user.school.name}」のアカウント（学校ID：{user.username}）を作成しました。",
        )
        return super().form_valid(form)


class SchoolAccountPasswordView(BoardRequiredMixin, FormView):
    form_class = SchoolPasswordForm
    template_name = "school_accounts/password_form.html"
    success_url = reverse_lazy("school_account_list")

    def get_target(self):
        return get_object_or_404(User, pk=self.kwargs["pk"], role=User.Role.TEACHER)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.get_target()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target"] = self.get_target()
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "パスワードを再設定しました。")
        return super().form_valid(form)


class SchoolAccountToggleView(BoardRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "有効" if user.is_active else "無効"
        messages.success(request, f"学校ID「{user.username}」を{state}にしました。")
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
    return redirect(home or "login")

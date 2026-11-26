from django.contrib import messages
from django.contrib.auth import logout

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView, View

from .forms import BoardLoginForm, ClubAccountCreateForm, ClubLoginForm, ClubPasswordForm
from .models import User
from schools.models import Club, School
from facilities.models import Facility
from matching.models import Message, PracticeMatch

def is_board(user):
    """教育委員会の管理者かどうか（スーパーユーザーも含む）"""
    return user.is_superuser or user.role == User.Role.BOARD


def is_club_account(user):
    """部活動が設定されている、部活動（顧問）のアカウントかどうか"""
    return user.role == User.Role.TEACHER and user.club_id is not None


# ---------- ログイン・ログアウト ----------

class ClubLoginView(LoginView):
    """部活動アカウントのログイン（学校ID＋部活動ID＋パスワード）"""
    form_class = ClubLoginForm
    template_name = 'login.html'
    redirect_authenticated_user = True
    board_login = False
    # 未入力のときに伝える項目（フォームの項目名 → 画面の表示名）
    labels = {"school_code": "学校ID", "club_code": "部活動ID", "password": "パスワード"}

    def get_success_url(self):
        url = self.get_redirect_url()
        if url:
            return url
        return home_url_for(self.request.user) or reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["board_login"] = self.board_login
        return context

    def form_invalid(self, form):
        # 未入力の項目があれば、どれが未入力かを伝える（ブラウザのチェックは使わない）
        missing = [label for name, label in self.labels.items()
                   if not form.data.get(name, "").strip()]
        if missing:
            joiner = "と" if len(missing) <= 2 else "・"
            error_msg = joiner.join(missing) + "を入力してください。"
        elif form.non_field_errors():
            error_msg = form.non_field_errors()[0]
        else:
            error_msg = "・".join(self.labels.values()) + "を入力してください。"
        return self.render_to_response(
            self.get_context_data(form=form, error=error_msg)
        )


class BoardLoginView(ClubLoginView):
    """教育委員会（管理者）のログイン（管理者ID＋パスワード）"""
    form_class = BoardLoginForm
    board_login = True
    labels = {"username": "管理者ID", "password": "パスワード"}


def custom_logout_view(request):
    logout(request)
    return redirect('login')


# ---------- 共通の部品（ミックスイン） ----------

def home_url_for(user):
    """そのユーザーのホーム画面。顧問なのに部活動が設定されていなければ None"""
    if is_board(user):
        return reverse_lazy("board_home")
    if is_club_account(user):
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
            messages.error(self.request, "このアカウントには部活動が設定されていません。教育委員会にお問い合わせください。")
            return redirect("login")
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

# ---------- ホーム画面（トップ） ----------
# メニューカードは accounts/menus.py の内容を context_processors.navigation が渡す

class BoardHomeView(BoardRequiredMixin, TemplateView):
    template_name = "board_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = [
            {"label": "部活動アカウント", "icon": "▣", "color": "blue",
             "value": User.objects.filter(role=User.Role.TEACHER, club__isnull=False).count(),
             "unit": "件", "note": "登録されている部活動アカウント"},
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


# ---------- 部活動アカウント管理（教育委員会） ----------

def club_accounts():
    return User.objects.filter(role=User.Role.TEACHER, club__isnull=False)


class SchoolAccountListView(BoardRequiredMixin, TemplateView):
    """部活動アカウントの一覧。学校名・学校ID・部活動名・部活動IDを、学校ごとにまとめて表示する"""
    template_name = "school_accounts/account_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clubs_with_account = (
            Club.objects.filter(account__role=User.Role.TEACHER)
            .select_related("account", "sport")
            .order_by("sport__name", "gender")
        )
        context["schools"] = School.objects.order_by("name").prefetch_related(
            Prefetch("club_set", queryset=clubs_with_account, to_attr="account_clubs"))
        context["account_count"] = club_accounts().count()
        return context


class SchoolAccountCreateView(BoardRequiredMixin, FormView):
    form_class = ClubAccountCreateForm
    template_name = "school_accounts/account_form.html"
    success_url = reverse_lazy("school_account_list")

    def get_initial(self):
        # 学校一覧の「部活動アカウントを追加」から来たときは、その学校を選んでおく
        initial = super().get_initial()
        school = self.request.GET.get("school", "")
        if school.isdigit():
            initial["school"] = school
        return initial

    def form_valid(self, form):
        user = form.save()
        club = user.club
        messages.success(
            self.request,
            f"「{user.display_name}」のアカウント（学校ID：{club.school.code}／部活動ID：{club.code}）を作成しました。",
        )
        return super().form_valid(form)


class SchoolAccountPasswordView(BoardRequiredMixin, FormView):
    form_class = ClubPasswordForm
    template_name = "school_accounts/password_form.html"
    success_url = reverse_lazy("school_account_list")

    def get_target(self):
        return get_object_or_404(
            club_accounts().select_related("club__school", "club__sport"), pk=self.kwargs["pk"])

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
        user = get_object_or_404(club_accounts(), pk=pk)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        state = "有効" if user.is_active else "無効"
        messages.success(request, f"「{user.display_name}」のアカウントを{state}にしました。")
        return redirect("school_account_list")


class SchoolAccountDeleteView(BoardRequiredMixin, TemplateView):
    """部活動アカウントを、部活動ごと削除する（確認画面のあと）。
    部活動の希望日・練習試合の申し込み・試合結果・メッセージ・大会成績も一緒に消える"""
    template_name = "school_accounts/account_confirm_delete.html"

    def get_target(self):
        return get_object_or_404(
            club_accounts().select_related("club__school", "club__sport"), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target = self.get_target()
        club = target.club
        context.update({
            "target": target,
            "match_count": PracticeMatch.objects.filter(
                Q(applicant_club=club) | Q(opponent_club=club)).count(),
            "result_count": club.tournament_results.count(),
        })
        return context

    def post(self, request, pk):
        target = self.get_target()
        name = target.display_name
        with transaction.atomic():
            target.club.delete()      # アカウントも、部活動と一緒に削除される
        messages.success(request, f"「{name}」のアカウントを削除しました。")
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

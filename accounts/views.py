from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, TemplateView, View

from .forms import CustomLoginForm, SchoolAccountCreateForm
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
        if form.non_field_errors():
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

class BoardRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """教育委員会の管理者だけが見られる画面に付ける"""
    def test_func(self):
        return is_board(self.request.user)

class TeacherRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
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
             "value": Message.objects.filter(receiver=school, is_read=False).count(),
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
    form_class = SetPasswordForm
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
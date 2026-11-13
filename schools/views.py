from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from accounts.views import BoardRequiredMixin, TeacherRequiredMixin
from .forms import ClubForm, SchoolAddressForm, SchoolUpdateForm
from .models import Area, Club, School, Sport

User = get_user_model()


# ---------- 競技管理（教育委員会） ----------

class SportListView(BoardRequiredMixin, ListView):
    model = Sport
    template_name = "sports/sport_list.html"
    context_object_name = "sports"
    ordering = ["name"]


class SportCreateView(BoardRequiredMixin, CreateView):
    model = Sport
    fields = ["name"]
    template_name = "sports/sport_form.html"
    success_url = reverse_lazy("sport_list")

    def form_valid(self, form):
        messages.success(self.request, "競技を登録しました。")
        return super().form_valid(form)


class SportUpdateView(BoardRequiredMixin, UpdateView):
    model = Sport
    fields = ["name"]
    template_name = "sports/sport_form.html"
    success_url = reverse_lazy("sport_list")

    def form_valid(self, form):
        messages.success(self.request, "競技を更新しました。")
        return super().form_valid(form)


class SportDeleteView(BoardRequiredMixin, DeleteView):
    model = Sport
    template_name = "sports/sport_confirm_delete.html"
    success_url = reverse_lazy("sport_list")

    def get_context_data(self, **kwargs):
        # 削除できない理由を、確認画面であらかじめ表示する
        context = super().get_context_data(**kwargs)
        reasons = []
        club_count = self.object.club_set.count()
        facility_count = self.object.facility_set.count()
        if club_count:
            reasons.append(f"部活動で使われています（{club_count}件）")
        if facility_count:
            reasons.append(f"施設の対応競技として使われています（{facility_count}件）")
        context["reasons"] = reasons
        return context

    def form_valid(self, form):
        # 多対多の関係は、何もしないと中間のデータが黙って消えてしまうので、先に確認する
        if self.object.facility_set.exists():
            messages.error(self.request, "この競技は施設の対応競技として使われているため、削除できません。")
            return redirect("sport_list")
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "この競技は部活動で使われているため、削除できません。")
            return redirect("sport_list")
        messages.success(self.request, "競技を削除しました。")
        return response

# ---------- 学校情報管理（教育委員会） ----------

class SchoolListView(BoardRequiredMixin, ListView):
    model = School
    template_name = "schools/school_list.html"
    context_object_name = "schools"
    ordering = ["name"]

    def get_queryset(self):
        return super().get_queryset().select_related("area")


class SchoolUpdateView(BoardRequiredMixin, UpdateView):
    model = School
    form_class = SchoolUpdateForm
    template_name = "schools/school_form.html"
    success_url = reverse_lazy("school_list")

    def form_valid(self, form):
        messages.success(self.request, "学校情報を更新しました。")
        return super().form_valid(form)


class SchoolDeleteView(BoardRequiredMixin, DeleteView):
    model = School
    template_name = "schools/school_confirm_delete.html"
    success_url = reverse_lazy("school_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["club_count"] = self.object.club_set.count()
        context["account_count"] = User.objects.filter(
            school=self.object, role=User.Role.TEACHER
        ).count()
        return context

    def form_valid(self, form):
        school = self.object
        with transaction.atomic():
            # 学校を消すと使い道のなくなるログインアカウントも、あわせて削除する
            User.objects.filter(school=school, role=User.Role.TEACHER).delete()
            school.delete()
        messages.success(self.request, f"「{school.name}」を削除しました。")
        return redirect("school_list")


# ---------- 部活動一覧（教育委員会） ----------

class ClubListView(BoardRequiredMixin, ListView):
    template_name = "clubs/club_list.html"
    context_object_name = "clubs"

    def get_filters(self):
        """URLの ?area=1&sport=2&gender=male を、安全な形で取り出す"""
        params = self.request.GET
        area = params.get("area", "")
        sport = params.get("sport", "")
        gender = params.get("gender", "")
        return {
            "area": area if area.isdigit() else "",
            "sport": sport if sport.isdigit() else "",
            "gender": gender if gender in Club.Gender.values else "",
        }

    def get_queryset(self):
        filters = self.get_filters()
        queryset = Club.objects.select_related("school__area", "sport").order_by(
            "school__name", "sport__name", "gender"
        )
        if filters["area"]:
            queryset = queryset.filter(school__area_id=filters["area"])
        if filters["sport"]:
            queryset = queryset.filter(sport_id=filters["sport"])
        if filters["gender"]:
            queryset = queryset.filter(gender=filters["gender"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["areas"] = Area.objects.order_by("name")
        context["sports"] = Sport.objects.order_by("name")
        context["genders"] = Club.Gender.choices
        context["selected"] = self.get_filters()
        return context


# ---------- 自校の学校情報（顧問） ----------

class MySchoolView(TeacherRequiredMixin, DetailView):
    """顧問が自校の学校情報を表示する（編集は教育委員会が行う）"""
    template_name = "my_school/school_detail.html"
    context_object_name = "school"

    def get_object(self, queryset=None):
        # URLの番号ではなく、ログイン中の顧問の学校だけを対象にする
        return self.request.user.school

# ---------- 自校の部活動管理（顧問） ----------

class MyClubsContextMixin:
    """部活動管理の画面に、自校の部活動の一覧（希望日の件数つき）を渡す"""

    def get_my_clubs(self):
        today = timezone.localdate()
        return (
            Club.objects.filter(school=self.request.user.school)
            .select_related("sport")
            .annotate(
                date_count=Count("availability", filter=Q(availability__date__gte=today))
            )
            .order_by("sport__name", "gender")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clubs"] = self.get_my_clubs()
        return context


class MyClubListView(TeacherRequiredMixin, MyClubsContextMixin, TemplateView):
    """部活動の一覧と、登録フォームを1画面で表示する（登録は MyClubCreateView へ送る）"""
    template_name = "my_clubs/club_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = ClubForm(school=self.request.user.school)
        return context


class MyClubCreateView(TeacherRequiredMixin, MyClubsContextMixin, CreateView):
    """登録フォームの送信先。入力に誤りがあれば、一覧画面にエラーつきで戻る"""
    form_class = ClubForm
    template_name = "my_clubs/club_list.html"
    success_url = reverse_lazy("my_club_list")

    def get(self, request, *args, **kwargs):
        return redirect("my_club_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["school"] = self.request.user.school
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "部活動を登録しました。")
        return super().form_valid(form)


class MyClubDeleteView(TeacherRequiredMixin, DeleteView):
    template_name = "my_clubs/club_confirm_delete.html"
    success_url = reverse_lazy("my_club_list")

    def get_queryset(self):
        # 自校の部活動だけが対象。他校の部活動の番号を指定しても、見つからない扱いになる
        return Club.objects.filter(school=self.request.user.school)

    def form_valid(self, form):
        name = f"{self.object.get_gender_display()}{self.object.sport.name}部"
        response = super().form_valid(form)
        messages.success(self.request, f"「{name}」を削除しました。")
        return response
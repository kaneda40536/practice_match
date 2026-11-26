from django.contrib import messages
from django.db.models import Prefetch, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View
from accounts.views import BoardRequiredMixin, TeacherRequiredMixin
from .forms import SchoolUpdateForm, SportForm, TournamentResultForm
from .models import Club, School, Sport, TournamentResult


# ---------- 競技管理（教育委員会） ----------

class SportListView(BoardRequiredMixin, ListView):
    model = Sport
    template_name = "sports/sport_list.html"
    context_object_name = "sports"
    ordering = ["name"]


class SportCreateView(BoardRequiredMixin, CreateView):
    model = Sport
    form_class = SportForm
    template_name = "sports/sport_form.html"
    success_url = reverse_lazy("sport_list")

    def form_valid(self, form):
        messages.success(self.request, "競技を登録しました。")
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
            reasons.append(f"会場の対応競技として使われています（{facility_count}件）")
        context["reasons"] = reasons
        return context

    def form_valid(self, form):
        # 多対多の関係は、何もしないと中間のデータが黙って消えてしまうので、先に確認する
        if self.object.facility_set.exists():
            messages.error(self.request, "この競技は会場の対応競技として使われているため、削除できません。")
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
    """学校の一覧（学校名・所在地・部活動）。学校の登録は「部活動アカウント管理」で行う"""
    model = School
    template_name = "schools/school_list.html"
    context_object_name = "schools"
    ordering = ["name"]

    def get_queryset(self):
        clubs = Club.objects.select_related("sport").order_by("sport__name", "gender")
        return super().get_queryset().prefetch_related(Prefetch("club_set", queryset=clubs))


class SchoolUpdateView(BoardRequiredMixin, UpdateView):
    model = School
    form_class = SchoolUpdateForm
    template_name = "schools/school_form.html"
    success_url = reverse_lazy("school_list")

    def form_valid(self, form):
        messages.success(self.request, "学校情報を更新しました。")
        return super().form_valid(form)


# ---------- 部活動一覧（教育委員会） ----------

class ClubListView(BoardRequiredMixin, ListView):
    template_name = "clubs/club_list.html"
    context_object_name = "clubs"

    def get_filters(self):
        """URLの ?sport=2&gender=male を、安全な形で取り出す"""
        params = self.request.GET
        sport = params.get("sport", "")
        gender = params.get("gender", "")
        return {
            "sport": sport if sport.isdigit() else "",
            "gender": gender if gender in Club.Gender.values else "",
        }

    def get_queryset(self):
        filters = self.get_filters()
        queryset = Club.objects.select_related("school", "sport").order_by(
            "school__name", "sport__name", "gender"
        )
        if filters["sport"]:
            queryset = queryset.filter(sport_id=filters["sport"])
        if filters["gender"]:
            queryset = queryset.filter(gender=filters["gender"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sports"] = Sport.objects.order_by("name")
        context["genders"] = Club.Gender.choices
        context["selected"] = self.get_filters()
        return context


# ---------- 自校の学校情報（部活動） ----------

class MySchoolView(TeacherRequiredMixin, DetailView):
    """自校の学校情報と、自分の部活動の情報を表示する（編集は教育委員会が行う）"""
    template_name = "my_school/school_detail.html"
    context_object_name = "school"

    def get_object(self, queryset=None):
        # URLの番号ではなく、ログイン中の顧問の学校だけを対象にする
        return self.request.user.school

# ---------- 大会成績管理（顧問） ----------

def my_tournament_results(club):
    return (
        TournamentResult.objects.filter(club=club)
        .select_related("club__sport")
        .order_by("-fiscal_year", "-created_at")
    )


class TournamentResultListView(TeacherRequiredMixin, View):
    """自分の部活動の大会成績の一覧と、登録フォーム"""
    template_name = "tournaments/result_list.html"

    def show(self, form):
        return render(self.request, self.template_name, {
            "form": form,
            "results": my_tournament_results(self.request.user.club),
        })

    def get(self, request):
        return self.show(TournamentResultForm(club=request.user.club))

    def post(self, request):
        form = TournamentResultForm(request.POST, club=request.user.club)
        if not form.is_valid():
            return self.show(form)
        form.save()
        messages.success(request, "大会成績を登録しました。")
        return redirect("tournament_results")


class TournamentResultUpdateView(TeacherRequiredMixin, View):
    template_name = "tournaments/result_form.html"

    def get_result(self):
        return get_object_or_404(
            TournamentResult, pk=self.kwargs["pk"], club=self.request.user.club)

    def get(self, request, pk):
        result = self.get_result()
        form = TournamentResultForm(instance=result, club=request.user.club)
        return render(request, self.template_name, {"form": form, "result": result})

    def post(self, request, pk):
        result = self.get_result()
        form = TournamentResultForm(request.POST, instance=result, club=request.user.club)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "result": result})
        form.save()
        messages.success(request, "大会成績を変更しました。")
        return redirect("tournament_results")


class TournamentResultDeleteView(TeacherRequiredMixin, View):
    def post(self, request, pk):
        result = get_object_or_404(TournamentResult, pk=pk, club=request.user.club)
        result.delete()
        messages.success(request, "大会成績を削除しました。")
        return redirect("tournament_results")

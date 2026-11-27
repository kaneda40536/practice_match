from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View
from accounts.forms import AdvisorClubForm
from accounts.models import User
from accounts.views import AdvisorRequiredMixin, BoardRequiredMixin, TeacherRequiredMixin, form_error_message
from .forms import SchoolInfoForm, SchoolSportsForm, SportForm, TournamentResultForm
from .models import Club, School, Sport, TournamentResult


# ---------- 競技管理（教育委員会） ----------

def sport_delete_reasons(sport):
    """競技を削除できない理由（部活動・施設・学校の対応競技で使われている）"""
    reasons = []
    for count, label in [
        (sport.club_set.count(), "部活動で使われています"),
        (sport.facility_set.count(), "施設の対応競技として使われています"),
        (sport.schools.count(), "学校の対応競技として使われています"),
    ]:
        if count:
            reasons.append(f"{label}（{count}件）")
    return reasons


class SportListView(BoardRequiredMixin, ListView):
    """競技の一覧。削除できない競技には、その理由を表示する"""
    model = Sport
    template_name = "sports/sport_list.html"
    context_object_name = "sports"
    ordering = ["name"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for sport in context["sports"]:
            sport.delete_error = sport_delete_reasons(sport)
        return context


class SportFormMixin(BoardRequiredMixin):
    model = Sport
    form_class = SportForm
    template_name = "sports/sport_form.html"
    success_url = reverse_lazy("sport_list")

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form, error=form_error_message(form)))


class SportCreateView(SportFormMixin, CreateView):
    def form_valid(self, form):
        messages.success(self.request, "競技を登録しました。")
        return super().form_valid(form)


class SportUpdateView(SportFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "競技を更新しました。")
        return super().form_valid(form)


class SportDeleteView(BoardRequiredMixin, View):
    """競技の削除（一覧の削除ボタンから）。使われている競技は削除できない"""

    def post(self, request, pk):
        sport = get_object_or_404(Sport, pk=pk)
        # 多対多の関係は、何もしないと中間のデータが黙って消えてしまうので、先に確認する
        if sport_delete_reasons(sport):
            messages.error(request, f"「{sport.name}」は使われているため、削除できません。")
            return redirect("sport_list")
        try:
            sport.delete()
        except ProtectedError:
            messages.error(request, f"「{sport.name}」は部活動で使われているため、削除できません。")
        else:
            messages.success(request, f"「{sport.name}」を削除しました。")
        return redirect("sport_list")


# ---------- 学校情報管理（教育委員会） ----------

class SchoolListView(BoardRequiredMixin, ListView):
    """学校情報の一覧（学校名・学校ID・所在地・連絡先・対応競技）"""
    model = School
    template_name = "schools/school_list.html"
    context_object_name = "schools"
    ordering = ["name"]

    def get_queryset(self):
        return super().get_queryset().select_related("account").prefetch_related("sports")


class SchoolFormMixin(BoardRequiredMixin):
    model = School
    form_class = SchoolInfoForm
    template_name = "schools/school_form.html"
    success_url = reverse_lazy("school_list")

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form, error=form_error_message(form)))


class SchoolCreateView(SchoolFormMixin, CreateView):
    """学校情報の登録（学校アカウント管理で作った学校IDを指定する）"""

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("account_id"):
            initial["account_id"] = self.request.GET["account_id"]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"「{self.object.name}」の学校情報を登録しました。")
        return response


class SchoolUpdateView(SchoolFormMixin, UpdateView):
    def form_valid(self, form):
        messages.success(self.request, "学校情報を更新しました。")
        return super().form_valid(form)


class SchoolDeleteView(BoardRequiredMixin, View):
    """学校情報の削除（確認画面のあと）。部活動・顧問・学校内の施設があれば削除できない"""
    template_name = "schools/school_confirm_delete.html"

    def get_school(self):
        return get_object_or_404(School.objects.select_related("account"), pk=self.kwargs["pk"])

    @staticmethod
    def reasons_for(school):
        reasons = []
        clubs = school.club_set.count()
        advisors = User.objects.filter(role=User.Role.TEACHER, school=school).count()
        facilities = school.facilities.count()
        if clubs:
            reasons.append(f"部活動が登録されています（{clubs}件）")
        if advisors:
            reasons.append(f"顧問アカウントが登録されています（{advisors}件）")
        if facilities:
            reasons.append(f"学校内の会場が登録されています（{facilities}件）")
        return reasons

    def get(self, request, pk):
        school = self.get_school()
        return render(request, self.template_name, {"school": school, "reasons": self.reasons_for(school)})

    def post(self, request, pk):
        school = self.get_school()
        if self.reasons_for(school):
            messages.error(request, "関連するデータがあるため、この学校情報は削除できません。")
            return redirect("school_delete", pk=pk)
        name = school.name
        school.delete()
        messages.success(request, f"「{name}」の学校情報を削除しました。")
        return redirect("school_list")


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


# ---------- 学校情報管理（顧問） ----------

class AdvisorSchoolView(AdvisorRequiredMixin, View):
    """自校の基本情報の確認と、対応競技の登録（学校名・所在地・連絡先は教育委員会が登録する）"""
    template_name = "advisor/school_profile.html"

    def show(self, form):
        school = self.request.user.school
        return render(self.request, self.template_name, {
            "profile": school,
            "sports": Sport.objects.order_by("name"),
            "selected_sports": {int(v) for v in form["sports"].value() or []},
        })

    def get(self, request):
        return self.show(SchoolSportsForm(instance=request.user.school))

    def post(self, request):
        form = SchoolSportsForm(request.POST, instance=request.user.school)
        if form.is_valid():
            form.save()
            messages.success(request, "対応競技を保存しました。")
            return redirect("advisor_school")
        return self.show(form)


# ---------- 部活動管理（顧問） ----------

def advisor_clubs(school):
    return Club.objects.filter(school=school).select_related("sport", "account").order_by("sport__name", "gender")


class AdvisorClubListView(AdvisorRequiredMixin, View):
    """自校の部活動の一覧と、登録フォーム（競技・男女区分・部活ID）"""
    template_name = "advisor/club_list.html"

    def show(self, form, error=None):
        return render(self.request, self.template_name, {
            "form": form, "error": error, "clubs": advisor_clubs(self.request.user.school)})

    def get(self, request):
        return self.show(AdvisorClubForm(school=request.user.school))

    def post(self, request):
        form = AdvisorClubForm(request.POST, school=request.user.school)
        if not form.is_valid():
            return self.show(form, form_error_message(form))
        club = form.save()
        messages.success(
            request, f"「{club.name}」（部活ID：{club.code}）を登録しました。部活動に学校IDと部活IDを伝えて、アカウントを登録してもらってください。")
        return redirect("advisor_club_list")


class AdvisorClubUpdateView(AdvisorRequiredMixin, View):
    template_name = "advisor/club_form.html"

    def get_club(self):
        return get_object_or_404(advisor_clubs(self.request.user.school), pk=self.kwargs["pk"])

    def get(self, request, pk):
        club = self.get_club()
        return render(request, self.template_name, {
            "club": club, "form": AdvisorClubForm(instance=club, school=request.user.school)})

    def post(self, request, pk):
        club = self.get_club()
        form = AdvisorClubForm(request.POST, instance=club, school=request.user.school)
        if not form.is_valid():
            return render(request, self.template_name, {
                "club": club, "form": form, "error": form_error_message(form)})
        form.save()
        messages.success(request, f"「{club.name}」を変更しました。")
        return redirect("advisor_club_list")


class AdvisorClubDeleteView(AdvisorRequiredMixin, View):
    """部活動の削除（一覧の削除ボタンから。部活動アカウントや練習試合の記録も消える）"""

    def post(self, request, pk):
        club = get_object_or_404(advisor_clubs(request.user.school), pk=pk)
        name = club.name
        club.delete()
        messages.success(request, f"「{name}」を削除しました。")
        return redirect("advisor_club_list")


class AdvisorClubAccountResetView(AdvisorRequiredMixin, View):
    """部活動アカウントの登録を解除する（パスワードを忘れたときなど。部活動はもう一度登録できる）"""

    def post(self, request, pk):
        club = get_object_or_404(advisor_clubs(request.user.school), pk=pk)
        User.objects.filter(club=club).delete()
        messages.success(request, f"「{club.name}」のアカウント登録を解除しました。もう一度、新規登録できます。")
        return redirect("advisor_club_list")


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

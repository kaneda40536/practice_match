from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, TemplateView, View

from accounts.views import TeacherRequiredMixin
from schools.distance import distance_km
from schools.models import Area, Club
from .forms import AvailabilityForm
from .models import Availability


# ---------- 希望日の登録 ----------

class ClubAvailabilityView(TeacherRequiredMixin, CreateView):
    """ある部活動の希望日の一覧と、追加フォーム"""
    form_class = AvailabilityForm
    template_name = "matching/availability.html"

    def get_club(self):
        # 自校の部活動だけが対象。他校の部活動の番号を指定すると、見つからない扱いになる
        return get_object_or_404(
            Club, pk=self.kwargs["club_pk"], school=self.request.user.school
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["club"] = self.get_club()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        club = self.get_club()
        context["club"] = club
        context["availabilities"] = Availability.objects.filter(
            club=club, date__gte=timezone.localdate()
        )
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "希望日を追加しました。")
        return response

    def get_success_url(self):
        return reverse("club_availability", args=[self.kwargs["club_pk"]])


class AvailabilityDeleteView(TeacherRequiredMixin, View):
    """希望日を1日削除する（確認画面は出さず、ボタンで直接削除）"""

    def post(self, request, pk):
        availability = get_object_or_404(
            Availability, pk=pk, club__school=request.user.school
        )
        club_pk = availability.club_id
        availability.delete()
        messages.success(request, "希望日を削除しました。")
        return redirect("club_availability", club_pk=club_pk)


# ---------- 対戦相手検索 ----------

class OpponentSearchView(TeacherRequiredMixin, TemplateView):
    template_name = "matching/opponent_search.html"

    @staticmethod
    def get_distance(school_a, school_b):
        """2校の直線距離（km）。どちらかの位置が未取得なら None"""
        if None in (school_a.latitude, school_a.longitude,
                    school_b.latitude, school_b.longitude):
            return None
        return round(distance_km(
            school_a.latitude, school_a.longitude,
            school_b.latitude, school_b.longitude,
        ), 1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school

        my_clubs = (
            Club.objects.filter(school=school)
            .select_related("sport")
            .order_by("sport__name", "gender")
        )

        # 検索に使う部活動は、必ず自校のものから選ぶ（他校の番号を指定しても無視される）
        club_param = self.request.GET.get("club", "")
        if club_param.isdigit():
            club = my_clubs.filter(pk=club_param).first()
        elif not club_param and my_clubs.count() == 1:
            club = my_clubs.first()
        else:
            club = None

        area_param = self.request.GET.get("area", "")
        selected_area = area_param if area_param.isdigit() else ""

        context.update({
            "my_clubs": my_clubs,
            "areas": Area.objects.order_by("name"),
            "selected_club": club,
            "selected_area": selected_area,
        })
        if club is None:
            return context

        # 自校の、これから先の希望日（日付 → 希望日のデータ）
        today = timezone.localdate()
        my_dates = {
            a.date: a
            for a in Availability.objects.filter(club=club, date__gte=today)
        }
        context["has_my_dates"] = bool(my_dates)

        # 相手の候補：同じ競技・同じ区分で、別の学校の部活動
        opponents = (
            Club.objects.filter(sport=club.sport, gender=club.gender)
            .exclude(school=school)
            .select_related("school__area")
        )
        if selected_area:
            opponents = opponents.filter(school__area_id=selected_area)

        # 共通の希望日を、相手の部活動ごとにまとめる
        common = {}
        if my_dates:
            overlapping = (
                Availability.objects.filter(club__in=opponents, date__in=list(my_dates))
                .order_by("date")
            )
            for a in overlapping:
                common.setdefault(a.club_id, []).append({
                    "date": a.date,
                    "my_host": my_dates[a.date].can_host,
                    "their_host": a.can_host,
                })

        matches, others = [], []
        for opp in opponents:
            row = {
                "club": opp,
                "school": opp.school,
                "distance": self.get_distance(school, opp.school),
                "common": common.get(opp.pk, []),
            }
            (matches if row["common"] else others).append(row)

        # 並び順：自校と同じ地域が先、次に距離が近い順、最後に学校名
        def sort_key(row):
            same_area = (
                school.area_id is not None
                and row["school"].area_id == school.area_id
            )
            distance = row["distance"] if row["distance"] is not None else 99999
            return (0 if same_area else 1, distance, row["school"].name)

        context["matches"] = sorted(matches, key=sort_key)
        context["others"] = sorted(others, key=sort_key)
        return context
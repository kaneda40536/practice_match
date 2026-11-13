from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, View

from accounts.views import TeacherRequiredMixin
from schools.distance import distance_km
from schools.models import Area, Club, School
from .forms import AvailabilityForm, MatchRequestForm, MatchResultForm, MessageForm
from .models import Availability, MatchResult, Message, PracticeMatch

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

# ---------- 練習試合の申し込み ----------

class MatchRequestView(TeacherRequiredMixin, CreateView):
    """相手校の部活動を選んで、日程と会場を提案し、申し込む"""
    form_class = MatchRequestForm
    template_name = "matching/match_request.html"
    success_url = reverse_lazy("sent_matches")

    def get_clubs(self):
        if not hasattr(self, "_clubs"):
            clubs = Club.objects.select_related("school__area", "sport")
            # 申込側は自校の部活動だけ
            applicant = get_object_or_404(
                clubs, pk=self.kwargs["club_pk"], school=self.request.user.school
            )
            # 相手側は、同じ競技・同じ区分で、別の学校の部活動だけ
            opponent = get_object_or_404(
                clubs.exclude(school=applicant.school),
                pk=self.kwargs["opponent_pk"],
                sport=applicant.sport,
                gender=applicant.gender,
            )
            self._clubs = (applicant, opponent)
        return self._clubs

    def get_initial(self):
        # 日程調整の画面から「この日程で申し込む」で来たときは、その日付を入れておく
        initial = super().get_initial()
        date = self.request.GET.get("date", "")
        if date:
            initial["date"] = date
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        applicant, opponent = self.get_clubs()
        kwargs["applicant"] = applicant
        kwargs["opponent"] = opponent
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        applicant, opponent = self.get_clubs()

        # 共通の希望日
        mine = {
            a.date: a
            for a in Availability.objects.filter(club=applicant, date__gte=timezone.localdate())
        }
        theirs = Availability.objects.filter(club=opponent, date__in=list(mine)).order_by("date")

        context["applicant"] = applicant
        context["opponent"] = opponent
        context["common_dates"] = [
            {"date": a.date, "my_host": mine[a.date].can_host, "their_host": a.can_host}
            for a in theirs
        ]
        context["candidates"] = context["form"].candidates
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "練習試合を申し込みました。相手校の承認をお待ちください。")
        return response


class SentMatchListView(TeacherRequiredMixin, ListView):
    """申し込んだ試合の一覧"""
    template_name = "matching/sent_list.html"
    context_object_name = "matches"

    def get_queryset(self):
        return (
            PracticeMatch.objects.filter(applicant_club__school=self.request.user.school)
            .select_related(
                "applicant_club__school", "opponent_club__school",
                "opponent_club__sport", "facility",
            )
            .order_by("-created_at")
        )


class ReceivedMatchListView(TeacherRequiredMixin, ListView):
    """届いた申し込みの一覧"""
    template_name = "matching/received_list.html"
    context_object_name = "matches"

    def get_queryset(self):
        return (
            PracticeMatch.objects.filter(opponent_club__school=self.request.user.school)
            .select_related(
                "applicant_club__school", "applicant_club__sport",
                "opponent_club__school", "facility",
            )
            .order_by("-created_at")
        )


class MatchWithdrawView(TeacherRequiredMixin, View):
    """申し込みを取り下げる（申込側だけ、申込中のものだけ）"""

    def post(self, request, pk):
        match = get_object_or_404(
            PracticeMatch, pk=pk, applicant_club__school=request.user.school
        )
        if match.status != PracticeMatch.Status.PENDING:
            messages.error(request, "承認または辞退された申し込みは、取り下げられません。")
        else:
            match.delete()
            messages.success(request, "申し込みを取り下げました。")
        return redirect("sent_matches")


class MatchApproveView(TeacherRequiredMixin, View):
    """届いた申し込みを承認する。承認すると練習試合が確定する"""

    def post(self, request, pk):
        match = get_object_or_404(
            PracticeMatch, pk=pk, opponent_club__school=request.user.school
        )
        if match.status != PracticeMatch.Status.PENDING:
            messages.error(request, "この申し込みは、すでに処理されています。")
        elif match.has_conflict():
            messages.error(
                request,
                "この日は、どちらかの部活動に、すでに別の練習試合が確定しているため、承認できません。",
            )
        else:
            match.status = PracticeMatch.Status.CONFIRMED
            match.decided_at = timezone.now()
            match.save(update_fields=["status", "decided_at"])
            messages.success(request, "練習試合が確定しました。")
        return redirect("received_matches")


class MatchDeclineView(TeacherRequiredMixin, View):
    """届いた申し込みを辞退する"""

    def post(self, request, pk):
        match = get_object_or_404(
            PracticeMatch, pk=pk, opponent_club__school=request.user.school
        )
        if match.status != PracticeMatch.Status.PENDING:
            messages.error(request, "この申し込みは、すでに処理されています。")
        else:
            match.status = PracticeMatch.Status.DECLINED
            match.decided_at = timezone.now()
            match.save(update_fields=["status", "decided_at"])
            messages.success(request, "申し込みを辞退しました。")
        return redirect("received_matches")


# ---------- 共通：自校が関わる練習試合 ----------

def school_matches(school):
    """自校が申込側・相手側のどちらかになっている練習試合"""
    return PracticeMatch.objects.filter(
        Q(applicant_club__school=school) | Q(opponent_club__school=school)
    ).select_related(
        "applicant_club__school", "applicant_club__sport",
        "opponent_club__school", "opponent_club__sport",
        "facility", "result",
    )


def match_row(match, school, today):
    """一覧に表示するための、自校から見た試合の情報"""
    result = getattr(match, "result", None)
    row = {
        "match": match,
        "my_club": match.my_club(school),
        "other_club": match.other_club(school),
        "result": result,
        "can_record": match.date <= today,
    }
    if result:
        row["my_score"], row["their_score"] = result.scores_for(school)
        row["outcome"] = result.outcome_for(school)
    return row


# ---------- 予定試合一覧 ----------

class PlannedMatchListView(TeacherRequiredMixin, TemplateView):
    """確定した練習試合の一覧。これからの試合と、終わった試合に分けて表示する"""
    template_name = "matching/planned_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        today = timezone.localdate()
        confirmed = school_matches(school).filter(status=PracticeMatch.Status.CONFIRMED)

        context["upcoming"] = [
            match_row(m, school, today)
            for m in confirmed.filter(date__gte=today).order_by("date")
        ]
        context["past"] = [
            match_row(m, school, today)
            for m in confirmed.filter(date__lt=today).order_by("-date")
        ]
        return context


# ---------- 試合結果 ----------

class MatchResultListView(TeacherRequiredMixin, TemplateView):
    """登録済みの試合結果と、結果がまだ登録されていない試合の一覧"""
    template_name = "matching/result_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        today = timezone.localdate()
        finished = school_matches(school).filter(
            status=PracticeMatch.Status.CONFIRMED, date__lte=today
        ).order_by("-date")

        rows = [match_row(m, school, today) for m in finished]
        results = [r for r in rows if r["result"]]
        context["results"] = results
        context["unrecorded"] = [r for r in rows if not r["result"]]
        context["record"] = {
            "win": sum(1 for r in results if r["outcome"] == "win"),
            "lose": sum(1 for r in results if r["outcome"] == "lose"),
            "draw": sum(1 for r in results if r["outcome"] == "draw"),
        }
        return context


class MatchResultEditView(TeacherRequiredMixin, View):
    """試合結果の登録・編集（1つの試合に1つの結果。どちらの学校からでも編集できる）"""
    template_name = "matching/result_form.html"

    def get_match(self):
        return get_object_or_404(
            school_matches(self.request.user.school),
            pk=self.kwargs["pk"], status=PracticeMatch.Status.CONFIRMED,
        )

    def show_form(self, match, form):
        school = self.request.user.school
        return render(self.request, self.template_name, {
            "match": match,
            "form": form,
            "my_club": match.my_club(school),
            "other_club": match.other_club(school),
            "is_edit": form.instance.pk is not None,
        })

    def get(self, request, pk):
        match = self.get_match()
        if match.date > timezone.localdate():
            messages.error(request, "試合結果は、試合日以降に登録できます。")
            return redirect("planned_matches")
        result = getattr(match, "result", None)
        return self.show_form(match, MatchResultForm(instance=result, match=match))

    def post(self, request, pk):
        match = self.get_match()
        if match.date > timezone.localdate():
            messages.error(request, "試合結果は、試合日以降に登録できます。")
            return redirect("planned_matches")
        result = getattr(match, "result", None)
        form = MatchResultForm(request.POST, instance=result, match=match)
        if not form.is_valid():
            return self.show_form(match, form)
        saved = form.save(commit=False)
        saved.updated_by = request.user.school
        saved.save()
        messages.success(request, "試合結果を保存しました。")
        return redirect("match_results")


class MatchResultDeleteView(TeacherRequiredMixin, View):
    """試合結果を削除する（試合そのものは残る）"""

    def post(self, request, pk):
        school = request.user.school
        result = get_object_or_404(
            MatchResult.objects.filter(
                Q(match__applicant_club__school=school) | Q(match__opponent_club__school=school)
            ),
            pk=pk,
        )
        result.delete()
        messages.success(request, "試合結果を削除しました。")
        return redirect("match_results")


# ---------- メッセージ ----------

class MessageListView(TeacherRequiredMixin, TemplateView):
    """会話（相手校ごと）の一覧と、新しく会話を始められる学校の一覧"""
    template_name = "matching/message_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school

        all_messages = (
            Message.objects.filter(Q(sender=school) | Q(receiver=school))
            .select_related("sender__area", "receiver__area")
            .order_by("-created_at")
        )
        conversations = {}
        for m in all_messages:
            other = m.receiver if m.sender_id == school.pk else m.sender
            conv = conversations.setdefault(other.pk, {
                "school": other, "last_message": m, "unread": 0,
                "last_is_mine": m.sender_id == school.pk,
            })
            if m.receiver_id == school.pk and not m.is_read:
                conv["unread"] += 1

        # 練習試合でやり取りのある学校を、新しい会話の候補の先頭に出す
        partner_ids = {m.other_club(school).school_id for m in school_matches(school)}
        others = (
            School.objects.exclude(pk=school.pk)
            .exclude(pk__in=list(conversations))
            .select_related("area")
        )
        context["conversations"] = list(conversations.values())
        context["available_schools"] = sorted(
            others,
            key=lambda s: (s.pk not in partner_ids, s.area.name if s.area else "", s.name),
        )
        context["partner_ids"] = partner_ids
        return context


class MessageRoomView(TeacherRequiredMixin, View):
    """ある学校との会話の画面。開くと、届いたメッセージは既読になる"""
    template_name = "matching/message_room.html"

    def get_other(self):
        return get_object_or_404(
            School.objects.exclude(pk=self.request.user.school_id).select_related("area"),
            pk=self.kwargs["school_pk"],
        )

    def show_room(self, other, form):
        school = self.request.user.school
        # 2校のあいだの、これからの練習試合（申込中・確定）を会話の上に表示する
        related = (
            school_matches(school)
            .filter(Q(applicant_club__school=other) | Q(opponent_club__school=other))
            .filter(
                status__in=[PracticeMatch.Status.PENDING, PracticeMatch.Status.CONFIRMED],
                date__gte=timezone.localdate(),
            )
            .order_by("date")
        )
        return render(self.request, self.template_name, {
            "other": other,
            "thread": Message.between(school, other).select_related("sender"),
            "form": form,
            "related_matches": related,
        })

    def get(self, request, school_pk):
        other = self.get_other()
        Message.objects.filter(
            sender=other, receiver=request.user.school, is_read=False
        ).update(is_read=True)
        return self.show_room(other, MessageForm())

    def post(self, request, school_pk):
        other = self.get_other()
        form = MessageForm(request.POST)
        if not form.is_valid():
            return self.show_room(other, form)
        message = form.save(commit=False)
        message.sender = request.user.school
        message.receiver = other
        message.save()
        return redirect(reverse("message_room", args=[other.pk]) + "#latest")


# ---------- 日程調整 ----------

class ScheduleView(TeacherRequiredMixin, TemplateView):
    """自校の部活動と相手校の部活動を選び、共通の希望日を確認して申し込む"""
    template_name = "matching/schedule.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        today = timezone.localdate()

        my_clubs = (
            Club.objects.filter(school=school)
            .select_related("sport")
            .order_by("sport__name", "gender")
        )
        context["my_clubs"] = my_clubs

        club_param = self.request.GET.get("club", "")
        club = my_clubs.filter(pk=club_param).first() if club_param.isdigit() else None
        context["selected_club"] = club
        if club is None:
            return context

        # 相手の候補：同じ競技・同じ区分で、別の学校の部活動
        opponent_clubs = (
            Club.objects.filter(sport=club.sport, gender=club.gender)
            .exclude(school=school)
            .select_related("school__area", "sport")
            .order_by("school__name")
        )
        context["opponent_clubs"] = opponent_clubs
        context["my_date_count"] = Availability.objects.filter(club=club, date__gte=today).count()

        opp_param = self.request.GET.get("opponent", "")
        opponent = opponent_clubs.filter(pk=opp_param).first() if opp_param.isdigit() else None
        context["selected_opponent"] = opponent
        if opponent is None:
            return context

        mine = {a.date: a for a in Availability.objects.filter(club=club, date__gte=today)}
        theirs = {a.date: a for a in Availability.objects.filter(club=opponent, date__gte=today)}

        # この2つの部活動のあいだで、すでに申込中・確定の試合がある日
        pair_matches = PracticeMatch.objects.filter(
            Q(applicant_club=club, opponent_club=opponent)
            | Q(applicant_club=opponent, opponent_club=club),
            status__in=[PracticeMatch.Status.PENDING, PracticeMatch.Status.CONFIRMED],
        )
        pair_status = {m.date: m.get_status_display() for m in pair_matches}

        # どちらかの部活動に、別の相手との試合が確定している日
        busy_dates = set(
            PracticeMatch.objects.filter(status=PracticeMatch.Status.CONFIRMED, date__gte=today)
            .filter(Q(applicant_club__in=[club, opponent]) | Q(opponent_club__in=[club, opponent]))
            .exclude(pk__in=pair_matches.values("pk"))
            .values_list("date", flat=True)
        )

        context["candidates"] = [
            {
                "date": d,
                "my_host": mine[d].can_host,
                "their_host": theirs[d].can_host,
                "requested": pair_status.get(d),
                "busy": d in busy_dates,
            }
            for d in sorted(set(mine) & set(theirs))
        ]
        context["their_date_count"] = len(theirs)
        return context
from django.contrib import messages
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.generic import CreateView, ListView, TemplateView, View

from accounts.context_processors import teacher_badges
from accounts.models import User
from accounts.views import TeacherRequiredMixin
from schools.distance import distance_km
from schools.forms import ClubLevelForm
from schools.models import Area, Club
from .forms import (
    MAX_CANDIDATES, AvailabilityForm, ConversationStartForm, MatchRequestForm,
    MatchResultForm, MessageForm, missing_host_dates,
)
from .live import live_versions
from .strength import FIT_ORDER, estimate, fit_for, head_to_head, recent_results
from .venues import choice_groups, parse_venue, venue_candidates, venue_choices
from .models import (
    Availability, CandidateDate, Conversation, MatchResult, Message, PracticeMatch,
)

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
    """対戦相手検索。希望する対戦レベル・共通の希望日・地域・距離から、おすすめ順に並べる"""
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
            .select_related("sport", "school")
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

        # 希望する対戦レベル：指定がなければ、部活動に設定したもの
        level_param = self.request.GET.get("level", "")
        if level_param not in Club.DesiredLevel.values:
            level_param = club.desired_level if club else Club.DesiredLevel.SAME

        context.update({
            "my_clubs": my_clubs,
            "areas": Area.objects.order_by("name"),
            "level_choices": Club.DesiredLevel.choices,
            "selected_club": club,
            "selected_area": selected_area,
            "selected_level": level_param,
            "selected_level_label": Club.DesiredLevel(level_param).label,
        })
        if club is None:
            return context

        # 相手の候補：同じ競技・同じ区分で、別の学校の部活動
        opponents = list(
            Club.objects.filter(sport=club.sport, gender=club.gender)
            .exclude(school=school)
            .select_related("school__area", "sport")
        )
        if selected_area:
            opponents = [o for o in opponents if str(o.school.area_id) == selected_area]

        context["rows"] = opponent_rows(club, opponents, level_param, self.get_distance)
        context["has_my_dates"] = Availability.objects.filter(
            club=club, date__gte=timezone.localdate()).exists()
        context["recommended_count"] = sum(1 for r in context["rows"] if r["fit"] == "match")
        return context


def opponent_rows(club, opponents, desired_level, get_distance):
    """相手の部活動ごとに、共通の希望日・推定したレベル・おすすめかどうかをまとめ、おすすめ順に並べる"""
    school = club.school
    today = timezone.localdate()

    # 自校の、これから先の希望日（日付 → 希望日のデータ）
    my_dates = {a.date: a for a in Availability.objects.filter(club=club, date__gte=today)}
    common = {}
    if my_dates:
        for a in (Availability.objects.filter(club__in=opponents, date__in=list(my_dates))
                  .order_by("date")):
            common.setdefault(a.club_id, []).append({
                "date": a.date,
                "my_host": my_dates[a.date].can_host,
                "their_host": a.can_host,
            })

    results = recent_results([club, *opponents])
    records = head_to_head(club, opponents)
    my_results = results.get(club.pk, [])

    rows = []
    for opp in opponents:
        level = estimate(club, opp, my_results, results.get(opp.pk, []), records.get(opp.pk))
        rows.append({
            "club": opp,
            "school": opp.school,
            "distance": get_distance(school, opp.school),
            "common": common.get(opp.pk, []),
            "level": level,
            "fit": fit_for(level["relation"], desired_level),
        })

    # 並び順：希望のレベルに合う → 未判定 → 合わない。その中で、共通の希望日がある → 同じ地域 → 近い → 学校名
    def sort_key(row):
        same_area = school.area_id is not None and row["school"].area_id == school.area_id
        distance = row["distance"] if row["distance"] is not None else 99999
        return (FIT_ORDER[row["fit"]], not row["common"], not same_area, distance, row["school"].name)

    rows.sort(key=sort_key)
    return rows


class ClubLevelView(TeacherRequiredMixin, View):
    """部活動の「希望する対戦レベル」を保存する（対戦相手検索の画面から）。
    保存したレベルは、次に検索するとき最初から選ばれる"""

    def post(self, request, club_pk):
        club = get_object_or_404(Club, pk=club_pk, school=request.user.school)
        form = ClubLevelForm(request.POST, instance=club)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"「{club.name}」の希望する対戦レベルを「{club.get_desired_level_display()}」にしました。")
        else:
            messages.error(request, "希望する対戦レベルを選び直してください。")
        return redirect(f"{reverse('opponent_search')}?club={club.pk}")


class OpponentDetailView(TeacherRequiredMixin, TemplateView):
    """対戦相手の詳細。学校・部活動の情報、レベルの判定理由、大会成績、過去の対戦、共通の希望日"""
    template_name = "matching/opponent_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clubs = Club.objects.select_related("school__area", "sport")
        club = get_object_or_404(clubs, pk=self.kwargs["club_pk"], school=self.request.user.school)
        opponent = get_object_or_404(
            clubs.exclude(school=club.school), pk=self.kwargs["opponent_pk"],
            sport=club.sport, gender=club.gender,
        )
        row = opponent_rows(club, [opponent], club.desired_level, OpponentSearchView.get_distance)[0]

        today = timezone.localdate()
        past_matches = [
            match_row(m, club.school, today)
            for m in school_matches(club.school).filter(
                status=PracticeMatch.Status.CONFIRMED, date__lt=today)
            .filter(Q(applicant_club=club, opponent_club=opponent)
                    | Q(applicant_club=opponent, opponent_club=club))
            .order_by("-date")[:10]
        ]
        context.update({
            "club": club,
            "opponent": opponent,
            "row": row,
            "tournament_results": opponent.tournament_results.all()[:10],
            "past_matches": past_matches,
            "their_dates": Availability.objects.filter(club=opponent, date__gte=today)[:20],
            "school_facilities": opponent.school.facilities.filter(sports=opponent.sport),
        })
        return context

# ---------- 練習試合の申し込み ----------

class MatchRequestView(TeacherRequiredMixin, CreateView):
    """相手校の部活動を選んで、候補日（複数）と会場を提案し、申し込む"""
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        applicant, opponent = self.get_clubs()
        kwargs["applicant"] = applicant
        kwargs["opponent"] = opponent
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        applicant, opponent = self.get_clubs()
        form = context["form"]

        # 共通の希望日（チェックボックスで選べるようにする）
        mine = {
            a.date: a
            for a in Availability.objects.filter(club=applicant, date__gte=timezone.localdate())
        }
        theirs = Availability.objects.filter(club=opponent, date__in=list(mine)).order_by("date")
        common = [
            {"date": a.date, "my_host": mine[a.date].can_host, "their_host": a.can_host}
            for a in theirs
        ]

        # チェック済みにする日：送信した内容、または日程調整の画面から来たときの ?date=
        if form.is_bound:
            checked = set(form.data.getlist("candidate_dates"))
        else:
            checked = set(self.request.GET.getlist("date"))
        common_iso = {c["date"].isoformat() for c in common}
        for c in common:
            c["checked"] = c["date"].isoformat() in checked
        # 共通の希望日以外で入力された日は、「その他の候補日」の欄に戻す
        others = sorted(d for d in checked if d not in common_iso)

        context.update({
            "applicant": applicant,
            "opponent": opponent,
            "common_dates": common,
            "other_dates": others + [""] * max(0, 3 - len(others)),
            "candidates": form.candidates,
            "max_candidates": MAX_CANDIDATES,
            "today": timezone.localdate(),
        })
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "練習試合を申し込みました。相手校が候補日を選ぶと確定します。")
        return response


def proposal_queryset():
    return PracticeMatch.objects.select_related(
        "applicant_club__school", "applicant_club__sport",
        "opponent_club__school", "opponent_club__sport",
        "facility", "conversation",
    ).prefetch_related("candidates")


class SentMatchListView(TeacherRequiredMixin, ListView):
    """申し込んだ試合（自校から送った申し込み）の一覧"""
    template_name = "matching/sent_list.html"
    context_object_name = "proposals"

    def get_queryset(self):
        return proposal_queryset().filter(
            applicant_club__school=self.request.user.school
        ).order_by("-created_at")


class ReceivedMatchListView(TeacherRequiredMixin, ListView):
    """届いた申し込みの一覧。返事待ちのものを先に表示する"""
    template_name = "matching/received_list.html"
    context_object_name = "proposals"

    def get_queryset(self):
        return proposal_queryset().filter(opponent_club__school=self.request.user.school)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proposals = list(context["proposals"])
        today = timezone.localdate()
        for p in proposals:
            p.open_candidates = [c for c in p.candidates.all() if c.date >= today]
            if p.status == PracticeMatch.Status.PENDING:
                # 確定するときに選ぶ会場（申し込んだ側が選んだ会場を、最初から選んでおく）
                rows = venue_candidates(p.applicant_club, p.opponent_club)
                p.venue_groups = choice_groups(venue_choices(p.applicant_club, p.opponent_club, rows))
                p.selected_venue = "" if p.venue_kind == PracticeMatch.VenueKind.UNDECIDED else p.venue_value
        context["pending"] = [p for p in proposals if p.status == PracticeMatch.Status.PENDING]
        context["answered"] = [p for p in proposals if p.status != PracticeMatch.Status.PENDING]
        return context


class MatchWithdrawView(TeacherRequiredMixin, View):
    """申し込みを取り下げる（申込側だけ、申込中のものだけ）"""

    def post(self, request, pk):
        match = get_object_or_404(
            PracticeMatch, pk=pk, applicant_club__school=request.user.school
        )
        if match.status != PracticeMatch.Status.PENDING:
            messages.error(request, "確定またはお断りされた申し込みは、取り下げられません。")
        else:
            match.delete()
            messages.success(request, "申し込みを取り下げました。")
        return redirect("sent_matches")


class MatchRespondView(TeacherRequiredMixin, View):
    """届いた申し込みに返事をする。候補日を1日選んで確定するか、お断りする"""

    def post(self, request, pk):
        match = get_object_or_404(
            PracticeMatch, pk=pk, opponent_club__school=request.user.school
        )
        if match.status != PracticeMatch.Status.PENDING:
            messages.error(request, "この申し込みは、すでに返事をしています。")
            return redirect("received_matches")

        if request.POST.get("action") == "reject":
            match.status = PracticeMatch.Status.DECLINED
            match.decided_at = timezone.now()
            match.save(update_fields=["status", "decided_at"])
            messages.success(request, "申し込みをお断りしました。")
            return redirect("received_matches")

        candidate_id = request.POST.get("candidate_date_id", "")
        candidate = (
            match.selectable_candidates().filter(pk=candidate_id).first()
            if candidate_id.isdigit() else None
        )
        rows = venue_candidates(match.applicant_club, match.opponent_club)
        venue = parse_venue(request.POST.get("venue", ""), rows)

        if candidate is None:
            messages.error(request, "確定する候補日を選んでください。")
            return redirect("received_matches")
        if venue is None:
            messages.error(request, "試合会場を選んでください。")
            return redirect("received_matches")
        if match.has_conflict(candidate.date):
            messages.error(
                request,
                f"{candidate.date.month}/{candidate.date.day} は、どちらかの部活動に別の練習試合が"
                "確定しているため、選べません。ほかの候補日を選んでください。",
            )
            return redirect("received_matches")

        match.venue_kind, match.facility = venue
        host = match.host_club
        if host is not None and missing_host_dates(host, [candidate.date]):
            who = "自校" if host == match.opponent_club else "相手校"
            messages.error(
                request,
                f"{candidate.date.month}/{candidate.date.day} は、{who}が「受け入れ可」になっていないため、"
                f"{match.venue_name} では実施できません。ほかの会場を選んでください。",
            )
            return redirect("received_matches")

        match.date = candidate.date
        match.status = PracticeMatch.Status.CONFIRMED
        match.decided_at = timezone.now()
        match.save(update_fields=["date", "status", "decided_at", "venue_kind", "facility"])
        messages.success(
            request,
            f"{candidate.date.month}/{candidate.date.day}・{match.venue_name} で練習試合が確定しました。")
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
        "can_record": match.date is not None and match.date <= today,
        "my_score": None,
        "their_score": None,
        "outcome": None,
        "my_notes": "",
    }
    if result:
        row["my_score"], row["their_score"] = result.scores_for(school)
        row["my_notes"], _ = result.notes_for(school)
        row["outcome"] = result.outcome_for(school)
    row["needs_my_score"] = row["can_record"] and row["my_score"] is None
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
    """試合結果の一覧。自校の得点が未入力の試合は、別にまとめて表示する"""
    template_name = "matching/result_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school
        today = timezone.localdate()
        finished = school_matches(school).filter(
            status=PracticeMatch.Status.CONFIRMED, date__lte=today
        ).order_by("-date")

        rows = [match_row(m, school, today) for m in finished]
        context["unrecorded"] = [r for r in rows if r["my_score"] is None]
        context["results"] = [r for r in rows if r["my_score"] is not None]
        outcomes = [r["outcome"] for r in context["results"]]
        context["record"] = {
            "win": outcomes.count("win"),
            "lose": outcomes.count("lose"),
            "draw": outcomes.count("draw"),
        }
        return context


class MatchResultEditView(TeacherRequiredMixin, View):
    """自校の得点・備考の登録と編集（相手校の得点は、相手校が登録する）"""
    template_name = "matching/result_form.html"

    def get_match(self):
        return get_object_or_404(
            school_matches(self.request.user.school),
            pk=self.kwargs["pk"], status=PracticeMatch.Status.CONFIRMED,
        )

    def show_form(self, match, form):
        school = self.request.user.school
        result = getattr(match, "result", None)
        their_score, their_notes = (None, "")
        if result:
            _, their_score = result.scores_for(school)
            _, their_notes = result.notes_for(school)
        return render(self.request, self.template_name, {
            "match": match,
            "form": form,
            "my_club": match.my_club(school),
            "other_club": match.other_club(school),
            "their_score": their_score,
            "their_notes": their_notes,
        })

    def check_date(self, request, match):
        if match.date > timezone.localdate():
            messages.error(request, "試合結果は、試合日以降に登録できます。")
            return redirect("planned_matches")
        return None

    def get(self, request, pk):
        match = self.get_match()
        if (response := self.check_date(request, match)):
            return response
        initial = {}
        result = getattr(match, "result", None)
        if result:
            score, _ = result.scores_for(request.user.school)
            notes, _ = result.notes_for(request.user.school)
            initial = {"my_score": score, "my_notes": notes}
        return self.show_form(match, MatchResultForm(initial=initial))

    def post(self, request, pk):
        match = self.get_match()
        if (response := self.check_date(request, match)):
            return response
        form = MatchResultForm(request.POST)
        if not form.is_valid():
            return self.show_form(match, form)
        result, _ = MatchResult.objects.get_or_create(match=match)
        result.match = match
        result.set_mine(request.user.school, form.cleaned_data["my_score"], form.cleaned_data["my_notes"])
        result.save()
        messages.success(request, "自校の試合結果を保存しました。")
        return redirect("match_results")


class MatchResultDeleteView(TeacherRequiredMixin, View):
    """自校の得点・備考を取り消す（相手校の入力は残る）"""

    def post(self, request, pk):
        school = request.user.school
        result = get_object_or_404(
            MatchResult.objects.select_related("match__applicant_club").filter(
                Q(match__applicant_club__school=school) | Q(match__opponent_club__school=school)
            ),
            pk=pk,
        )
        result.set_mine(school, None, "")
        if result.applicant_score is None and result.opponent_score is None \
                and not result.applicant_notes and not result.opponent_notes:
            result.delete()
        else:
            result.save()
        messages.success(request, "自校の試合結果を取り消しました。")
        return redirect("match_results")


# ---------- メッセージ ----------

def conversation_row(conversation, school):
    """会話の一覧に表示するための、自校から見た会話の情報"""
    return {
        "conversation": conversation,
        "school": conversation.other_school(school),
        "my_club": conversation.my_club(school),
        "other_club": conversation.other_club(school),
        "kind": conversation.kind,
        "kind_label": conversation.get_kind_display(),
    }


class MessageListView(TeacherRequiredMixin, TemplateView):
    """会話の一覧と、自由メッセージを始めるフォーム"""
    template_name = "matching/message_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.request.user.school

        conversations = (
            Conversation.for_school(school)
            .filter(last_message_at__isnull=False)
            .select_related("school_a", "school_b", "club_a__sport", "club_b__sport", "match")
        )
        unread = {}
        for conv_id in Message.unread_for(school).values_list("conversation_id", flat=True):
            unread[conv_id] = unread.get(conv_id, 0) + 1
        last_messages = {}
        for m in Message.objects.filter(conversation__in=conversations).order_by("created_at"):
            last_messages[m.conversation_id] = m

        rows = []
        for conv in conversations:
            row = conversation_row(conv, school)
            row["last_message"] = last_messages.get(conv.pk)
            row["last_is_mine"] = row["last_message"] and row["last_message"].sender_id == school.pk
            row["unread"] = unread.get(conv.pk, 0)
            rows.append(row)
        context["conversations"] = rows
        context["start_form"] = kwargs.get("start_form") or ConversationStartForm(school=school)
        return context


class ConversationStartView(TeacherRequiredMixin, View):
    """自校と相手校の部活動を選んで、自由メッセージの会話を開く（すでにあればそれを開く）"""

    def post(self, request):
        form = ConversationStartForm(request.POST, school=request.user.school)
        if not form.is_valid():
            view = MessageListView()
            view.setup(request)
            return render(request, MessageListView.template_name,
                          view.get_context_data(start_form=form))
        conversation = Conversation.free_between(
            form.cleaned_data["my_club"], form.cleaned_data["opponent_club"])
        return redirect("message_room", pk=conversation.pk)


class MessageRoomView(TeacherRequiredMixin, View):
    """会話の画面。開くと、届いたメッセージは既読になる"""
    template_name = "matching/message_room.html"

    def get_conversation(self):
        conversation = get_object_or_404(
            Conversation.objects.select_related(
                "school_a__area", "school_b__area", "club_a__sport", "club_b__sport",
                "match__applicant_club__school", "match__opponent_club__school", "match__facility",
            ),
            pk=self.kwargs["pk"],
        )
        if not conversation.includes(self.request.user.school):
            raise Http404
        return conversation

    def show_room(self, conversation, form):
        school = self.request.user.school
        context = conversation_row(conversation, school)
        context.update({
            "thread": conversation.messages.select_related("sender"),
            "form": form,
            "match": conversation.match,
        })
        if conversation.match:
            context["match_candidates"] = list(conversation.match.candidates.all())
        return render(self.request, self.template_name, context)

    def get(self, request, pk):
        conversation = self.get_conversation()
        conversation.messages.filter(is_read=False).exclude(
            sender=request.user.school).update(is_read=True)
        return self.show_room(conversation, MessageForm())

    def post(self, request, pk):
        conversation = self.get_conversation()
        form = MessageForm(request.POST)
        if not form.is_valid():
            return self.show_room(conversation, form)
        message = form.save(commit=False)
        message.conversation = conversation
        message.sender = request.user.school
        message.save()
        return redirect(reverse("message_room", args=[conversation.pk]) + "#latest")


class MatchConversationView(TeacherRequiredMixin, View):
    """申し込みの会話を開く（古い申し込みで会話がまだなければ、ここで作る）"""

    def get(self, request, pk):
        match = get_object_or_404(
            school_matches(request.user.school).select_related(None), pk=pk)
        return redirect("message_room", pk=Conversation.for_match(match).pk)


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

        # この2つの部活動のあいだで、申し込み中の候補日・確定した日
        pair = PracticeMatch.objects.filter(
            Q(applicant_club=club, opponent_club=opponent)
            | Q(applicant_club=opponent, opponent_club=club)
        )
        pair_status = {
            d: "申込中" for d in CandidateDate.objects.filter(
                match__in=pair.filter(status=PracticeMatch.Status.PENDING)
            ).values_list("date", flat=True)
        }
        pair_status.update({
            d: "確定" for d in pair.filter(status=PracticeMatch.Status.CONFIRMED)
            .values_list("date", flat=True)
        })

        # どちらかの部活動に、別の相手との試合が確定している日
        busy_dates = set(
            PracticeMatch.objects.filter(status=PracticeMatch.Status.CONFIRMED, date__gte=today)
            .filter(Q(applicant_club__in=[club, opponent]) | Q(opponent_club__in=[club, opponent]))
            .exclude(pk__in=pair.values("pk"))
            .values_list("date", flat=True)
        )

        candidates = [
            {
                "date": d,
                "my_host": mine[d].can_host,
                "their_host": theirs[d].can_host,
                "requested": pair_status.get(d),
                "busy": d in busy_dates,
            }
            for d in sorted(set(mine) & set(theirs))
        ]
        context["candidates"] = candidates
        context["their_date_count"] = len(theirs)

        # 申し込める日をまとめて候補日にして、申し込み画面へ進むリンク
        open_dates = [c["date"].isoformat() for c in candidates if not c["requested"] and not c["busy"]]
        if open_dates:
            query = "&".join(f"date={d}" for d in open_dates[:MAX_CANDIDATES])
            context["apply_all_url"] = (
                reverse("match_request", args=[club.pk, opponent.pk]) + "?" + query)
        return context


# ---------- 画面の自動更新 ----------

@never_cache
def live_updates(request):
    """サイドバーの件数と、データの変化の目印を返す（画面が数秒ごとに問い合わせる）"""
    user = request.user
    if not user.is_authenticated or user.role != User.Role.TEACHER or user.school_id is None:
        # ログインが切れた・別のアカウントに切り替わったときは、画面側が問い合わせをやめる
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse({
        "user": user.pk,
        "badges": teacher_badges(user.school),
        "versions": live_versions(user.school),
    })

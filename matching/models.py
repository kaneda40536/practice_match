from django.db import models
from django.db.models import Q
from django.utils import timezone

from facilities.models import Facility
from schools.models import Club, School


class Availability(models.Model):
    """部活動ごとの、練習試合をしたい日（希望日）"""

    club = models.ForeignKey(Club, on_delete=models.CASCADE, verbose_name="部活動")
    date = models.DateField("日付")
    can_host = models.BooleanField("自校で受け入れ可", default=False)

    class Meta:
        unique_together = ("club", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.club} {self.date}"


class PracticeMatch(models.Model):
    """練習試合の申し込み。

    申込側が候補日（CandidateDate）を複数送り、相手側がその中から1日を選ぶと確定する。
    確定した日は date に入る（確定するまでは空）。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "申込中"
        CONFIRMED = "confirmed", "確定"
        DECLINED = "declined", "お断り"

    class VenueKind(models.TextChoices):
        APPLICANT = "applicant", "申込校"
        OPPONENT = "opponent", "相手校"
        FACILITY = "facility", "施設"
        UNDECIDED = "undecided", "未定"

    applicant_club = models.ForeignKey(
        Club, on_delete=models.CASCADE, related_name="sent_matches",
        verbose_name="申込側の部活動",
    )
    opponent_club = models.ForeignKey(
        Club, on_delete=models.CASCADE, related_name="received_matches",
        verbose_name="相手側の部活動",
    )
    date = models.DateField("確定した試合日", null=True, blank=True)
    venue_kind = models.CharField("会場の種類", max_length=10, choices=VenueKind.choices)
    facility = models.ForeignKey(
        Facility, null=True, blank=True, on_delete=models.PROTECT,
        verbose_name="会場の施設",
    )
    message = models.TextField("備考・連絡事項", blank=True)
    status = models.CharField(
        "状態", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField("申込日時", auto_now_add=True)
    decided_at = models.DateTimeField("確定・お断りの日時", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.applicant_club} → {self.opponent_club}（{self.get_status_display()}）"

    @property
    def venue_name(self):
        """会場の名前（施設名、または学校名）"""
        if self.venue_kind == self.VenueKind.FACILITY and self.facility:
            return self.facility.display_name
        if self.venue_kind == self.VenueKind.APPLICANT:
            return self.applicant_club.school.name
        if self.venue_kind == self.VenueKind.OPPONENT:
            return self.opponent_club.school.name
        return "未定（相手校が決めます）"

    @property
    def venue_value(self):
        """会場の選択肢の値（matching.venues.venue_choices と同じ形）"""
        if self.venue_kind == self.VenueKind.FACILITY and self.facility_id:
            return f"facility:{self.facility_id}"
        return self.venue_kind

    @property
    def host_club(self):
        """学校で実施する場合の、会場になる学校の部活動（学校以外・未定なら None）"""
        if self.venue_kind == self.VenueKind.APPLICANT:
            return self.applicant_club
        if self.venue_kind == self.VenueKind.OPPONENT:
            return self.opponent_club
        if self.venue_kind == self.VenueKind.FACILITY and self.facility and self.facility.school_id:
            if self.facility.school_id == self.applicant_club.school_id:
                return self.applicant_club
            if self.facility.school_id == self.opponent_club.school_id:
                return self.opponent_club
        return None

    def selectable_candidates(self):
        """相手側が選べる候補日（今日以降のもの）"""
        return self.candidates.filter(date__gte=timezone.localdate())

    def has_conflict(self, date):
        """どちらかの部活動に、その日に確定済みの試合が別にあるか"""
        club_ids = [self.applicant_club_id, self.opponent_club_id]
        return (
            PracticeMatch.objects.filter(status=self.Status.CONFIRMED, date=date)
            .exclude(pk=self.pk)
            .filter(Q(applicant_club_id__in=club_ids) | Q(opponent_club_id__in=club_ids))
            .exists()
        )

    def other_club(self, school):
        """school から見た、相手側の部活動"""
        if self.applicant_club.school_id == school.pk:
            return self.opponent_club
        return self.applicant_club

    def my_club(self, school):
        """school から見た、自校側の部活動"""
        if self.applicant_club.school_id == school.pk:
            return self.applicant_club
        return self.opponent_club


class CandidateDate(models.Model):
    """申し込みの候補日"""

    match = models.ForeignKey(
        PracticeMatch, on_delete=models.CASCADE, related_name="candidates",
        verbose_name="申し込み",
    )
    date = models.DateField("候補日")

    class Meta:
        unique_together = ("match", "date")
        ordering = ["date"]

    def __str__(self):
        return f"{self.match_id} {self.date}"


class MatchResult(models.Model):
    """確定した練習試合の結果。

    両校がそれぞれ、自校の得点と備考だけを入力する。両方の得点がそろうと結果が完成する。
    """

    match = models.OneToOneField(
        PracticeMatch, on_delete=models.CASCADE, related_name="result",
        verbose_name="練習試合",
    )
    applicant_score = models.PositiveIntegerField("申込側の得点", null=True, blank=True)
    opponent_score = models.PositiveIntegerField("相手側の得点", null=True, blank=True)
    applicant_notes = models.TextField("申込側の試合内容・備考", blank=True)
    opponent_notes = models.TextField("相手側の試合内容・備考", blank=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    def __str__(self):
        return f"{self.match} {self.applicant_score}-{self.opponent_score}"

    def _is_applicant(self, school):
        return self.match.applicant_club.school_id == school.pk

    @property
    def is_complete(self):
        return self.applicant_score is not None and self.opponent_score is not None

    def scores_for(self, school):
        """school から見た（自校の得点, 相手の得点）。未入力は None"""
        if self._is_applicant(school):
            return self.applicant_score, self.opponent_score
        return self.opponent_score, self.applicant_score

    def notes_for(self, school):
        """school から見た（自校の備考, 相手の備考）"""
        if self._is_applicant(school):
            return self.applicant_notes, self.opponent_notes
        return self.opponent_notes, self.applicant_notes

    def set_mine(self, school, score, notes):
        """school の側の得点・備考を書き換える"""
        if self._is_applicant(school):
            self.applicant_score, self.applicant_notes = score, notes
        else:
            self.opponent_score, self.opponent_notes = score, notes

    def outcome_for(self, school):
        """school から見た勝敗。"win" / "lose" / "draw"。両校の得点がそろうまでは None"""
        if not self.is_complete:
            return None
        mine, theirs = self.scores_for(school)
        if mine > theirs:
            return "win"
        if mine < theirs:
            return "lose"
        return "draw"


class Conversation(models.Model):
    """2校のあいだの会話。

    ・申し込みの会話：練習試合の申し込み（match）ごとに1つ。申し込むと自動で作られる
    ・自由メッセージ：部活動の組み合わせごとに1つ
    ・以前の会話：部活動を指定しない、学校どうしの会話（以前の仕組みのメッセージ）
    school_a / club_a は会話を始めた側。
    """

    class Kind(models.TextChoices):
        PROPOSAL = "proposal", "練習試合の申し込み"
        FREE = "free", "自由メッセージ"
        LEGACY = "legacy", "以前の会話"

    school_a = models.ForeignKey(School, on_delete=models.CASCADE, related_name="+", verbose_name="学校（開始した側）")
    school_b = models.ForeignKey(School, on_delete=models.CASCADE, related_name="+", verbose_name="学校（相手側）")
    club_a = models.ForeignKey(Club, null=True, blank=True, on_delete=models.CASCADE, related_name="+", verbose_name="部活動（開始した側）")
    club_b = models.ForeignKey(Club, null=True, blank=True, on_delete=models.CASCADE, related_name="+", verbose_name="部活動（相手側）")
    match = models.OneToOneField(
        PracticeMatch, null=True, blank=True, on_delete=models.CASCADE,
        related_name="conversation", verbose_name="申し込み",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    last_message_at = models.DateTimeField("最後のメッセージの日時", null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self):
        return f"{self.school_a} ⇔ {self.school_b}（{self.get_kind_display()}）"

    @property
    def kind(self):
        if self.match_id:
            return self.Kind.PROPOSAL
        if self.club_a_id:
            return self.Kind.FREE
        return self.Kind.LEGACY

    def get_kind_display(self):
        return self.Kind(self.kind).label

    def includes(self, school):
        return school.pk in (self.school_a_id, self.school_b_id)

    def other_school(self, school):
        return self.school_b if self.school_a_id == school.pk else self.school_a

    def my_club(self, school):
        return self.club_a if self.school_a_id == school.pk else self.club_b

    def other_club(self, school):
        return self.club_b if self.school_a_id == school.pk else self.club_a

    @staticmethod
    def for_school(school):
        return Conversation.objects.filter(Q(school_a=school) | Q(school_b=school))

    @classmethod
    def for_match(cls, match):
        """申し込みの会話を取り出す（なければ作る）"""
        conversation, _ = cls.objects.get_or_create(
            match=match,
            defaults={
                "school_a": match.applicant_club.school, "club_a": match.applicant_club,
                "school_b": match.opponent_club.school, "club_b": match.opponent_club,
            },
        )
        return conversation

    @classmethod
    def free_between(cls, my_club, other_club):
        """2つの部活動の自由メッセージの会話を取り出す（なければ作る）"""
        existing = cls.objects.filter(match__isnull=True).filter(
            Q(club_a=my_club, club_b=other_club) | Q(club_a=other_club, club_b=my_club)
        ).first()
        if existing:
            return existing
        return cls.objects.create(
            school_a=my_club.school, club_a=my_club,
            school_b=other_club.school, club_b=other_club,
        )


class Message(models.Model):
    """会話の中の1つのメッセージ"""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages",
        verbose_name="会話",
    )
    sender = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="sent_messages",
        verbose_name="送信した学校",
    )
    content = models.TextField("本文", max_length=2000)
    is_read = models.BooleanField("既読", default=False)
    created_at = models.DateTimeField("送信日時", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # 会話の一覧を、新しいメッセージ順に並べるため
        Conversation.objects.filter(pk=self.conversation_id).update(last_message_at=self.created_at)

    @staticmethod
    def unread_for(school):
        """school に届いている、まだ読んでいないメッセージ"""
        return Message.objects.filter(
            Q(conversation__school_a=school) | Q(conversation__school_b=school),
            is_read=False,
        ).exclude(sender=school)

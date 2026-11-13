from django.db import models
from django.db.models import Q

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
    """練習試合の申し込み。相手が承認すると確定する"""

    class Status(models.TextChoices):
        PENDING = "pending", "申込中"
        CONFIRMED = "confirmed", "確定"
        DECLINED = "declined", "辞退"

    class VenueKind(models.TextChoices):
        APPLICANT = "applicant", "申込校"
        OPPONENT = "opponent", "相手校"
        FACILITY = "facility", "施設"

    applicant_club = models.ForeignKey(
        Club, on_delete=models.CASCADE, related_name="sent_matches",
        verbose_name="申込側の部活動",
    )
    opponent_club = models.ForeignKey(
        Club, on_delete=models.CASCADE, related_name="received_matches",
        verbose_name="相手側の部活動",
    )
    date = models.DateField("日程")
    venue_kind = models.CharField("会場の種類", max_length=10, choices=VenueKind.choices)
    facility = models.ForeignKey(
        Facility, null=True, blank=True, on_delete=models.PROTECT,
        verbose_name="会場の施設",
    )
    message = models.TextField("ひとこと（任意）", blank=True)
    status = models.CharField(
        "状態", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField("申込日時", auto_now_add=True)
    decided_at = models.DateTimeField("承認・辞退の日時", null=True, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.applicant_club} → {self.opponent_club} {self.date}"

    @property
    def venue_name(self):
        """会場の名前（施設名、または学校名）"""
        if self.venue_kind == self.VenueKind.FACILITY and self.facility:
            return self.facility.name
        if self.venue_kind == self.VenueKind.APPLICANT:
            return self.applicant_club.school.name
        return self.opponent_club.school.name

    def has_conflict(self):
        """どちらかの部活動に、同じ日の確定済みの試合が別にあるか"""
        club_ids = [self.applicant_club_id, self.opponent_club_id]
        return (
            PracticeMatch.objects.filter(status=self.Status.CONFIRMED, date=self.date)
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


class MatchResult(models.Model):
    """確定した練習試合の結果。どちらの学校からでも登録・編集できる"""

    match = models.OneToOneField(
        PracticeMatch, on_delete=models.CASCADE, related_name="result",
        verbose_name="練習試合",
    )
    applicant_score = models.PositiveIntegerField("申込側の得点")
    opponent_score = models.PositiveIntegerField("相手側の得点")
    notes = models.TextField("試合内容・備考", blank=True)
    updated_by = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="最後に登録した学校",
    )
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    def __str__(self):
        return f"{self.match} {self.applicant_score}-{self.opponent_score}"

    def scores_for(self, school):
        """school から見た（自校の得点, 相手の得点）"""
        if self.match.applicant_club.school_id == school.pk:
            return self.applicant_score, self.opponent_score
        return self.opponent_score, self.applicant_score

    def outcome_for(self, school):
        """school から見た勝敗。"win" / "lose" / "draw" """
        mine, theirs = self.scores_for(school)
        if mine > theirs:
            return "win"
        if mine < theirs:
            return "lose"
        return "draw"


class Message(models.Model):
    """学校どうしのメッセージ"""

    sender = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="sent_messages",
        verbose_name="送信した学校",
    )
    receiver = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="received_messages",
        verbose_name="受信した学校",
    )
    content = models.TextField("本文", max_length=2000)
    is_read = models.BooleanField("既読", default=False)
    created_at = models.DateTimeField("送信日時", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} → {self.receiver} {self.created_at:%Y-%m-%d %H:%M}"

    @staticmethod
    def between(school_a, school_b):
        """2校のあいだのメッセージ（古い順）"""
        return Message.objects.filter(
            Q(sender=school_a, receiver=school_b) | Q(sender=school_b, receiver=school_a)
        )

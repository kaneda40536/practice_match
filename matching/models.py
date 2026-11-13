from django.db import models
from django.db.models import Q

from facilities.models import Facility
from schools.models import Club

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
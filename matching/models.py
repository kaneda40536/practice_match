from django.db import models

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
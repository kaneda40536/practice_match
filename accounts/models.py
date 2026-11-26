from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """ログインアカウント。

    ・教育委員会：role=board。学校・部活動は持たない
    ・部活動（顧問）：role=teacher。部活動ごとに1つ。学校ID＋部活動ID＋パスワードでログインする
      school は club の学校と同じ（保存するときに自動で合わせる）
    username は内部で使うだけ（部活動アカウントは「club＋部活動の番号」）
    """

    class Role(models.TextChoices):
        BOARD = "board", "教育委員会"
        TEACHER = "teacher", "顧問"

    role = models.CharField("役割", max_length=10, choices=Role.choices, default=Role.TEACHER)
    school = models.ForeignKey(
        "schools.School", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="所属学校",
    )
    club = models.OneToOneField(
        "schools.Club", on_delete=models.CASCADE, null=True, blank=True,
        related_name="account", verbose_name="部活動",
    )

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        if self.club_id:
            self.school_id = self.club.school_id
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        """画面に出すアカウントの名前（例：A高校 男子サッカー部）"""
        if self.club_id:
            return f"{self.club.school.name} {self.club.name}"
        return self.username

    @staticmethod
    def username_for(club):
        return f"club{club.pk}"

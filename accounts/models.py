import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """ログインアカウント。役割（role）ごとに使い方が違う。

    ・教育委員会（board）：管理者。管理者ID（username）＋パスワードでログインする
    ・学校（school）     ：教育委員会が作る学校アカウント。username が学校ID。
                           これ自体ではログインせず、パスワードは顧問の登録の確認に使う
                           （学校情報は School.account でひも付く。user.school_profile）
    ・顧問（teacher）    ：学校ID＋顧問名＋パスワードでログインし、部活動と部活IDを作る
    ・部活動（club）     ：部活動ごとに1つ。学校ID＋部活ID＋パスワードでログインし、練習試合の操作をする
    顧問・部活動の username は内部で使うだけ（画面には出さない）。
    """

    class Role(models.TextChoices):
        BOARD = "board", "教育委員会"
        SCHOOL = "school", "学校"
        TEACHER = "teacher", "顧問"
        CLUB = "club", "部活動"

    role = models.CharField("役割", max_length=10, choices=Role.choices, default=Role.CLUB)
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE,
        null=True, blank=True, verbose_name="所属学校",
        help_text="顧問・部活動のアカウントの学校",
    )
    club = models.OneToOneField(
        "schools.Club", on_delete=models.CASCADE, null=True, blank=True,
        related_name="account", verbose_name="部活動",
    )
    advisor_name = models.CharField("顧問名", max_length=100, blank=True)

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
        if self.role == self.Role.TEACHER and self.school_id:
            return f"{self.school.name} {self.advisor_name}（顧問）"
        return self.username

    @staticmethod
    def username_for(club):
        return f"club{club.pk}"

    @staticmethod
    def new_advisor_username():
        return f"teacher-{uuid.uuid4().hex[:12]}"

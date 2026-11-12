from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        BOARD = "board", "教育委員会"
        TEACHER = "teacher", "顧問"

    role = models.CharField("役割", max_length=10, choices=Role.choices, default=Role.TEACHER)
    school = models.ForeignKey(
        "schools.School", on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="所属学校",
    )

    def __str__(self):
        return self.username
from django.db import models


class Sport(models.Model):
    name = models.CharField("競技種目", max_length=50, unique=True)

    def __str__(self):
        return self.name


class Area(models.Model):
    name = models.CharField("地域", max_length=50, unique=True)

    def __str__(self):
        return self.name


class School(models.Model):
    name = models.CharField("学校名", max_length=100)
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, null=True, verbose_name="地域"
    )
    address = models.CharField("所在地", max_length=200, blank=True)
    latitude = models.FloatField("緯度", null=True, blank=True)
    longitude = models.FloatField("経度", null=True, blank=True)

    def __str__(self):
        return self.name


class Club(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "男子"
        FEMALE = "female", "女子"
        MIXED = "mixed", "男女混合"

    school = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name="学校")
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, verbose_name="競技種目")
    gender = models.CharField("区分", max_length=10, choices=Gender.choices)

    class Meta:
        unique_together = ("school", "sport", "gender")

    def __str__(self):
        return f"{self.school.name} {self.get_gender_display()}{self.sport.name}部"
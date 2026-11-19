from django.db import models

from schools.models import School, Sport


class Facility(models.Model):
    """練習試合の会場になる施設。

    school が空なら、教育委員会が登録した施設（市民体育館など）。
    school が入っていれば、その学校が「会場管理」で登録した学校内の施設（体育館・グラウンドなど）。
    学校内の施設の所在地・位置は、学校のものを使う。
    """
    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.CASCADE,
        related_name="facilities", verbose_name="学校（学校内の施設のとき）",
    )
    name = models.CharField("施設名", max_length=100)
    address = models.CharField("所在地", max_length=200, blank=True)
    sports = models.ManyToManyField(Sport, verbose_name="対応競技")
    equipment = models.TextField("設備", blank=True)
    latitude = models.FloatField("緯度", null=True, blank=True)
    longitude = models.FloatField("経度", null=True, blank=True)

    def __str__(self):
        if self.school_id:
            return f"{self.school.name} {self.name}"
        return self.name

    @property
    def is_school_facility(self):
        return self.school_id is not None

    @property
    def display_name(self):
        """会場として表示する名前（学校内の施設は「学校名 施設名」）"""
        return str(self)

    @property
    def location(self):
        """(緯度, 経度)。学校内の施設は学校の位置。わからなければ (None, None)"""
        if self.school_id:
            return self.school.latitude, self.school.longitude
        return self.latitude, self.longitude

    @property
    def full_address(self):
        return self.school.address if self.school_id else self.address
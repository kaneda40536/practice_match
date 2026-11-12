from django.db import models

from schools.models import Sport


class Facility(models.Model):
    name = models.CharField("施設名", max_length=100)
    address = models.CharField("所在地", max_length=200)
    sports = models.ManyToManyField(Sport, verbose_name="対応競技")
    equipment = models.TextField("設備", blank=True)
    latitude = models.FloatField("緯度", null=True, blank=True)
    longitude = models.FloatField("経度", null=True, blank=True)

    def __str__(self):
        return self.name
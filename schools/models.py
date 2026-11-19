from django.db import models


class Sport(models.Model):
    DEFAULT_ICON = "🏅"

    name = models.CharField("競技種目", max_length=50, unique=True)
    icon = models.CharField(
        "競技アイコン", max_length=20, blank=True,
        help_text="競技に合った絵文字を入力してください。（例：⚽）",
    )

    def __str__(self):
        return self.name

    @property
    def display_icon(self):
        """アイコンが未設定なら、共通のメダルを表示する"""
        return self.icon or self.DEFAULT_ICON


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

    class DesiredLevel(models.TextChoices):
        """対戦相手を探すときの、希望する相手のレベル"""
        SAME = "same", "同程度の相手"
        HIGHER = "higher", "格上の相手"
        LOWER = "lower", "格下の相手"

    school = models.ForeignKey(School, on_delete=models.CASCADE, verbose_name="学校")
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, verbose_name="競技種目")
    gender = models.CharField("区分", max_length=10, choices=Gender.choices)
    desired_level = models.CharField(
        "希望する対戦レベル", max_length=10,
        choices=DesiredLevel.choices, default=DesiredLevel.SAME,
    )

    class Meta:
        unique_together = ("school", "sport", "gender")

    def __str__(self):
        return f"{self.school.name} {self.name}"

    @property
    def name(self):
        """部活動名（例：男子サッカー部）"""
        return f"{self.get_gender_display()}{self.sport.name}部"


class TournamentResult(models.Model):
    """部活動の大会成績（対戦相手のレベルを推定するために使う。登録は任意）"""

    class Level(models.TextChoices):
        DISTRICT = "district", "地区大会"
        PREFECTURE = "prefecture", "都道府県大会"
        NATIONAL = "national", "全国大会"

    class Achievement(models.TextChoices):
        CHAMPION = "champion", "優勝"
        RUNNER_UP = "runner_up", "準優勝"
        BEST4 = "best4", "ベスト4（3位）"
        BEST8 = "best8", "ベスト8"
        BEST16 = "best16", "ベスト16"
        PARTICIPATED = "participated", "出場（ベスト32以下）"

    club = models.ForeignKey(
        Club, on_delete=models.CASCADE, related_name="tournament_results", verbose_name="部活動")
    tournament_name = models.CharField("大会名", max_length=100)
    fiscal_year = models.PositiveSmallIntegerField("開催年度")
    level = models.CharField("大会規模", max_length=12, choices=Level.choices)
    achievement = models.CharField("大会成績", max_length=12, choices=Achievement.choices)
    created_at = models.DateTimeField("登録日時", auto_now_add=True)

    class Meta:
        ordering = ["-fiscal_year", "club", "-created_at"]

    def __str__(self):
        return f"{self.club} {self.fiscal_year}年度 {self.tournament_name} {self.get_achievement_display()}"

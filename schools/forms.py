from django import forms

from config.form_messages import RequiredMessageMixin
from .geocoding import geocode
from django.utils import timezone

from .models import Club, School, Sport, TournamentResult

ADDRESS_HELP = "都道府県から番地まで入力してください。入力した住所から、距離の計算に使う位置を自動で求めます。"


class SchoolLocationMixin:
    """住所から緯度・経度を求めて、保存時にモデルへ入れる部品"""

    def clean_address(self):
        address = self.cleaned_data["address"].strip()
        if not address:
            raise forms.ValidationError("住所を入力してください。")

        # 住所が変わっていなければ、前に求めた位置をそのまま使う
        instance = self.instance
        if instance.pk and instance.address == address and instance.latitude is not None:
            self._location = (instance.latitude, instance.longitude)
            return address

        location = geocode(address)
        if location is None:
            raise forms.ValidationError(
                "住所から位置を特定できませんでした。都道府県から番地まで入力して、"
                "もう一度お試しください（インターネットに接続できているかも確認してください）。"
            )
        self._location = location
        return address

    def save(self, commit=True):
        self.instance.latitude, self.instance.longitude = self._location
        return super().save(commit)


class SportForm(RequiredMessageMixin, forms.ModelForm):
    """教育委員会が、競技を登録・編集するフォーム"""

    class Meta:
        model = Sport
        fields = ["name", "icon"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "例：サッカー"}),
            "icon": forms.TextInput(attrs={"placeholder": "例：⚽", "maxlength": 20}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # デザインに合わせて、アイコンも入力必須にする（既存の競技は未設定のままでも表示できる）
        self.fields["icon"].required = True


class SchoolUpdateForm(RequiredMessageMixin, SchoolLocationMixin, forms.ModelForm):
    """教育委員会が、学校の情報を編集するフォーム"""

    class Meta:
        model = School
        fields = ["name", "area", "address"]
        help_texts = {"address": ADDRESS_HELP}

    def clean_name(self):
        name = self.cleaned_data["name"]
        if School.objects.filter(name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("同じ名前の学校がすでに登録されています。")
        return name


class SchoolAddressForm(RequiredMessageMixin, SchoolLocationMixin, forms.ModelForm):
    """顧問が、自校の所在地だけを編集するフォーム"""

    class Meta:
        model = School
        fields = ["address"]
        help_texts = {"address": ADDRESS_HELP}


class ClubForm(RequiredMessageMixin, forms.ModelForm):
    """顧問が、自校の部活動を追加するフォーム（学校は自動で入る）"""

    class Meta:
        model = Club
        fields = ["sport", "gender"]

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.instance.school = school
        # 競技の選択肢に、アイコンも表示する（例：⚽ サッカー）
        self.fields["sport"].queryset = Sport.objects.order_by("name")
        self.fields["sport"].label_from_instance = lambda s: f"{s.display_icon} {s.name}"

    def clean(self):
        cleaned = super().clean()
        sport = cleaned.get("sport")
        gender = cleaned.get("gender")
        if sport and gender and Club.objects.filter(
            school=self.school, sport=sport, gender=gender
        ).exists():
            raise forms.ValidationError("この競技・区分の部活動は、すでに登録されています。")
        return cleaned


def current_fiscal_year():
    """今の年度（4月はじまり）"""
    today = timezone.localdate()
    return today.year if today.month >= 4 else today.year - 1


class TournamentResultForm(RequiredMessageMixin, forms.ModelForm):
    """大会成績の登録・変更フォーム（顧問の「大会成績管理」）"""

    class Meta:
        model = TournamentResult
        fields = ["club", "tournament_name", "fiscal_year", "level", "achievement"]
        widgets = {
            "tournament_name": forms.TextInput(attrs={"placeholder": "例：地区新人大会"}),
            "fiscal_year": forms.NumberInput(attrs={"placeholder": "例：2026", "inputmode": "numeric"}),
        }
        help_texts = {
            "level": "地区大会の成績は、同じ地域の学校どうしでだけ比べます。",
        }

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["club"].queryset = (
            Club.objects.filter(school=school).select_related("sport").order_by("sport__name", "gender"))
        self.fields["club"].label_from_instance = lambda c: f"{c.sport.display_icon} {c.name}"
        self.fields["club"].empty_label = "部活動を選択してください"
        self.fields["level"].choices = [("", "大会規模を選択してください")] + list(TournamentResult.Level.choices)
        self.fields["achievement"].choices = (
            [("", "大会成績を選択してください")] + list(TournamentResult.Achievement.choices))
        if not self.instance.pk:
            self.initial.setdefault("fiscal_year", current_fiscal_year())

    def clean_fiscal_year(self):
        year = self.cleaned_data["fiscal_year"]
        if not 1990 <= year <= current_fiscal_year():
            raise forms.ValidationError(f"開催年度は1990〜{current_fiscal_year()}の間で入力してください。")
        return year


class ClubLevelForm(forms.ModelForm):
    """部活動の「希望する対戦レベル」を変更するフォーム"""

    class Meta:
        model = Club
        fields = ["desired_level"]
        widgets = {"desired_level": forms.RadioSelect}
        help_texts = {
            "desired_level": "対戦相手検索で、このレベルに合う相手を先に表示します。",
        }

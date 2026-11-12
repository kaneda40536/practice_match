from django import forms

from .geocoding import geocode
from .models import Club, School

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


class SchoolUpdateForm(SchoolLocationMixin, forms.ModelForm):
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


class SchoolAddressForm(SchoolLocationMixin, forms.ModelForm):
    """顧問が、自校の所在地だけを編集するフォーム"""

    class Meta:
        model = School
        fields = ["address"]
        help_texts = {"address": ADDRESS_HELP}


class ClubForm(forms.ModelForm):
    """顧問が、自校の部活動を追加するフォーム（学校は自動で入る）"""

    class Meta:
        model = Club
        fields = ["sport", "gender"]

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.instance.school = school

    def clean(self):
        cleaned = super().clean()
        sport = cleaned.get("sport")
        gender = cleaned.get("gender")
        if sport and gender and Club.objects.filter(
            school=self.school, sport=sport, gender=gender
        ).exists():
            raise forms.ValidationError("この競技・区分の部活動は、すでに登録されています。")
        return cleaned
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
    """教育委員会が、学校の情報（学校名・所在地）を編集するフォーム"""

    class Meta:
        model = School
        fields = ["name", "address"]
        help_texts = {"address": ADDRESS_HELP}

    def clean_name(self):
        name = self.cleaned_data["name"]
        if School.objects.filter(name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("同じ名前の学校がすでに登録されています。")
        return name


class SchoolCreateForm(SchoolUpdateForm):
    """新しい学校（学校ID）を登録するフォーム（部活動アカウントの作成画面で使う）"""

    class Meta(SchoolUpdateForm.Meta):
        fields = ["name", "code", "address"]
        error_messages = {"code": {"unique": "この学校IDはすでに使われています。"}}


class SchoolAddressForm(RequiredMessageMixin, SchoolLocationMixin, forms.ModelForm):
    """顧問が、自校の所在地だけを編集するフォーム"""

    class Meta:
        model = School
        fields = ["address"]
        help_texts = {"address": ADDRESS_HELP}


def current_fiscal_year():
    """今の年度（4月はじまり）"""
    today = timezone.localdate()
    return today.year if today.month >= 4 else today.year - 1


class TournamentResultForm(RequiredMessageMixin, forms.ModelForm):
    """大会成績の登録・変更フォーム（部活動の「大会成績管理」。部活動はログイン中の部活動）"""

    class Meta:
        model = TournamentResult
        fields = ["tournament_name", "fiscal_year", "level", "achievement"]
        widgets = {
            "tournament_name": forms.TextInput(attrs={"placeholder": "例：地区新人大会"}),
            "fiscal_year": forms.NumberInput(attrs={"placeholder": "例：2026", "inputmode": "numeric"}),
        }

    def __init__(self, *args, club, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.club = club
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

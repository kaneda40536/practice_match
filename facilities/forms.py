from django import forms

from config.form_messages import RequiredMessageMixin
from schools.forms import ADDRESS_HELP, SchoolLocationMixin
from schools.models import Sport
from .models import Facility


class FacilityForm(RequiredMessageMixin, SchoolLocationMixin, forms.ModelForm):
    """施設の登録・編集フォーム。住所から緯度・経度を自動で求める"""

    class Meta:
        model = Facility
        fields = ["name", "address", "sports", "equipment"]
        widgets = {
            "sports": forms.CheckboxSelectMultiple,
            "equipment": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"name": "会場名"}
        help_texts = {
            "address": ADDRESS_HELP,
            "sports": "この会場で練習試合ができる競技を、すべて選んでください。",
            "equipment": "例：照明、更衣室、駐車場、シャワー",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sports"].queryset = Sport.objects.order_by("name")
        self.fields["sports"].label_from_instance = lambda s: f"{s.display_icon} {s.name}"

    def clean_name(self):
        name = self.cleaned_data["name"]
        if Facility.objects.filter(name=name, school__isnull=True).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("同じ名前の会場がすでに登録されています。")
        return name


class SchoolFacilityForm(RequiredMessageMixin, forms.ModelForm):
    """学校内の施設（会場）の登録・編集フォーム（顧問の「会場管理」）。所在地は学校のものを使う"""

    class Meta:
        model = Facility
        fields = ["name", "sports"]
        labels = {"name": "会場名"}
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "例：第一体育館"}),
            "sports": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.instance.school = school
        self.fields["sports"].queryset = Sport.objects.order_by("name")
        self.fields["sports"].label_from_instance = lambda s: f"{s.display_icon} {s.name}"
        self.fields["sports"].error_messages["required"] = "対応競技を1つ以上選択してください。"

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Facility.objects.filter(school=self.school, name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("同じ名前の会場がすでに登録されています。")
        return name

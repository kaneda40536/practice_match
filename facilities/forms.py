from django import forms

from schools.forms import ADDRESS_HELP, SchoolLocationMixin
from schools.models import Sport
from .models import Facility


class FacilityForm(SchoolLocationMixin, forms.ModelForm):
    """施設の登録・編集フォーム。住所から緯度・経度を自動で求める"""

    class Meta:
        model = Facility
        fields = ["name", "address", "sports", "equipment"]
        widgets = {
            "sports": forms.CheckboxSelectMultiple,
            "equipment": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "address": ADDRESS_HELP,
            "sports": "この施設で練習試合ができる競技を、すべて選んでください。",
            "equipment": "例：照明、更衣室、駐車場、シャワー",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sports"].queryset = Sport.objects.order_by("name")

    def clean_name(self):
        name = self.cleaned_data["name"]
        if Facility.objects.filter(name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("同じ名前の施設がすでに登録されています。")
        return name
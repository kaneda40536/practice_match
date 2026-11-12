from django import forms
from django.utils import timezone

from .models import Availability


class AvailabilityForm(forms.ModelForm):
    """希望日を1日追加するフォーム（部活動は自動で入る）"""

    class Meta:
        model = Availability
        fields = ["date", "can_host"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, club, **kwargs):
        super().__init__(*args, **kwargs)
        self.club = club
        self.instance.club = club
        # 日付を選ぶカレンダーで、過去の日を選べないようにする
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("過去の日付は登録できません。")
        if Availability.objects.filter(club=self.club, date=date).exists():
            raise forms.ValidationError("この日はすでに登録されています。")
        return date
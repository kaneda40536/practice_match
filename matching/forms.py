from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import Availability, MatchResult, Message, PracticeMatch
from .venues import venue_candidates

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

class MatchRequestForm(forms.ModelForm):
    """練習試合を申し込むフォーム（申込側・相手側の部活動は自動で入る）"""

    venue = forms.ChoiceField(
        label="会場",
        choices=[],
        help_text="「自校」「相手校」は、その日に「受け入れ可」が登録されている場合だけ選べます。",
    )
    field_order = ["date", "venue", "message"]

    class Meta:
        model = PracticeMatch
        fields = ["date", "message"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "message": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"date": "日程"}

    def __init__(self, *args, applicant, opponent, **kwargs):
        super().__init__(*args, **kwargs)
        self.applicant = applicant
        self.opponent = opponent
        self.instance.applicant_club = applicant
        self.instance.opponent_club = opponent
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

        # 会場の選択肢（施設は、距離の近い順）
        self.candidates = venue_candidates(applicant.school, opponent.school, applicant.sport)
        facility_choices = []
        for c in self.candidates:
            if c["total"] is not None:
                label = f"{c['facility'].name}（両校からの距離の合計 {c['total']} km）"
            else:
                label = f"{c['facility'].name}（距離は不明）"
            facility_choices.append((f"facility:{c['facility'].pk}", label))

        choices = [
            ("", "会場を選択してください"),
            ("学校で実施", [
                ("applicant", f"自校（{applicant.school.name}）で実施"),
                ("opponent", f"相手校（{opponent.school.name}）で実施"),
            ]),
        ]
        if facility_choices:
            choices.append(("施設（距離の近い順）", facility_choices))
        self.fields["venue"].choices = choices

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("過去の日付は選べません。")
        return date

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("date")
        venue = cleaned.get("venue")
        if date is None or not venue:
            return cleaned

        # 同じ相手との、同じ日の申し込み（または確定）がすでにないか
        duplicate = PracticeMatch.objects.filter(
            date=date,
            status__in=[PracticeMatch.Status.PENDING, PracticeMatch.Status.CONFIRMED],
        ).filter(
            Q(applicant_club=self.applicant, opponent_club=self.opponent)
            | Q(applicant_club=self.opponent, opponent_club=self.applicant)
        ).exists()
        if duplicate:
            raise forms.ValidationError("この日は、この相手校とすでに申し込み（または確定）があります。")

        # 学校を会場にするときは、その日に「受け入れ可」が登録されていること
        if venue in ("applicant", "opponent"):
            club = self.applicant if venue == "applicant" else self.opponent
            can_host = Availability.objects.filter(club=club, date=date, can_host=True).exists()
            if not can_host:
                if venue == "applicant":
                    self.add_error(
                        "venue",
                        "この日は、自校が「受け入れ可」になっていません。希望日の登録で、チェックを付けてください。",
                    )
                else:
                    self.add_error("venue", "この日は、相手校が「受け入れ可」になっていません。")
        return cleaned

    def save(self, commit=True):
        venue = self.cleaned_data["venue"]
        if venue.startswith("facility:"):
            self.instance.venue_kind = PracticeMatch.VenueKind.FACILITY
            self.instance.facility_id = int(venue.split(":")[1])
        else:
            self.instance.venue_kind = venue
            self.instance.facility = None
        return super().save(commit)

class MatchResultForm(forms.ModelForm):
    """試合結果の登録・編集フォーム。得点の欄には学校名を表示する"""

    class Meta:
        model = MatchResult
        fields = ["applicant_score", "opponent_score", "notes"]
        widgets = {
            "applicant_score": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
            "opponent_score": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
            "notes": forms.Textarea(attrs={
                "rows": 4, "placeholder": "試合内容や、次回への反省点などを自由に入力してください。"}),
        }

    def __init__(self, *args, match, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.match = match
        self.fields["applicant_score"].label = f"{match.applicant_club.school.name}の得点"
        self.fields["opponent_score"].label = f"{match.opponent_club.school.name}の得点"


class MessageForm(forms.ModelForm):
    """メッセージの送信フォーム"""

    class Meta:
        model = Message
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={
                "rows": 3, "placeholder": "メッセージを入力してください", "maxlength": 2000}),
        }
        labels = {"content": "メッセージ"}

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if not content:
            raise forms.ValidationError("メッセージを入力してください。")
        return content

import datetime

from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from config.form_messages import RequiredMessageMixin
from schools.models import Club
from .models import Availability, CandidateDate, Conversation, Message, PracticeMatch
from .venues import parse_venue, venue_candidates, venue_choices

MAX_CANDIDATES = 5


class AvailabilityForm(RequiredMessageMixin, forms.ModelForm):
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


def missing_host_dates(club, dates):
    """dates のうち、club が「受け入れ可」を登録していない日"""
    host_dates = set(
        Availability.objects.filter(club=club, date__in=dates, can_host=True)
        .values_list("date", flat=True)
    )
    return [d for d in dates if d not in host_dates]


class MultipleDateWidget(forms.Widget):
    """同じ名前の入力欄（チェックボックスや日付欄）から、日付をまとめて受け取る"""

    def value_from_datadict(self, data, files, name):
        return [v for v in data.getlist(name) if v.strip()]


class MultipleDateField(forms.Field):
    """複数の日付（YYYY-MM-DD）。重複は1つにまとめ、古い順に並べる"""
    widget = MultipleDateWidget

    def to_python(self, value):
        dates = set()
        for v in value or []:
            try:
                dates.add(datetime.date.fromisoformat(v.strip()))
            except ValueError:
                raise forms.ValidationError(f"「{v}」は日付として読み取れません。")
        return sorted(dates)


class MatchRequestForm(RequiredMessageMixin, forms.ModelForm):
    """練習試合を申し込むフォーム。候補日を複数送り、相手校が1日を選ぶと確定する"""

    candidate_dates = MultipleDateField(
        label="候補日",
        error_messages={"required": "候補日を1日以上選んでください。"},
        help_text=f"相手校がこの中から1日を選びます。最大{MAX_CANDIDATES}日まで選べます。",
    )
    venue = forms.ChoiceField(
        label="会場",
        choices=[],
        help_text="学校で実施する場合は、すべての候補日にその学校が「受け入れ可」を登録している必要があります。"
                  "「未定」にすると、相手校が確定するときに会場を決めます。",
    )
    field_order = ["candidate_dates", "venue", "message"]

    class Meta:
        model = PracticeMatch
        fields = ["message"]
        widgets = {
            "message": forms.Textarea(attrs={
                "rows": 3, "placeholder": "試合についての希望や連絡事項を入力してください。"}),
        }

    def __init__(self, *args, applicant, opponent, **kwargs):
        super().__init__(*args, **kwargs)
        self.applicant = applicant
        self.opponent = opponent
        self.instance.applicant_club = applicant
        self.instance.opponent_club = opponent

        # 会場の選択肢（両校の学校内の施設・公共の施設・未定）
        self.candidates = venue_candidates(applicant, opponent)
        self.fields["venue"].choices = venue_choices(
            applicant, opponent, self.candidates, allow_undecided=True)

    def clean_venue(self):
        venue = self.cleaned_data["venue"]
        parsed = parse_venue(venue, self.candidates, allow_undecided=True)
        if parsed is None:
            raise forms.ValidationError("会場を選び直してください。")
        self.instance.venue_kind, self.instance.facility = parsed
        return venue

    def clean_candidate_dates(self):
        dates = self.cleaned_data["candidate_dates"]
        if not dates:
            raise forms.ValidationError("候補日を1日以上選んでください。")
        if len(dates) > MAX_CANDIDATES:
            raise forms.ValidationError(f"候補日は{MAX_CANDIDATES}日までにしてください。")
        if dates[0] < timezone.localdate():
            raise forms.ValidationError("過去の日付は候補日にできません。")

        # 同じ相手と、すでに申し込み中の候補日・確定した日と重なっていないか
        pair = PracticeMatch.objects.filter(
            Q(applicant_club=self.applicant, opponent_club=self.opponent)
            | Q(applicant_club=self.opponent, opponent_club=self.applicant)
        )
        taken = set(
            CandidateDate.objects.filter(
                match__in=pair.filter(status=PracticeMatch.Status.PENDING), date__in=dates
            ).values_list("date", flat=True)
        ) | set(
            pair.filter(status=PracticeMatch.Status.CONFIRMED, date__in=dates)
            .values_list("date", flat=True)
        )
        if taken:
            listed = "、".join(f"{d.month}/{d.day}" for d in sorted(taken))
            raise forms.ValidationError(
                f"{listed} は、この相手校とすでに申し込み中（または確定）です。")
        return dates

    def clean(self):
        cleaned = super().clean()
        dates = cleaned.get("candidate_dates")
        venue = cleaned.get("venue")
        if not dates or not venue:
            return cleaned

        # 学校で実施するときは、すべての候補日にその学校が「受け入れ可」を登録していること
        host = self.instance.host_club
        if host is not None:
            missing = missing_host_dates(host, dates)
            if missing:
                listed = "、".join(f"{d.month}/{d.day}" for d in missing)
                who = "自校" if host == self.applicant else "相手校"
                self.add_error("venue", f"{listed} は、{who}が「受け入れ可」になっていません。")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        # 会場（venue_kind・facility）は clean_venue で instance に入れてある
        match = super().save(commit=True)
        CandidateDate.objects.bulk_create(
            CandidateDate(match=match, date=d) for d in self.cleaned_data["candidate_dates"]
        )

        # 申し込みの会話を作り、備考があれば最初のメッセージとして送っておく
        conversation = Conversation.for_match(match)
        if match.message.strip():
            Message.objects.create(
                conversation=conversation, sender=match.applicant_club.school,
                content=match.message.strip(),
            )
        return match


class MatchResultForm(RequiredMessageMixin, forms.Form):
    """試合結果の登録フォーム。自校の得点と備考だけを入力する"""

    my_score = forms.IntegerField(
        label="自校の得点", min_value=0,
        error_messages={"min_value": "得点は0以上の数字で入力してください。",
                        "invalid": "得点は数字で入力してください。"},
        widget=forms.NumberInput(attrs={"min": 0, "step": 1, "inputmode": "numeric"}),
    )
    my_notes = forms.CharField(
        label="自校側の試合内容・備考", required=False,
        widget=forms.Textarea(attrs={
            "rows": 5, "placeholder": "試合内容や、次回への反省点などを自由に入力してください。"}),
    )


class MessageForm(RequiredMessageMixin, forms.ModelForm):
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


class ConversationStartForm(RequiredMessageMixin, forms.Form):
    """自由メッセージを始めるときに、自校と相手校の部活動を選ぶフォーム"""

    my_club = forms.ModelChoiceField(label="自校の部活動", queryset=Club.objects.none(),
                                     empty_label="部活動を選択してください")
    opponent_club = forms.ModelChoiceField(label="相手校の部活動", queryset=Club.objects.none(),
                                           empty_label="部活動を選択してください")

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        clubs = Club.objects.select_related("school", "sport")
        self.fields["my_club"].queryset = clubs.filter(school=school).order_by("sport__name", "gender")
        self.fields["my_club"].label_from_instance = lambda c: c.name
        self.fields["opponent_club"].queryset = (
            clubs.exclude(school=school).order_by("school__name", "sport__name", "gender"))
        self.fields["opponent_club"].label_from_instance = lambda c: f"{c.school.name}：{c.name}"

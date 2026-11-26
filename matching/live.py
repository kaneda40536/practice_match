"""画面の自動更新に使う「変化の目印」

画面（static/js/live-update.js）が数秒ごとに問い合わせ、目印が前と変わっていれば
画面の中身を読み込み直す。目印は、データの件数や最後に変わった日時をまとめた短い文字列。

  matches  : 自分の部活動が関わる申し込み・試合・候補日・試合結果
  messages : 自分の部活動が参加している会話のメッセージ（既読になったことも含む）
  dates    : 希望日と部活動（対戦相手検索・日程調整で、他校の希望日を表示するため）
"""
import hashlib

from django.db.models import Count, Max, Q

from schools.models import Club
from .models import Availability, CandidateDate, Conversation, MatchResult, Message, PracticeMatch


def _stamp(*values):
    return hashlib.md5(repr(values).encode("utf-8")).hexdigest()[:12]


def live_versions(club):
    matches = PracticeMatch.objects.filter(Q(applicant_club=club) | Q(opponent_club=club))
    match_info = matches.aggregate(n=Count("id"), created=Max("created_at"), decided=Max("decided_at"))
    candidate_count = CandidateDate.objects.filter(match__in=matches).count()
    result_info = MatchResult.objects.filter(match__in=matches).aggregate(
        n=Count("id"), updated=Max("updated_at"))

    message_info = Message.objects.filter(conversation__in=Conversation.for_club(club)).aggregate(
        n=Count("id"), last=Max("created_at"), unread=Count("id", filter=Q(is_read=False)))

    date_info = Availability.objects.aggregate(n=Count("id"), last=Max("id"))
    club_info = Club.objects.aggregate(n=Count("id"), last=Max("id"))

    return {
        "matches": _stamp(match_info, candidate_count, result_info),
        "messages": _stamp(message_info),
        "dates": _stamp(date_info, club_info),
    }

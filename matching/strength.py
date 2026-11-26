"""対戦相手の「競技レベル」の推定と、おすすめ順の並べ替え

自校の部活動から見て、相手が「格上」「同程度」「格下」のどれに近いかを、次の2つから推定する。

1. 大会成績（直近3年度分。登録は任意）
   ・大会規模（全国＞都道府県＞地区）と成績（優勝〜出場）を点数にして、いちばん良い成績どうしを比べる。
2. 過去の対戦結果（直近3年度分。このシステムで登録した練習試合の結果）
   ・勝ち越していれば「格下」寄り、負け越していれば「格上」寄りとみなす。

どちらも判断の材料がなければ「未判定」。未判定の相手も、おすすめの対象から外さない。
"""
from datetime import date

from django.db.models import Q

from schools.forms import current_fiscal_year
from schools.models import Club, TournamentResult
from .models import MatchResult, PracticeMatch

RECENT_YEARS = 3          # 直近何年度分の成績・対戦結果を使うか
SAME_MARGIN = 3           # 点数の差がこれより小さければ「同程度」

LEVEL_POINTS = {
    TournamentResult.Level.DISTRICT: 0,
    TournamentResult.Level.PREFECTURE: 10,
    TournamentResult.Level.NATIONAL: 20,
}
ACHIEVEMENT_POINTS = {
    TournamentResult.Achievement.CHAMPION: 6,
    TournamentResult.Achievement.RUNNER_UP: 5,
    TournamentResult.Achievement.BEST4: 4,
    TournamentResult.Achievement.BEST8: 3,
    TournamentResult.Achievement.BEST16: 2,
    TournamentResult.Achievement.PARTICIPATED: 1,
}

RELATION_LABELS = {
    "higher": "格上",
    "same": "同程度",
    "lower": "格下",
    "unknown": "未判定",
}
# 希望する対戦レベル（Club.DesiredLevel）と、推定したレベルの対応
DESIRED_TO_RELATION = {
    Club.DesiredLevel.SAME: "same",
    Club.DesiredLevel.HIGHER: "higher",
    Club.DesiredLevel.LOWER: "lower",
}


def first_year():
    return current_fiscal_year() - (RECENT_YEARS - 1)


def result_points(result):
    return LEVEL_POINTS[result.level] + ACHIEVEMENT_POINTS[result.achievement]


def result_label(result):
    return f"{result.fiscal_year}年度 {result.get_level_display()} {result.get_achievement_display()}"


def recent_results(clubs):
    """部活動ごとの、直近の大会成績 {club_id: [TournamentResult, ...]}"""
    grouped = {}
    for r in TournamentResult.objects.filter(club__in=clubs, fiscal_year__gte=first_year()):
        grouped.setdefault(r.club_id, []).append(r)
    return grouped


def best_result(results):
    return max(results, key=result_points, default=None)


def head_to_head(my_club, other_clubs):
    """自校の部活動と各相手の、直近の対戦成績 {相手のclub_id: {"win":, "lose":, "draw":}}"""
    start = date(first_year(), 4, 1)
    other_ids = [c.pk for c in other_clubs]
    matches = (
        PracticeMatch.objects.filter(status=PracticeMatch.Status.CONFIRMED, date__gte=start)
        .filter(
            Q(applicant_club=my_club, opponent_club_id__in=other_ids)
            | Q(opponent_club=my_club, applicant_club_id__in=other_ids)
        )
        .select_related("applicant_club", "opponent_club")
    )
    results = {r.match_id: r for r in MatchResult.objects.filter(match__in=matches)}
    records = {}
    for match in matches:
        result = results.get(match.pk)
        outcome = result.outcome_for(my_club.school) if result else None
        if outcome is None:
            continue
        other_id = match.opponent_club_id if match.applicant_club_id == my_club.pk else match.applicant_club_id
        record = records.setdefault(other_id, {"win": 0, "lose": 0, "draw": 0})
        record[outcome] += 1
    return records


def estimate(my_club, other_club, my_results, their_results, record):
    """相手のレベルを推定する。relation・label・reasons（判断の理由）を返す"""
    signals = []
    reasons = []

    mine = best_result(my_results)
    theirs = best_result(their_results)
    if mine and theirs:
        diff = result_points(theirs) - result_points(mine)
        signals.append(1 if diff >= SAME_MARGIN else -1 if diff <= -SAME_MARGIN else 0)
        reasons.append(f"大会成績：相手 {result_label(theirs)}／自校 {result_label(mine)}")
    elif theirs:
        reasons.append(f"相手の大会成績：{result_label(theirs)}（自校の比べられる成績が未登録）")
    elif mine and their_results:
        reasons.append("相手の比べられる大会成績がありません")

    if record:
        win, lose, draw = record["win"], record["lose"], record["draw"]
        signals.append(1 if lose > win else -1 if win > lose else 0)
        text = f"{win}勝{lose}敗" + (f"{draw}分" if draw else "")
        reasons.append(f"過去の対戦：{text}")

    if not signals:
        relation = "unknown"
        if not reasons:
            reasons.append("大会成績・過去の対戦結果がないため、判定できません")
    else:
        total = sum(signals)
        relation = "higher" if total > 0 else "lower" if total < 0 else "same"

    return {"relation": relation, "label": RELATION_LABELS[relation], "reasons": reasons}


def fit_for(relation, desired_level):
    """希望する対戦レベルに合うか。"match"（合う）・"unknown"（未判定）・"mismatch"（合わない）"""
    if relation == "unknown":
        return "unknown"
    return "match" if DESIRED_TO_RELATION.get(desired_level) == relation else "mismatch"


FIT_ORDER = {"match": 0, "unknown": 1, "mismatch": 2}

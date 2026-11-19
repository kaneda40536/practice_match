"""練習試合の会場の候補

会場の候補は、次の3種類。
  ・両校が「会場管理」で登録した、学校内の施設（その競技に対応しているもの）
  ・学校内の施設を登録していない学校は、「○○高校で実施（施設未登録）」
  ・教育委員会が登録した施設（その競技に対応しているもの）。両校からの距離の合計が近い順

選択肢の値は、"facility:<施設の番号>"・"applicant"・"opponent"・"undecided"（未定）。
申し込む側は「未定」を選べ、申し込みを受けた側が確定するときに会場を決める（変更もできる）。
"""
from django.db.models import Q

from facilities.models import Facility
from schools.distance import distance_km

UNDECIDED = "undecided"


def _distance(location_a, location_b):
    """2地点の直線距離（km）。どちらかの位置が未取得なら None"""
    if None in (*location_a, *location_b):
        return None
    return round(distance_km(*location_a, *location_b), 1)


def _school_location(school):
    return school.latitude, school.longitude


def venue_candidates(applicant, opponent):
    """会場になれる施設を、両校からの距離といっしょに返す（申込側・相手側の部活動を渡す）"""
    sport = applicant.sport
    schools = [applicant.school, opponent.school]
    facilities = (
        Facility.objects.filter(sports=sport)
        .filter(Q(school__isnull=True) | Q(school__in=schools))
        .select_related("school").distinct()
    )

    rows = []
    for facility in facilities:
        location = facility.location
        dist_a = _distance(_school_location(applicant.school), location)
        dist_b = _distance(_school_location(opponent.school), location)
        total = round(dist_a + dist_b, 1) if dist_a is not None and dist_b is not None else None
        if facility.school_id == applicant.school_id:
            owner = "applicant"
        elif facility.school_id == opponent.school_id:
            owner = "opponent"
        else:
            owner = None
        rows.append({"facility": facility, "owner": owner,
                     "dist_a": dist_a, "dist_b": dist_b, "total": total})

    # 距離がわかる施設を先に、合計が小さい順。位置が未取得の施設は最後
    rows.sort(key=lambda r: (
        r["total"] is None,
        r["total"] if r["total"] is not None else 0,
        r["facility"].name,
    ))
    return rows


def venue_choices(applicant, opponent, rows, allow_undecided=False):
    """<select> に使う、グループ分けした会場の選択肢"""
    choices = [("", "会場を選択してください")]
    if allow_undecided:
        choices.append((UNDECIDED, "未定（相手校に決めてもらう）"))

    for owner, club in (("applicant", applicant), ("opponent", opponent)):
        school = club.school
        own = [r for r in rows if r["owner"] == owner]
        if own:
            options = [(f"facility:{r['facility'].pk}", f"{school.name}　{r['facility'].name}") for r in own]
        else:
            options = [(owner, f"{school.name}で実施（施設は未登録）")]
        choices.append((f"{school.name}の施設", options))

    public = []
    for r in rows:
        if r["owner"] is not None:
            continue
        if r["total"] is not None:
            label = f"{r['facility'].name}（両校からの距離の合計 {r['total']} km）"
        else:
            label = f"{r['facility'].name}（距離は不明）"
        public.append((f"facility:{r['facility'].pk}", label))
    if public:
        choices.append(("公共の施設（距離の近い順）", public))
    return choices


def parse_venue(value, rows, allow_undecided=False):
    """選択肢の値を (会場の種類, 施設) にする。候補にない値なら None"""
    from .models import PracticeMatch

    if value == UNDECIDED and allow_undecided:
        return PracticeMatch.VenueKind.UNDECIDED, None
    if value in ("applicant", "opponent"):
        # 学校内の施設が登録されている学校は、施設から選ぶ
        if any(r["owner"] == value for r in rows):
            return None
        return value, None
    if value.startswith("facility:"):
        pk = value.split(":", 1)[1]
        for r in rows:
            if str(r["facility"].pk) == pk:
                return PracticeMatch.VenueKind.FACILITY, r["facility"]
    return None


def choice_groups(choices):
    """venue_choices の結果を、テンプレートで <optgroup> を作りやすい形にする"""
    groups = []
    for value, label in choices:
        if isinstance(label, (list, tuple)):
            groups.append({"label": value, "options": list(label)})
        elif groups and groups[-1]["label"] is None:
            groups[-1]["options"].append((value, label))
        else:
            groups.append({"label": None, "options": [(value, label)]})
    return groups

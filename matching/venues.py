from facilities.models import Facility
from schools.distance import distance_km


def _distance(school, facility):
    """学校と施設の直線距離（km）。どちらかの位置が未取得なら None"""
    if None in (school.latitude, school.longitude, facility.latitude, facility.longitude):
        return None
    return round(
        distance_km(school.latitude, school.longitude, facility.latitude, facility.longitude),
        1,
    )


def venue_candidates(school_a, school_b, sport):
    """競技に対応する施設を、両校からの距離の合計が近い順に並べて返す"""
    rows = []
    for facility in Facility.objects.filter(sports=sport):
        dist_a = _distance(school_a, facility)
        dist_b = _distance(school_b, facility)
        if dist_a is not None and dist_b is not None:
            total = round(dist_a + dist_b, 1)
        else:
            total = None
        rows.append({"facility": facility, "dist_a": dist_a, "dist_b": dist_b, "total": total})

    # 距離がわかる施設を先に、合計が小さい順。位置が未取得の施設は最後
    rows.sort(key=lambda r: (
        r["total"] is None,
        r["total"] if r["total"] is not None else 0,
        r["facility"].name,
    ))
    return rows
from django.urls import reverse

from .menus import BOARD_MENU, BOARD_SECTIONS, TEACHER_MENU, TEACHER_SECTIONS


def build_menu(sections, menu, current_url_name=None, badges=None):
    """メニューを、グループ（section）ごとにまとめて返す。

    各項目には url（未実装なら None）、active（今開いている画面か）、
    badge_count（サイドバーに出す件数）を付ける。
    """
    badges = badges or {}
    result = []
    for section in sections:
        items = []
        for item in menu:
            if item["section"] != section["key"]:
                continue
            url = reverse(item["url_name"]) if item["url_name"] else None
            active = current_url_name in item.get("match_names", [])
            badge_count = badges.get(item.get("badge"), 0)
            items.append({**item, "url": url, "active": active, "badge_count": badge_count})
        result.append({**section, "items": items})
    return result


def teacher_badges(school):
    """顧問のサイドバーに出す件数（未読メッセージ、返事待ちの申し込み）"""
    # 循環 import を避けるため、ここで読み込む
    from matching.models import Message, PracticeMatch

    return {
        "unread_messages": Message.unread_for(school).count(),
        "pending_received": PracticeMatch.objects.filter(
            opponent_club__school=school, status=PracticeMatch.Status.PENDING
        ).count(),
    }


def navigation(request):
    """すべての画面に、サイドバーのメニューと、上部ヘッダーの表示内容を渡す（base.html で使う）"""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    match = request.resolver_match
    current = match.url_name if match else None

    if user.is_superuser or user.role == "board":
        return {
            "nav_sections": build_menu(BOARD_SECTIONS, BOARD_MENU, current),
            "nav_home_url": reverse("board_home"),
            "nav_is_home": current == "board_home",
            "nav_brand_icon": "M",
            "nav_brand_label": "ADMIN SYSTEM",
            "nav_portal_label": "ADMINISTRATION",
            "nav_user_name": "管理者",
        }

    school = user.school
    badges = teacher_badges(school) if school else {}
    return {
        "nav_sections": build_menu(TEACHER_SECTIONS, TEACHER_MENU, current, badges),
        "nav_home_url": reverse("teacher_home"),
        "nav_is_home": current == "teacher_home",
        "nav_brand_icon": "S",
        "nav_brand_label": "SCHOOL SYSTEM",
        "nav_portal_label": "SCHOOL PORTAL",
        "nav_user_name": school.name if school else user.username,
    }

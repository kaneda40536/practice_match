from django.urls import reverse

from .menus import BOARD_MENU, BOARD_SECTIONS, TEACHER_MENU, TEACHER_SECTIONS


def build_menu(sections, menu, current_url_name=None):
    """メニューを、グループ（section）ごとにまとめて返す。

    各項目には url（未実装なら None）と active（今開いている画面か）を付ける。
    """
    result = []
    for section in sections:
        items = []
        for item in menu:
            if item["section"] != section["key"]:
                continue
            url = reverse(item["url_name"]) if item["url_name"] else None
            active = current_url_name in item.get("match_names", [])
            items.append({**item, "url": url, "active": active})
        result.append({**section, "items": items})
    return result


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

    school_name = user.school.name if user.school else user.username
    return {
        "nav_sections": build_menu(TEACHER_SECTIONS, TEACHER_MENU, current),
        "nav_home_url": reverse("teacher_home"),
        "nav_is_home": current == "teacher_home",
        "nav_brand_icon": "S",
        "nav_brand_label": "SCHOOL SYSTEM",
        "nav_portal_label": "SCHOOL PORTAL",
        "nav_user_name": school_name,
    }

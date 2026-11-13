# url_name が None の項目は「準備中」と表示され、リンクになりません。
# 機能を作ったら、urls.py の name を入れてください。（例: "sport_list"）

# メニューは、ホーム画面のカードと、左サイドバーの両方に使います。
#   section     : どのグループに表示するか（*_SECTIONS のキー）
#   icon        : 表示する記号
#   color       : ホーム画面のカードのアイコンの色（blue / green / orange / purple / teal）
#   match_names : この画面を開いているとき、サイドバーの項目を光らせる url_name の一覧
#   badge       : サイドバーに件数を表示するときの種類（context_processors.teacher_badges を参照）


# ---------- 教育委員会（管理者）側 ----------

BOARD_SECTIONS = [
    {"key": "main", "label": "MAIN MENU",
     "title": "管理メニュー", "description": "管理する情報を選択してください。"},
]

BOARD_MENU = [
    {"title": "学校アカウント管理", "description": "学校アカウントの作成・パスワード再設定・利用状態の管理",
     "url_name": "school_account_list", "section": "main", "icon": "▣", "color": "blue",
     "match_names": ["school_account_list", "school_account_add",
                     "school_account_password", "school_account_toggle"]},
    {"title": "学校情報管理", "description": "各学校の基本情報を確認・管理",
     "url_name": "school_list", "section": "main", "icon": "▤", "color": "green",
     "match_names": ["school_list", "school_edit", "school_delete"]},
    {"title": "競技管理", "description": "システムで使用する競技の種類を管理",
     "url_name": "sport_list", "section": "main", "icon": "⚽", "color": "orange",
     "match_names": ["sport_list", "sport_add", "sport_edit", "sport_delete"]},
    {"title": "部活動一覧", "description": "各学校が登録した部活動を確認",
     "url_name": "club_list", "section": "main", "icon": "▦", "color": "purple",
     "match_names": ["club_list"]},
    {"title": "施設情報管理", "description": "練習試合で使用する施設を登録・管理",
     "url_name": "facility_list", "section": "main", "icon": "⌖", "color": "teal",
     "match_names": ["facility_list", "facility_add", "facility_edit", "facility_delete"]},
]


# ---------- 顧問（学校）側 ----------

TEACHER_SECTIONS = [
    {"key": "school", "label": "MAIN MENU",
     "title": "学校情報管理", "description": "学校や部活動に関する情報を管理します。"},
    {"key": "match", "label": "PRACTICE MATCH",
     "title": "練習試合管理", "description": "対戦相手の検索や試合の日程調整を行います。"},
    {"key": "contact", "label": "COMMUNICATION",
     "title": "連絡", "description": "対戦相手の学校と連絡を行います。"},
]

TEACHER_MENU = [
    {"title": "学校情報管理", "description": "自校の基本情報を確認",
     "url_name": "my_school", "section": "school", "icon": "▣", "color": "blue",
     "match_names": ["my_school"]},
    {"title": "部活動管理", "description": "自校の部活動と希望日を登録・確認",
     "url_name": "my_club_list", "section": "school", "icon": "▤", "color": "green",
     "match_names": ["my_club_list", "my_club_add", "my_club_delete", "club_availability"]},

    {"title": "対戦相手検索", "description": "希望日が重なる相手校を検索",
     "url_name": "opponent_search", "section": "match", "icon": "⌕", "color": "orange",
     "match_names": ["opponent_search", "match_request"]},
    {"title": "日程調整", "description": "相手校との共通の希望日を確認して申し込む",
     "url_name": "schedule", "section": "match", "icon": "▦", "color": "purple",
     "match_names": ["schedule"]},
    {"title": "届いた申し込み", "description": "他校から届いた申し込みを確認・対応",
     "url_name": "received_matches", "section": "match", "icon": "↓", "color": "teal",
     "match_names": ["received_matches"], "badge": "pending_received"},
    {"title": "申し込んだ試合", "description": "自校から申し込んだ試合の状況を確認",
     "url_name": "sent_matches", "section": "match", "icon": "↑", "color": "blue",
     "match_names": ["sent_matches"]},
    {"title": "予定試合一覧", "description": "確定した練習試合の日程を確認",
     "url_name": "planned_matches", "section": "match", "icon": "✓", "color": "green",
     "match_names": ["planned_matches"]},
    {"title": "試合結果管理", "description": "試合結果の登録・確認",
     "url_name": "match_results", "section": "match", "icon": "★", "color": "orange",
     "match_names": ["match_results", "match_result_edit"]},

    {"title": "メッセージ", "description": "他校との会話を確認・開始",
     "url_name": "message_list", "section": "contact", "icon": "✉", "color": "purple",
     "match_names": ["message_list", "message_room"], "badge": "unread_messages"},
]

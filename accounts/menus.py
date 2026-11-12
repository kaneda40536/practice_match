# url_name が None の項目は「準備中」と表示され、リンクになりません。
# 機能を作ったら、urls.py の name を入れてください。（例: "sport_list"）

BOARD_MENU = [
    {"title": "学校アカウント管理", "description": "学校アカウントの作成・編集・利用状態の管理",
     "url_name": "school_account_list", "icon": "bi-people-fill", "color": "blue"},
    {"title": "競技管理", "description": "システムで使用する競技の種類を管理",
     "url_name": "sport_list", "icon": "bi-dribbble", "color": "orange"},
    {"title": "部活動一覧", "description": "各学校が登録した部活動を確認",
     "url_name": "club_list", "icon": "bi-grid-fill", "color": "purple"},
    {"title": "施設情報管理", "description": "練習試合で使用する施設を登録・管理",
     "url_name": "facility_list", "icon": "bi-geo-alt-fill", "color": "teal"},
]

TEACHER_MENU = [
    {"title": "学校情報管理", "description": "学校の基本情報を確認・編集", "url_name": "my_school"},
    {"title": "部活動管理", "description": "自校の部活動を登録・確認", "url_name": "my_club_list"},
    {"title": "対戦相手検索", "description": "練習試合の相手校を探す", "url_name": "opponent_search"},
    {"title": "日程調整", "description": "練習試合の日程を調整する", "url_name": None},
    {"title": "届いた申し込み", "description": "他校から届いた練習試合の申し込みを確認する", "url_name": None},
    {"title": "申し込んだ試合", "description": "自校から申し込んだ練習試合の状況を確認する", "url_name": None},
    {"title": "予定試合一覧", "description": "確定した練習試合の日程を確認する", "url_name": None},
    {"title": "試合結果管理", "description": "試合結果を登録・確認する", "url_name": None},
    {"title": "メッセージ", "description": "相手校との会話を確認・開始する", "url_name": None},
]
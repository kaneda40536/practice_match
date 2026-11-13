from django.urls import path
from . import views

urlpatterns = [
    # 希望日
    path("clubs/<int:club_pk>/dates/", views.ClubAvailabilityView.as_view(), name="club_availability"),
    path("dates/<int:pk>/delete/", views.AvailabilityDeleteView.as_view(), name="availability_delete"),

    # 対戦相手検索
    path("search/", views.OpponentSearchView.as_view(), name="opponent_search"),

    # 練習試合の申し込み
    path("apply/<int:club_pk>/<int:opponent_pk>/", views.MatchRequestView.as_view(), name="match_request"),
    path("sent/", views.SentMatchListView.as_view(), name="sent_matches"),
    path("received/", views.ReceivedMatchListView.as_view(), name="received_matches"),
    path("matches/<int:pk>/withdraw/", views.MatchWithdrawView.as_view(), name="match_withdraw"),
    path("matches/<int:pk>/approve/", views.MatchApproveView.as_view(), name="match_approve"),
    path("matches/<int:pk>/decline/", views.MatchDeclineView.as_view(), name="match_decline"),

    # 日程調整
    path("schedule/", views.ScheduleView.as_view(), name="schedule"),

    # 予定試合・試合結果
    path("planned/", views.PlannedMatchListView.as_view(), name="planned_matches"),
    path("results/", views.MatchResultListView.as_view(), name="match_results"),
    path("matches/<int:pk>/result/", views.MatchResultEditView.as_view(), name="match_result_edit"),
    path("results/<int:pk>/delete/", views.MatchResultDeleteView.as_view(), name="match_result_delete"),

    # メッセージ
    path("messages/", views.MessageListView.as_view(), name="message_list"),
    path("messages/<int:school_pk>/", views.MessageRoomView.as_view(), name="message_room"),
]
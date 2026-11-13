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
]
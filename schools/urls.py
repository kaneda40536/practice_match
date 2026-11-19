from django.urls import path
from . import views

urlpatterns = [
    # 競技管理（教育委員会）
    path("sports/", views.SportListView.as_view(), name="sport_list"),
    path("sports/add/", views.SportCreateView.as_view(), name="sport_add"),
    path("sports/<int:pk>/edit/", views.SportUpdateView.as_view(), name="sport_edit"),
    path("sports/<int:pk>/delete/", views.SportDeleteView.as_view(), name="sport_delete"),

    # 学校情報管理（教育委員会）
    path("manage/", views.SchoolListView.as_view(), name="school_list"),
    path("manage/<int:pk>/edit/", views.SchoolUpdateView.as_view(), name="school_edit"),
    path("manage/<int:pk>/delete/", views.SchoolDeleteView.as_view(), name="school_delete"),

    # 部活動一覧（教育委員会）
    path("clubs/", views.ClubListView.as_view(), name="club_list"),

    # 自校の情報・部活動（顧問）
    path("my/school/", views.MySchoolView.as_view(), name="my_school"),
    path("my/clubs/", views.MyClubListView.as_view(), name="my_club_list"),
    path("my/clubs/add/", views.MyClubCreateView.as_view(), name="my_club_add"),
    path("my/clubs/<int:pk>/delete/", views.MyClubDeleteView.as_view(), name="my_club_delete"),
    path("my/clubs/<int:pk>/level/", views.MyClubLevelView.as_view(), name="my_club_level"),

    # 大会成績管理（顧問）
    path("my/tournaments/", views.TournamentResultListView.as_view(), name="tournament_results"),
    path("my/tournaments/<int:pk>/edit/", views.TournamentResultUpdateView.as_view(), name="tournament_result_edit"),
    path("my/tournaments/<int:pk>/delete/", views.TournamentResultDeleteView.as_view(), name="tournament_result_delete"),
]
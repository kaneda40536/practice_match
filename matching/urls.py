from django.urls import path
from . import views

urlpatterns = [
    path("clubs/<int:club_pk>/dates/", views.ClubAvailabilityView.as_view(), name="club_availability"),
    path("dates/<int:pk>/delete/", views.AvailabilityDeleteView.as_view(), name="availability_delete"),
    path("search/", views.OpponentSearchView.as_view(), name="opponent_search"),
]
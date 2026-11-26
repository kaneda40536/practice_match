from django.urls import path
from . import views

urlpatterns = [
    path("", views.FacilityListView.as_view(), name="facility_list"),
    path("add/", views.FacilityCreateView.as_view(), name="facility_add"),
    path("<int:pk>/edit/", views.FacilityUpdateView.as_view(), name="facility_edit"),
    path("<int:pk>/delete/", views.FacilityDeleteView.as_view(), name="facility_delete"),
]
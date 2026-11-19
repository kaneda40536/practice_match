from django.urls import path
from . import views

urlpatterns = [
    path("", views.FacilityListView.as_view(), name="facility_list"),
    path("add/", views.FacilityCreateView.as_view(), name="facility_add"),
    path("<int:pk>/edit/", views.FacilityUpdateView.as_view(), name="facility_edit"),
    path("<int:pk>/delete/", views.FacilityDeleteView.as_view(), name="facility_delete"),

    # 会場管理（顧問：学校内の施設）
    path("my/", views.SchoolFacilityListView.as_view(), name="my_facility_list"),
    path("my/<int:pk>/edit/", views.SchoolFacilityUpdateView.as_view(), name="my_facility_edit"),
    path("my/<int:pk>/delete/", views.SchoolFacilityDeleteView.as_view(), name="my_facility_delete"),
]
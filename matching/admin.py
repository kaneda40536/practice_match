from django.contrib import admin
from .models import Availability, PracticeMatch


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("club", "date", "can_host")
    list_filter = ("can_host",)


@admin.register(PracticeMatch)
class PracticeMatchAdmin(admin.ModelAdmin):
    list_display = ("applicant_club", "opponent_club", "date", "status")
    list_filter = ("status",)
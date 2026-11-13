from django.contrib import admin
from .models import Availability, MatchResult, Message, PracticeMatch


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("club", "date", "can_host")
    list_filter = ("can_host",)


@admin.register(PracticeMatch)
class PracticeMatchAdmin(admin.ModelAdmin):
    list_display = ("applicant_club", "opponent_club", "date", "status")
    list_filter = ("status",)

@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ("match", "applicant_score", "opponent_score", "updated_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "receiver", "created_at", "is_read")
    list_filter = ("is_read",)

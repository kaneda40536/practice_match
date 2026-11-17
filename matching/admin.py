from django.contrib import admin

from .models import Availability, CandidateDate, Conversation, MatchResult, Message, PracticeMatch


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("club", "date", "can_host")
    list_filter = ("can_host",)


class CandidateDateInline(admin.TabularInline):
    model = CandidateDate
    extra = 0


@admin.register(PracticeMatch)
class PracticeMatchAdmin(admin.ModelAdmin):
    list_display = ("applicant_club", "opponent_club", "status", "date", "created_at")
    list_filter = ("status",)
    inlines = [CandidateDateInline]


@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ("match", "applicant_score", "opponent_score", "updated_at")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("school_a", "school_b", "club_a", "club_b", "match", "last_message_at")
    inlines = [MessageInline]

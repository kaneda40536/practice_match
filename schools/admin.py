from django.contrib import admin
from .models import Sport, Area, School, Club, TournamentResult


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "address")


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("school", "sport", "gender")
    list_filter = ("sport", "gender")

@admin.register(TournamentResult)
class TournamentResultAdmin(admin.ModelAdmin):
    list_display = ("club", "fiscal_year", "tournament_name", "level", "achievement")
    list_filter = ("level", "fiscal_year")

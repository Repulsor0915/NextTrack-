from django.contrib import admin

from .models import Track, TrackFeatures


class TrackFeaturesInline(admin.StackedInline):
    model = TrackFeatures
    extra = 0


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "artist", "genre", "year", "data_source")
    list_filter = ("genre", "data_source")
    search_fields = ("id", "title", "artist")
    inlines = (TrackFeaturesInline,)

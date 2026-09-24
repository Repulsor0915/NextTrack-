from django.contrib import admin
from django.utils import timezone

from .models import CatalogueState, Track, TrackFeatures, TrackSuggestion


admin.site.site_header = "NextTrack administration"
admin.site.site_title = "NextTrack admin"
admin.site.index_title = "Catalogue operations"


class ReadOnlyCatalogueAdmin(admin.ModelAdmin):
    """Catalogue snapshots are changed only through the verified importer."""

    actions = None
    show_full_result_count = False
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Track)
class TrackAdmin(ReadOnlyCatalogueAdmin):
    list_display = ("id", "title", "artist", "year", "explicit", "data_source")
    list_filter = ("explicit", "year", "data_source")
    search_fields = ("id", "title", "artist")
    search_help_text = "Search by track ID, title, or artist."
    fields = ("id", "title", "artist", "genres", "explicit", "year", "data_source")
    readonly_fields = fields


@admin.register(TrackFeatures)
class TrackFeaturesAdmin(ReadOnlyCatalogueAdmin):
    list_display = ("track", "tempo", "energy", "valence", "feature_source")
    list_filter = ("feature_source",)
    list_select_related = ("track",)
    search_fields = ("track__id", "track__title", "track__artist")
    search_help_text = "Search by track ID, title, or artist."
    fields = (
        "track", "tempo", "energy", "valence", "danceability", "acousticness",
        "instrumentalness", "loudness", "speechiness", "feature_source",
    )
    readonly_fields = fields


@admin.register(CatalogueState)
class CatalogueStateAdmin(ReadOnlyCatalogueAdmin):
    list_display = (
        "version", "record_count", "actual_track_count", "actual_feature_count",
        "snapshot_consistent", "imported_at",
    )
    fields = (
        "version", "catalogue_sha256", "record_count", "actual_track_count",
        "actual_feature_count", "snapshot_consistent", "import_mode", "imported_at",
    )
    readonly_fields = fields

    @admin.display(description="Track rows")
    def actual_track_count(self, obj):
        return Track.objects.count()

    @admin.display(description="Feature rows")
    def actual_feature_count(self, obj):
        return TrackFeatures.objects.count()

    @admin.display(boolean=True, description="Snapshot consistent")
    def snapshot_consistent(self, obj):
        return (
            Track.objects.count() == TrackFeatures.objects.count() == obj.record_count
            and not Track.objects.exclude(data_source=obj.version).exists()
            and not TrackFeatures.objects.exclude(feature_source=obj.version).exists()
        )


@admin.register(TrackSuggestion)
class TrackSuggestionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "artist", "album_name", "status", "submitted_at", "reviewed_at",
    )
    list_filter = ("status", "submitted_at")
    search_fields = ("title", "artist", "album_name", "reference_url")
    search_help_text = "Search by title, artist, album, or reference URL."
    ordering = ("-submitted_at", "-id")
    actions = None
    fields = (
        "title", "artist", "album_name", "reference_url", "note", "submitted_at", "status",
        "reviewed_at",
    )
    readonly_fields = (
        "title", "artist", "album_name", "reference_url", "note", "submitted_at", "reviewed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        previous_status = (
            TrackSuggestion.objects.filter(pk=obj.pk)
            .values_list("status", flat=True)
            .first()
        )
        if obj.status == TrackSuggestion.Status.PENDING:
            obj.reviewed_at = None
        elif obj.status != previous_status or obj.reviewed_at is None:
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)

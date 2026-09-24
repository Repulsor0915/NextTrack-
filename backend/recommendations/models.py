from symtable import Class

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Artist(models.Model):
    name = models.CharField(max_length=255, unique=True)


class Album(models.Model):
    name = models.CharField(max_length=255)
    artist = models.ForeignKey(
        Artist,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="albums",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("artist", "name"), name="unique_album_artist_name"
            ),
        ]


class Track(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    title = models.CharField(max_length=255)
    artist = models.CharField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
    )
    genres = models.JSONField(default=list, blank=True)
    explicit = models.BooleanField(default=False)
    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2100)],
    )
    data_source = models.CharField(max_length=100, default="unknown", db_index=True)

    artist_display = models.TextField(null=True, blank=True)
    album_display = models.TextField(null=True, blank=True)
    primary_artist = models.ForeignKey(
        Artist,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="primary_tracks",
    )
    album = models.ForeignKey(
        Album,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tracks",
    )

    class Meta:
        ordering = ["artist", "title", "id"]

    def __str__(self):
        return f"{self.title} — {self.artist}"


class TrackArtist(models.Model):
    track = models.ForeignKey(
        Track, on_delete=models.CASCADE, related_name="track_artists"
    )
    artist = models.ForeignKey(
        Artist, on_delete=models.PROTECT, related_name="track_links"
    )
    position = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("track", "artist"), name="unique_track_artist"
            ),
            models.UniqueConstraint(
                fields=("track", "position"), name="unique_track_artist_position"
            ),
        ]


class TrackFeatures(models.Model):
    """Numeric audio features used by the recommendation algorithms."""

    track = models.OneToOneField(
        Track,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="features",
    )
    tempo = models.FloatField(validators=[MinValueValidator(0)])
    energy = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    valence = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    danceability = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    acousticness = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    instrumentalness = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    loudness = models.FloatField()
    speechiness = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    feature_source = models.CharField(max_length=100, default="unknown")

    class Meta:
        verbose_name_plural = "track features"

    def __str__(self):
        return f"Features for {self.track}"


class CatalogueState(models.Model):
    """The single verified catalogue snapshot active in this database."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    version = models.CharField(max_length=100)
    catalogue_sha256 = models.CharField(max_length=64)
    record_count = models.PositiveIntegerField()
    imported_at = models.DateTimeField(auto_now=True)
    import_mode = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="single_catalogue_state"
            )
        ]

    def __str__(self):
        return f"{self.version} ({self.record_count} tracks)"


class TrackGenre(models.Model):
    """A derived exact-match index for the catalogue's genre labels."""

    track = models.ForeignKey(
        Track, on_delete=models.CASCADE, related_name="genre_index"
    )
    name = models.CharField(max_length=100)
    normalized_name = models.CharField(max_length=255, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("track", "normalized_name"),
                name="unique_track_genre_name",
            )
        ]


class TrackSuggestion(models.Model):
    """A request to review a track, never an active catalogue entry."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED = "reviewed", "Reviewed"
        REJECTED = "rejected", "Rejected"

    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    album_name = models.CharField(max_length=255, blank=True)
    reference_url = models.URLField(blank=True)
    note = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

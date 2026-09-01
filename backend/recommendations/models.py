from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Track(models.Model):
    """Catalogue metadata for a track that can be recommended."""

    id = models.CharField(primary_key=True, max_length=100)
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255, db_index=True)
    genre = models.CharField(max_length=100, blank=True, db_index=True)
    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2100)],
    )
    data_source = models.CharField(max_length=100, default="unknown", db_index=True)

    class Meta:
        ordering = ["artist", "title", "id"]

    def __str__(self):
        return f"{self.title} — {self.artist}"


class TrackFeatures(models.Model):
    """Numeric audio features used by the recommendation algorithms."""

    track = models.OneToOneField(
        Track,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="features",
    )
    tempo = models.FloatField(validators=[MinValueValidator(0)])
    energy = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    valence = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
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

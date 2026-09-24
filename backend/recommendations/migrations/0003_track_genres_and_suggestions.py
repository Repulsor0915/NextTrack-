import django.db.models.deletion
from django.db import migrations, models


def populate_genre_index(apps, schema_editor):
    Track = apps.get_model("recommendations", "Track")
    TrackGenre = apps.get_model("recommendations", "TrackGenre")
    database = schema_editor.connection.alias
    pending = []
    for track in Track.objects.using(database).order_by().values(
        "id", "genres"
    ).iterator(chunk_size=500):
        seen = set()
        for name in track["genres"] or []:
            normalized = name.strip().casefold()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            pending.append(
                TrackGenre(
                    track_id=track["id"], name=name,
                    normalized_name=normalized,
                )
            )
        if len(pending) >= 500:
            TrackGenre.objects.using(database).bulk_create(pending, batch_size=500)
            pending.clear()
    if pending:
        TrackGenre.objects.using(database).bulk_create(pending, batch_size=500)


class Migration(migrations.Migration):
    # Existing databases may have applied the earlier migration filename.
    replaces = [("recommendations", "0003_stage_five")]
    dependencies = [("recommendations", "0002_cataloguestate")]

    operations = [
        migrations.CreateModel(
            name="TrackGenre",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("normalized_name", models.CharField(db_index=True, max_length=255)),
                (
                    "track",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="genre_index",
                        to="recommendations.track",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TrackSuggestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("artist", models.CharField(max_length=255)),
                ("reference_url", models.URLField(blank=True)),
                ("note", models.CharField(blank=True, max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("reviewed", "Reviewed"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True, default="pending", max_length=16,
                    ),
                ),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="trackgenre",
            constraint=models.UniqueConstraint(
                fields=("track", "normalized_name"),
                name="unique_track_genre_name",
            ),
        ),
        migrations.RunPython(populate_genre_index, migrations.RunPython.noop),
    ]

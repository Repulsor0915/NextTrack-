import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.models import Track, TrackFeatures


FEATURE_FIELDS = (
    "tempo",
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
    "loudness",
    "speechiness",
)


class Command(BaseCommand):
    help = "Import or update a JSON track catalogue and its audio features."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=Path,
            help="Path to a JSON file containing a list of tracks.",
        )
        parser.add_argument(
            "--data-source",
            default="unknown",
            help="Provenance label stored with every imported track.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = options["path"].expanduser().resolve()
        data_source = options["data_source"].strip()

        if not data_source:
            raise CommandError("--data-source cannot be empty.")

        catalogue = self._read_catalogue(path)
        created_count = 0
        updated_count = 0
        seen_ids = set()

        for index, item in enumerate(catalogue, start=1):
            try:
                track_id = item["id"]
                if track_id in seen_ids:
                    raise ValueError(f'duplicate track id "{track_id}"')
                seen_ids.add(track_id)

                features_data = item["features"]
                if not isinstance(features_data, dict):
                    raise TypeError("features must be a JSON object")

                track = Track.objects.filter(pk=track_id).first()
                was_created = track is None
                if was_created:
                    track = Track(id=track_id)

                track.title = item["title"]
                track.artist = item["artist"]
                track.genre = item.get("genre", "")
                track.year = item.get("year")
                track.data_source = data_source
                track.full_clean()
                track.save()

                features = TrackFeatures.objects.filter(track=track).first()
                if features is None:
                    features = TrackFeatures(track=track)

                for field_name in FEATURE_FIELDS:
                    setattr(features, field_name, features_data[field_name])
                features.feature_source = data_source
                features.full_clean()
                features.save()
            except (KeyError, TypeError, ValueError, ValidationError) as error:
                raise CommandError(f"Invalid track at item {index}: {error}") from error

            if was_created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(catalogue)} tracks from {path} "
                f"({created_count} created, {updated_count} updated)."
            )
        )

    @staticmethod
    def _read_catalogue(path):
        if not path.is_file():
            raise CommandError(f"Catalogue file does not exist: {path}")

        try:
            with path.open(encoding="utf-8") as catalogue_file:
                catalogue = json.load(catalogue_file)
        except json.JSONDecodeError as error:
            raise CommandError(f"Catalogue is not valid JSON: {error}") from error
        except OSError as error:
            raise CommandError(f"Could not read catalogue: {error}") from error

        if not isinstance(catalogue, list):
            raise CommandError("Catalogue root must be a JSON list.")

        return catalogue

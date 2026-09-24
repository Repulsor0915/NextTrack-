## This file writes validated catalogue records into the database in batches.
## It creates and updates tracks, features, artists, albums, genres, and artist links.

from recommendations.audio_features import FEATURE_NAMES
from recommendations.models import (
    Album,
    Artist,
    Track,
    TrackArtist,
    TrackFeatures,
    TrackGenre,
)

BATCH_SIZE = 500
TRACK_UPDATE_FIELDS = (
    "title",
    "artist",
    "artist_display",
    "album_display",
    "primary_artist",
    "album",
    "genres",
    "explicit",
    "year",
    "data_source",
)
FEATURE_UPDATE_FIELDS = (*FEATURE_NAMES, "feature_source")


def _parse_artist_names(raw):
    names = []
    seen = set()
    for part in (raw or "").split(";"):
        name = part.strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _artists_for_batch(names_by_track):
    names = {name for track_names in names_by_track.values() for name in track_names}
    if not names:
        return {}
    existing = Artist.objects.in_bulk(names, field_name="name")
    missing = names - existing.keys()
    if missing:
        Artist.objects.bulk_create(
            [Artist(name=name) for name in sorted(missing)],
            ignore_conflicts=True,
            batch_size=BATCH_SIZE,
        )
    return Artist.objects.in_bulk(names, field_name="name")


def _albums_for_batch(batch, names_by_track, artists_by_name):
    keys = set()
    for item in batch:
        names = names_by_track[item["id"]]
        name = (item["album_display"] or "").strip()
        if names and name and len(name) <= 255:
            keys.add((artists_by_name[names[0]].pk, name))
    if not keys:
        return {}

    artist_ids = {artist_id for artist_id, _ in keys}
    album_names = sorted({name for _, name in keys})

    def find_existing():
        found = {}
        # Keep the combined IN parameters below SQLite's older 999 limit.
        for start in range(0, len(album_names), 300):
            for album in Album.objects.filter(
                artist_id__in=artist_ids,
                name__in=album_names[start : start + 300],
            ):
                key = (album.artist_id, album.name)
                if key in keys:
                    found[key] = album
        return found

    existing = find_existing()
    missing = keys - existing.keys()
    if missing:
        Album.objects.bulk_create(
            [Album(artist_id=artist_id, name=name) for artist_id, name in sorted(missing)],
            ignore_conflicts=True,
            batch_size=BATCH_SIZE,
        )
        existing = find_existing()
    return existing


## Save the verified catalogue
def _write_batches(records, existing_ids, version):
    for batch in _batches(records):
        names_by_track = {
            item["id"]: _parse_artist_names(item["artist_display"])
            for item in batch
        }
        artists_by_name = _artists_for_batch(names_by_track)
        albums_by_key = _albums_for_batch(batch, names_by_track, artists_by_name)
        new_tracks = []
        changed_tracks = []
        new_features = []
        changed_features = []
        genre_entries = []
        artist_entries = []
        changed_ids = []
        for item in batch:
            track_id = item["id"]
            names = names_by_track[track_id]
            primary_artist = artists_by_name[names[0]] if names else None
            album_name = (item["album_display"] or "").strip()
            album = (
                albums_by_key.get((primary_artist.pk, album_name))
                if primary_artist is not None
                else None
            )
            track = Track(
                id=track_id,
                title=item["title"],
                artist=names[0] if names else None,
                artist_display=item["artist_display"],
                album_display=item["album_display"],
                primary_artist=primary_artist,
                album=album,
                genres=item.get("genres", []),
                explicit=item["explicit"],
                year=item.get("year"),
                data_source=version,
            )
            features = TrackFeatures(
                track_id=track_id,
                feature_source=version,
                **item["features"],
            )
            if track_id in existing_ids:
                changed_tracks.append(track)
                changed_features.append(features)
                changed_ids.append(track_id)
            else:
                new_tracks.append(track)
                new_features.append(features)

            artist_entries.extend(
                TrackArtist(
                    track_id=track_id,
                    artist=artists_by_name[name],
                    position=position,
                )
                for position, name in enumerate(names)
            )

            seen_genres = set()
            for name in item.get("genres", []):
                normalized = name.strip().casefold()
                if normalized not in seen_genres:
                    seen_genres.add(normalized)
                    genre_entries.append(
                        TrackGenre(
                            track_id=track_id,
                            name=name,
                            normalized_name=normalized,
                        )
                    )

        if new_tracks:
            Track.objects.bulk_create(new_tracks, batch_size=BATCH_SIZE)
            TrackFeatures.objects.bulk_create(new_features, batch_size=BATCH_SIZE)
        if changed_tracks:
            Track.objects.bulk_update(
                changed_tracks, TRACK_UPDATE_FIELDS, batch_size=BATCH_SIZE
            )
            TrackFeatures.objects.bulk_update(
                changed_features, FEATURE_UPDATE_FIELDS, batch_size=BATCH_SIZE
            )
            TrackGenre.objects.filter(track_id__in=changed_ids).delete()
            TrackArtist.objects.filter(track_id__in=changed_ids).delete()
        if genre_entries:
            TrackGenre.objects.bulk_create(genre_entries, batch_size=BATCH_SIZE)
        if artist_entries:
            TrackArtist.objects.bulk_create(artist_entries, batch_size=BATCH_SIZE)


def _batches(items):
    for start in range(0, len(items), BATCH_SIZE):
        yield items[start : start + BATCH_SIZE]

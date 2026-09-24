from rest_framework import serializers

from recommendations.models import Track, TrackFeatures, TrackSuggestion


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {name: "Unknown field." for name in sorted(unknown)}
                )
        return super().to_internal_value(data)


class BpmRangeSerializer(StrictSerializer):
    min = serializers.FloatField(min_value=0)
    max = serializers.FloatField(min_value=0)

    def validate(self, attrs):
        if attrs["min"] >= attrs["max"]:
            raise serializers.ValidationError("min must be lower than max.")
        return attrs


class ContextSerializer(StrictSerializer):
    mood = serializers.ChoiceField(
        choices=["happy", "energetic", "calm", "sad"],
        required=False,
    )
    bpm = BpmRangeSerializer(required=False)
    diversity_strength = serializers.FloatField(
        min_value=0,
        max_value=1,
        required=False,
        default=0.2,
    )

    def to_internal_value(self, data):
        if isinstance(data, dict) and "exploration" in data:
            raise serializers.ValidationError(
                {
                    "exploration": (
                        "This field was renamed to diversity_strength."
                    )
                }
            )
        return super().to_internal_value(data)


class RecommendationRequestSerializer(StrictSerializer):
    history = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        max_length=50,
        required=False,
        default=list,
    )
    algorithm = serializers.ChoiceField(
        choices=["auto", "random", "cbf", "context_mmr"],
        default="auto",
    )
    limit = serializers.IntegerField(
        min_value=1,
        max_value=20,
        default=5,
    )
    context = ContextSerializer(required=False)
    mood = serializers.ChoiceField(
        choices=["happy", "energetic", "calm", "sad"], required=False,
        help_text="User-facing alias for context.mood.",
    )
    bpm = BpmRangeSerializer(
        required=False, help_text="User-facing alias for context.bpm."
    )
    diversity_strength = serializers.FloatField(
        min_value=0, max_value=1, required=False,
        help_text="User-facing alias for context.diversity_strength.",
    )
    candidate_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        max_length=500,
    )

    def validate(self, attrs):
        algorithm = attrs["algorithm"]
        history = attrs["history"]
        context = dict(attrs.get("context", {}))
        for name in ("mood", "bpm", "diversity_strength"):
            if name in attrs:
                if name in context:
                    raise serializers.ValidationError(
                        {name: f"Use either {name} or context.{name}, not both."}
                    )
                context[name] = attrs.pop(name)
        attrs["context"] = context

        if algorithm == "cbf" and not history:
            raise serializers.ValidationError(
                {
                    "history": (
                        "At least one history track is required " "for this algorithm."
                    )
                }
            )
        if algorithm == "context_mmr" and not history and not context.get("mood"):
            raise serializers.ValidationError(
                {
                    "history": (
                        "Provide at least one history track or a mood "
                        "for the context_mmr algorithm."
                    )
                }
            )
        return attrs


class TrackQuerySerializer(StrictSerializer):
    q = serializers.CharField(max_length=100, required=False)
    artist = serializers.CharField(max_length=255, required=False)
    genre = serializers.CharField(max_length=100, required=False)
    bpm_min = serializers.FloatField(min_value=0, required=False)
    bpm_max = serializers.FloatField(min_value=0, required=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=100, required=False, default=20
    )

    def validate(self, attrs):
        if (
            "bpm_min" in attrs and "bpm_max" in attrs
            and attrs["bpm_min"] > attrs["bpm_max"]
        ):
            raise serializers.ValidationError(
                {"bpm_max": "Must be greater than or equal to bpm_min."}
            )
        return attrs


class TrackFeaturesResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackFeatures
        fields = (
            "tempo", "energy", "valence", "danceability", "acousticness",
            "instrumentalness", "loudness", "speechiness",
        )


class TrackSummarySerializer(serializers.ModelSerializer):
    tempo = serializers.FloatField(source="features.tempo", read_only=True)

    class Meta:
        model = Track
        fields = ("id", "title", "artist", "genres", "explicit", "year", "tempo")


class TrackDetailSerializer(serializers.ModelSerializer):
    features = TrackFeaturesResponseSerializer(read_only=True)

    class Meta:
        model = Track
        fields = ("id", "title", "artist", "genres", "explicit", "year", "features")


class CatalogueResponseSerializer(serializers.Serializer):
    version = serializers.CharField()
    catalogue_sha256 = serializers.CharField()
    record_count = serializers.IntegerField()
    imported_at = serializers.DateTimeField()


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class RecommendationTrackResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    artist = serializers.CharField()


class ExplanationResponseSerializer(serializers.Serializer):
    summary = serializers.CharField()
    evidence = serializers.ListField(child=serializers.CharField())


class RecommendationItemResponseSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    track = RecommendationTrackResponseSerializer()
    score = serializers.FloatField(allow_null=True)
    components = serializers.DictField()
    explanation = ExplanationResponseSerializer()
    explanation_evidence = serializers.DictField()


class RecommendationResponseSerializer(serializers.Serializer):
    algorithm = serializers.CharField()
    recommendations = RecommendationItemResponseSerializer(many=True)
    meta = serializers.DictField()


class SuggestionCreateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=255)
    artist = serializers.CharField(max_length=255)
    album_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    reference_url = serializers.URLField(required=False, allow_blank=True)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class SuggestionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackSuggestion
        fields = ("id", "title", "artist", "album_name", "status", "submitted_at")


class StaffSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackSuggestion
        fields = (
            "id", "title", "artist", "album_name", "reference_url", "note", "status",
            "submitted_at", "reviewed_at",
        )


class SuggestionReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=("reviewed", "rejected"))


class StaffCatalogueResponseSerializer(CatalogueResponseSerializer):
    track_count = serializers.IntegerField()
    feature_count = serializers.IntegerField()
    genre_entry_count = serializers.IntegerField()
    state_consistent = serializers.BooleanField()


class ApiErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ApiErrorResponseSerializer(serializers.Serializer):
    error = ApiErrorDetailSerializer()

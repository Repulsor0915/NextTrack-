from rest_framework import serializers


class BpmRangeSerializer(serializers.Serializer):
    min = serializers.FloatField(min_value=0)
    max = serializers.FloatField(min_value=0)

    def validate(self, attrs):
        if attrs["min"] >= attrs["max"]:
            raise serializers.ValidationError("min must be lower than max.")
        return attrs


class ContextSerializer(serializers.Serializer):
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


class RecommendationRequestSerializer(serializers.Serializer):
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
        max_value=10,
        default=5,
    )
    context = ContextSerializer(required=False)
    candidate_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        max_length=500,
    )

    def validate(self, attrs):
        algorithm = attrs["algorithm"]
        history = attrs["history"]
        context = attrs.get("context", {})

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

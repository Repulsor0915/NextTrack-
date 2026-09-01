from rest_framework.response import Response
from rest_framework.views import APIView

from recommendations.services.recommendation_service import (
    RecommendationService,
    RecommendationServiceError,
)

from .serializers import RecommendationRequestSerializer


class RecommendationView(APIView):
    def post(self, request):
        serializer = RecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        if data["algorithm"] in {"random", "cbf", "context_mmr"}:
            try:
                result = RecommendationService().recommend(data)
            except RecommendationServiceError as error:
                return Response(
                    {"error": error.as_dict()},
                    status=error.status_code,
                )
            return Response(result)

        return Response(
            {
                "algorithm": data["algorithm"],
                "recommendations": [],
                "meta": {
                    "status": "placeholder",
                },
            }
        )

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, pagination, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from recommendations.models import (
    CatalogueState, Track, TrackFeatures, TrackGenre, TrackSuggestion,
)
from recommendations.services.recommendation_service import (
    RecommendationService, RecommendationServiceError,
)

from .serializers import (
    ApiErrorResponseSerializer, CatalogueResponseSerializer, HealthResponseSerializer,
    RecommendationRequestSerializer, RecommendationResponseSerializer,
    StaffCatalogueResponseSerializer, StaffSuggestionSerializer,
    SuggestionCreateSerializer, SuggestionResponseSerializer,
    SuggestionReviewSerializer, TrackDetailSerializer,
    TrackQuerySerializer, TrackSummarySerializer,
)


class CatalogueUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "No verified active catalogue is available."
    default_code = "catalogue_unavailable"


class TrackPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(responses=HealthResponseSerializer)
    def get(self, request):
        return Response({"status": "ok"})


class CatalogueView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "track_reads"

    @extend_schema(
        responses={
            200: CatalogueResponseSerializer,
            429: ApiErrorResponseSerializer,
            503: ApiErrorResponseSerializer,
        }
    )
    def get(self, request):
        state = CatalogueState.objects.filter(pk=1).first()
        if state is None:
            raise CatalogueUnavailable()
        result = {
            "version": state.version,
            "catalogue_sha256": state.catalogue_sha256,
            "record_count": state.record_count,
            "imported_at": state.imported_at,
        }
        return Response(CatalogueResponseSerializer(result).data)


TRACK_PARAMETERS = [
    OpenApiParameter("q", str, description="Partial title or artist search."),
    OpenApiParameter("artist", str, description="Exact artist-field match."),
    OpenApiParameter("genre", str, description="Exact genre-label match."),
    OpenApiParameter("bpm_min", float),
    OpenApiParameter("bpm_max", float),
    OpenApiParameter("page", int),
    OpenApiParameter("page_size", int),
]


class TrackListView(generics.ListAPIView):
    serializer_class = TrackSummarySerializer
    pagination_class = TrackPagination
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "track_reads"

    def get_queryset(self):
        parameters = TrackQuerySerializer(data=self.request.query_params)
        parameters.is_valid(raise_exception=True)
        filters = parameters.validated_data
        queryset = Track.objects.select_related("features").filter(
            features__isnull=False
        )
        if "q" in filters:
            queryset = queryset.filter(
                Q(title__icontains=filters["q"])
                | Q(artist__icontains=filters["q"])
            )
        if "artist" in filters:
            queryset = queryset.filter(artist__iexact=filters["artist"])
        if "genre" in filters:
            queryset = queryset.filter(
                genre_index__normalized_name=filters["genre"].strip().casefold()
            )
        if "bpm_min" in filters:
            queryset = queryset.filter(features__tempo__gte=filters["bpm_min"])
        if "bpm_max" in filters:
            queryset = queryset.filter(features__tempo__lte=filters["bpm_max"])
        return queryset.order_by("id")

    @extend_schema(
        parameters=TRACK_PARAMETERS,
        responses={
            200: TrackSummarySerializer(many=True),
            400: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class TrackDetailView(generics.RetrieveAPIView):
    queryset = Track.objects.select_related("features").filter(
        features__isnull=False
    )
    serializer_class = TrackDetailSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "track_reads"

    @extend_schema(
        responses={
            200: TrackDetailSerializer,
            404: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
        }
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RecommendationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "recommendations"

    @extend_schema(
        request=RecommendationRequestSerializer,
        responses={
            200: RecommendationResponseSerializer,
            400: ApiErrorResponseSerializer,
            413: ApiErrorResponseSerializer,
            422: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
        },
    )
    def post(self, request):
        serializer = RecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = RecommendationService().recommend(serializer.validated_data)
        except RecommendationServiceError as error:
            return Response({"error": error.as_dict()}, status=error.status_code)
        return Response(RecommendationResponseSerializer(result).data)


class SuggestionCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "suggestions"

    @extend_schema(
        request=SuggestionCreateSerializer,
        responses={
            202: SuggestionResponseSerializer,
            400: ApiErrorResponseSerializer,
            413: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
        },
    )
    def post(self, request):
        serializer = SuggestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = TrackSuggestion.objects.create(**serializer.validated_data)
        return Response(
            SuggestionResponseSerializer(suggestion).data,
            status=status.HTTP_202_ACCEPTED,
        )


class StaffCatalogueView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "staff"

    @extend_schema(
        responses={
            200: StaffCatalogueResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
            503: ApiErrorResponseSerializer,
        }
    )
    def get(self, request):
        state = CatalogueState.objects.filter(pk=1).first()
        if state is None:
            raise CatalogueUnavailable()
        track_count = Track.objects.count()
        feature_count = TrackFeatures.objects.count()
        source_versions = list(
            Track.objects.order_by().values_list("data_source", flat=True).distinct()
        )
        result = {
            "version": state.version,
            "catalogue_sha256": state.catalogue_sha256,
            "record_count": state.record_count,
            "imported_at": state.imported_at,
            "track_count": track_count,
            "feature_count": feature_count,
            "genre_entry_count": TrackGenre.objects.count(),
            "state_consistent": (
                track_count == feature_count == state.record_count
                and source_versions == [state.version]
            ),
        }
        return Response(StaffCatalogueResponseSerializer(result).data)


class StaffSuggestionListView(generics.ListAPIView):
    queryset = TrackSuggestion.objects.order_by("-submitted_at", "-id")
    serializer_class = StaffSuggestionSerializer
    pagination_class = TrackPagination
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "staff"

    def get_queryset(self):
        queryset = super().get_queryset()
        requested_status = self.request.query_params.get("status")
        if requested_status is not None:
            if requested_status not in TrackSuggestion.Status.values:
                raise ValidationError({"status": "Invalid suggestion status."})
            queryset = queryset.filter(status=requested_status)
        return queryset

    @extend_schema(
        parameters=[OpenApiParameter("status", str)],
        responses={
            200: StaffSuggestionSerializer(many=True),
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class StaffSuggestionReviewView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "staff"

    @extend_schema(
        request=SuggestionReviewSerializer,
        responses={
            200: StaffSuggestionSerializer,
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
            429: ApiErrorResponseSerializer,
        },
    )
    def patch(self, request, pk):
        serializer = SuggestionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = get_object_or_404(TrackSuggestion, pk=pk)
        suggestion.status = serializer.validated_data["decision"]
        suggestion.reviewed_at = timezone.now()
        suggestion.save(update_fields=("status", "reviewed_at"))
        return Response(StaffSuggestionSerializer(suggestion).data)

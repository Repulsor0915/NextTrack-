from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView,
)

from . import views

app_name = "recommendations"

urlpatterns = [
    path("catalogue/", views.CatalogueView.as_view(), name="catalogue"),
    path("tracks/", views.TrackListView.as_view(), name="tracks"),
    path("tracks/<str:pk>/", views.TrackDetailView.as_view(), name="track-detail"),
    path(
        "recommendations/",
        views.RecommendationView.as_view(),
        name="recommendations",
    ),
    path(
        "track-suggestions/",
        views.SuggestionCreateView.as_view(),
        name="track-suggestions",
    ),
    path(
        "staff/catalogue/",
        views.StaffCatalogueView.as_view(),
        name="staff-catalogue",
    ),
    path(
        "staff/track-suggestions/",
        views.StaffSuggestionListView.as_view(),
        name="staff-track-suggestions",
    ),
    path(
        "staff/track-suggestions/<int:pk>/",
        views.StaffSuggestionReviewView.as_view(),
        name="staff-track-suggestion-detail",
    ),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/swagger/",
        SpectacularSwaggerView.as_view(url_name="recommendations:schema"),
        name="swagger",
    ),
    path(
        "docs/redoc/",
        SpectacularRedocView.as_view(url_name="recommendations:schema"),
        name="redoc",
    ),
]

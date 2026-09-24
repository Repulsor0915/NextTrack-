"""Service-level errors raised by the recommendation workflow."""


class RecommendationServiceError(Exception):
    code = "RECOMMENDATION_ERROR"
    status_code = 400

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def as_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class UnknownTrackIdsError(RecommendationServiceError):
    code = "UNKNOWN_TRACK_ID"


class NoCandidatesError(RecommendationServiceError):
    code = "NO_CANDIDATES"
    status_code = 422


class UnsupportedAlgorithmError(RecommendationServiceError):
    code = "UNSUPPORTED_ALGORITHM"


class MissingTrackFeaturesError(RecommendationServiceError):
    code = "MISSING_TRACK_FEATURES"
    status_code = 422

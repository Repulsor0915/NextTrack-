from rest_framework.response import Response
from rest_framework.views import APIView


class RecommendationView(APIView):
    def post(self, request):
        return Response(
            {
                "message": "NextTrack recommendation endpoint",
                "received_data": request.data,
            }
        )

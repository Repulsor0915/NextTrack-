from rest_framework.permissions import BasePermission


class IsSuperuser(BasePermission):
    """Limit the live API documentation to a logged-in superuser."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)

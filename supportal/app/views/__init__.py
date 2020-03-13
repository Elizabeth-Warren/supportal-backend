from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .email_views import UnsubscribeView
from .invite_views import InviteViewSet
from .person_views import PersonViewSet
from .user_views import FullUserViewSet, MeView
from .vol_prospect_views import (
    VolProspectAssignmentViewSet,
    VolProspectContactEventViewSet,
)


@api_view()
@permission_classes([permissions.AllowAny])
def index(request):
    """Unauthenticated health check endpoint"""
    return Response({"message": "Hello, from EW!"})

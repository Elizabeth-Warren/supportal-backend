from django.utils import timezone
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from supportal.app.models import User


class UnsubscribeView(GenericAPIView):
    """ Allow a user to unsubscribe from
    emails from supportal. Only requires
    an email to look up the user and
    unsubscribe"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        email = request.data["email"]
        try:
            user = User.objects.get_user_by_email(email=email)
        except User.DoesNotExist:
            return Response(
                {"message": "No User with that email"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.unsubscribed_at = timezone.now()
        user.save()
        return Response(None, status=status.HTTP_200_OK)

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# from ew_common.telemetry import Metric, telemetry
from supportal.app.models import EmailSend, User, VolProspectAssignment
from supportal.app.permissions import HasInvite, IsSupportalAdminUser
from supportal.services.email_service import get_email_service


class VerifyView(GenericAPIView):
    """ APIView for a verifying a user """

    permission_classes = [IsSupportalAdminUser]

    def _email_verified_user(self, email):
        payload = {"email": email, "transactional": True}
        get_email_service().send_email(
            template_name=EmailSend.VERIFIED_EMAIL,
            from_email=settings.FROM_EMAIL,
            recipient=email,
            reply_to_email=settings.REPLY_TO_EMAIL,
            configuration_set_name=settings.CONFIGURATION_SET_NAME,
            payload=payload,
            application_name="supportal",
        )

    def _verify_single_user(self, email):
        try:
            user = User.objects.get_user_by_email(email=email)
            VolProspectAssignment.objects.delete_demo_assignments(user)
        except User.DoesNotExist:
            user = User.objects.create_user(None, email)
            # telemetry.metric(Metric("UsersCreatedViaVerify", 1, unit="Count"))
        if user.verified_at is None:
            user.verified_at = timezone.now()
            user.save()
            self._email_verified_user(email)

    def _verify_users(self, email_list):
        for email in email_list:
            self._verify_single_user(email)

    def post(self, request, *args, **kwargs):
        emails = request.data.get("emails", [])
        email = request.data.get("email")
        if email:
            emails.append(email)
        self._verify_users(emails)
        return Response(None, status=status.HTTP_200_OK)


class InviteViewSet(viewsets.ViewSet):
    """
    Invite a user via email. Each User gets an invite after they
    have talked to 10 contacts. The person they invite must talk
    to 10 perspective users before the invite-r gets an invite
    """

    permission_classes = [IsSupportalAdminUser | HasInvite]

    def _create_user_from_email(self, email, request_user):
        """
        Create the user from an email. First try looking up
        the user, if that user exists already or for some
        reason we have multiple added users just return None.
        """
        try:
            User.objects.get_user_by_email(email=email)
        except User.DoesNotExist:
            return User.objects.create_user(
                email,
                email,
                should_send_invite_email=True,
                added_by=request_user,
                verified_at=timezone.now(),
            )
        except User.MultipleObjectsReturned:
            pass
        return None

    @action(detail=False, permission_classes=[IsAuthenticated])
    def available(self, request, *args, **kwargs):
        # user has the ability to send an invite
        user = request.user
        has_invite = user.has_invite
        latest_invite = user.latest_invite
        latest_invite_object = {}

        if latest_invite:
            latest_invite_object = {
                "email": latest_invite.email,
                "remaining_contacts_count": latest_invite.remaining_contacts_count,
            }
        response_data = {
            "has_invite": has_invite,
            "remaining_contacts_count": user.remaining_contacts_count,
            "latest_invite": latest_invite_object,
        }

        return Response(response_data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        email = request.data.get("email", "").strip()
        if not email:
            return Response(
                {"message": "Must include an email address"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validator = EmailValidator()
            validator(email)
        except ValidationError:
            return Response(
                {"message": "Invalid email address given"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_user = self._create_user_from_email(email, request.user)

        if created_user:
            return Response(status=status.HTTP_201_CREATED)

        # If the user tried to send an invite to a user who
        # already existed no-op
        return Response(status=status.HTTP_204_NO_CONTENT)

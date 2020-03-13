import datetime
import logging

import boto3
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models as gis_models
from django.core.exceptions import FieldError
from django.db import IntegrityError, models
from django.utils import timezone
from localflavor.us.models import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES
from phonenumber_field.modelfields import PhoneNumberField

from supportal.app.models import EmailSend, Person
from supportal.app.models.base_model_mixin import BaseModelMixin
from supportal.services.email_service import get_email_service

_cognito_client = None

ASSIGNMENT_COUNT_TO_INVITE = 10
DAILY_INVITES = 3


def _get_cognito_client():
    global _cognito_client
    if _cognito_client is None:
        _cognito_client = boto3.client("cognito-idp")
    return _cognito_client


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """Lower case email addresses, overrides BaseUserManager#normalize_email.

        We do this to make email log-in case insensitive.
        This is technically not RFC compliant and could create problems for users
        with case-sensitive email servers. We aren't likely to be affected by this but,
        if we are, normalization can be bypassed by calling User.change_email on an
        existing user.
        """
        return email.strip().lower()

    def create_cognito_user(self, email):
        if not email:
            raise FieldError("email field is required")
        response = _get_cognito_client().admin_create_user(
            UserPoolId=settings.COGNITO_USER_POOL,
            # Cognito quirk: when the pool is set to use email as username, Cognito
            # *does not* use the email as the username... it generates a uuid.
            # We need to read the "real" Cognito username, which we use
            # to associate id tokens to our users in the authentication backend,
            # from the response.
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                # No need to verify email as it is is effectively verified by
                # our custom auth flow.
                {"Name": "email_verified", "Value": "True"},
            ],
            MessageAction="SUPPRESS",
            # Even though we don't use it, set email as the desired delivery medium
            # in case we want to use it in the future.
            DesiredDeliveryMediums=["EMAIL"],
            # Fail if email already exists
            ForceAliasCreation=False,
        )
        return response

    def _email_new_user(self, email):
        payload = {
            "email": email,
            "switchboard_signup_url": settings.SUPPORTAL_BASE_URL,
            "transactional": True,
        }
        email_service = get_email_service()
        email_service.send_email(
            template_name=EmailSend.INVITE_EMAIL,
            from_email=settings.FROM_EMAIL,
            recipient=email,
            reply_to_email=settings.REPLY_TO_EMAIL,
            configuration_set_name=settings.CONFIGURATION_SET_NAME,
            payload=payload,
            application_name="supportal",
        )

    def _create_user(
        self,
        username,
        email,
        password,
        skip_cognito,
        should_send_invite_email,
        **extra_fields,
    ):
        """
        Create and save a user with the given username, email, and password.

        This sets up the user in Congito unless skip_cognito=True is passed.
        This option is intended for testing or to add users that have already been
        created in Cognito.
        """
        email = self.normalize_email(email)
        if not skip_cognito:
            cognito_response = self.create_cognito_user(email)
            logging.info(f"Create user response from Cognito {cognito_response}")
            username = cognito_response["User"]["Username"]
            logging.info(f"Created Cognito user {username} for email {email}")
        if not username:
            raise ValueError("The given username must be set")
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        if should_send_invite_email:
            self._email_new_user(email)
        return user

    def create_user(
        self,
        username,
        email,
        should_send_invite_email=False,
        skip_cognito=False,
        **extra_fields,
    ):
        """Create and save a regular User (password not allowed)."""
        is_staff = email.endswith(
            "@elizabethwarren.com"
        )  # staff get added as admins and staff
        extra_fields.setdefault("is_staff", is_staff)
        extra_fields.setdefault("is_admin", is_staff)

        extra_fields.setdefault("is_superuser", False)
        return self._create_user(
            username,
            email,
            None,
            skip_cognito,
            should_send_invite_email,
            **extra_fields,
        )

    def create_superuser(
        self, username, email, password, skip_cognito=False, **extra_fields
    ):
        """Create and save a super User (password required).

        We keep the "username" param for compatibility with the createsuperuser
        manage command, but it is never used.
        TODO: update createsuperuser command
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_superuser", True)
        if password is None:
            raise ValueError("Superuser must have a usable password.")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(
            username,
            email,
            password,
            should_send_invite_email=False,
            skip_cognito=skip_cognito,
            **extra_fields,
        )

    def get_user_by_email(self, email):
        """Get a user by email

        :raises User.DoesNotExist
        :raises User.MultipleObjectsReturned if email matches more than one User,
            which should be impossible.
        """
        return self.get(email=self.normalize_email(email))


class User(AbstractUser, BaseModelMixin):
    """
    Custom User class for the Supportal

    We inherit 'password' from AbstractUser in order to use the admin interface.
    It's not actually necessary when using Cognito, so the user manager sets
    unusable passwords for all non-admin users. In the future, we may want to
    integrate Cognito auth with the admin interface, but it's not trivial.
    """

    objects = UserManager()

    person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True)
    added_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, blank=True, null=True, related_name="invites"
    )

    is_admin = models.BooleanField(default=False)
    email = models.EmailField(blank=False, unique=True, db_index=True)
    phone = PhoneNumberField(blank=True)

    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    state = USStateField(choices=STATE_CHOICES, blank=True)
    zip5 = USZipCodeField(blank=True)
    coordinates = gis_models.PointField(
        geography=True, srid=4326, null=True, blank=True
    )
    unsubscribed_at = models.DateTimeField(null=True, db_index=True)
    self_reported_team_name = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(null=True)
    impersonated_user = models.ForeignKey(
        "self", on_delete=models.DO_NOTHING, null=True, blank=True, default=None
    )

    @property
    def latest_invite(self):
        try:
            return self.invites.latest(field_name="created_at")
        except User.DoesNotExist:
            return None

    @property
    def has_invite(self):
        latest_invite = self.latest_invite
        has_reached_contact_count = (
            self.assignment_contacts_count >= ASSIGNMENT_COUNT_TO_INVITE
        )
        if latest_invite:
            invite_has_reached_contact_count = (
                latest_invite.assignment_contacts_count >= ASSIGNMENT_COUNT_TO_INVITE
            )
            has_not_maxed_daily_invites = (
                self.invites.filter(
                    created_at__gte=timezone.now() - datetime.timedelta(days=1)
                ).count()
                < DAILY_INVITES
            )
            return (
                invite_has_reached_contact_count
                and has_not_maxed_daily_invites
                and has_reached_contact_count
            )
        return has_reached_contact_count

    @property
    def assignment_contacts_count(self):
        return (
            self.vol_prospect_assignments.filter(
                vol_prospect_contact_events__isnull=False
            )
            .distinct("person")
            .count()
        )

    @property
    def remaining_contacts_count(self):
        remaining = ASSIGNMENT_COUNT_TO_INVITE - self.assignment_contacts_count
        return remaining if remaining > 0 else 0

    def change_email(self, new_email):
        logging.info(
            f"Changing {self.username}'s email from {self.email} to {new_email}"
        )
        self.email = new_email
        self.save()
        _get_cognito_client().admin_update_user_attributes(
            UserPoolId=settings.COGNITO_USER_POOL,
            Username=self.username,
            UserAttributes=[
                {"Name": "email", "Value": new_email},
                # If not set to true, this would trigger Cognito's internal
                # email verification flow, which we don't support.
                {"Name": "email_verified", "Value": "True"},
            ],
        )

    def normalize_email(self):
        normalized = UserManager.normalize_email(self.email)
        if self.email != normalized:
            try:
                self.change_email(normalized)
            except IntegrityError as e:
                # Skip users that have already worked around case-sensitivity by creating
                # a second user with a lower-case email.
                # TODO: we may want to delete these Users at some point since it is
                #  no longer possible for them to log in.
                logging.warning(f"Skipping user {self.id}. IntegrityError: {e}")

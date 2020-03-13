import datetime

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import CharField

# from ew_common.geocode import geocode
# from ew_common.input_validation import extract_phone_number_e164
from supportal.app.common.enums import ActivityStatus
from supportal.app.models import User, VolProspectAssignment
from supportal.app.serializers import FullPersonSerializer


class LimitedUserSerializer(serializers.ModelSerializer):
    """ A limited User Serializer """

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name"]
        read_only_fields = fields


class FullUserSerializer(serializers.ModelSerializer):
    """Full read-write User serializer for superuser access"""

    ngp_id = CharField(source="person.ngp_id", required=False)
    activity_status = serializers.SerializerMethodField()
    added_by = LimitedUserSerializer(required=False, read_only=True)
    is_mobilize_america_signup = serializers.BooleanField(required=False)
    should_send_invite_email = serializers.BooleanField(required=False)

    def get_activity_status(self, obj):
        """Currently activity status follows rules below:
        ACTIVE: last_login within in in past week
        INACTIVE: last_login > two weeks
        CHURNING: last_login > one week and <two weeks
        NEW: no last_login
        """

        now = timezone.now()
        last_week = now - datetime.timedelta(days=7)
        two_weeks_ago = now - datetime.timedelta(days=14)

        if obj.last_login:
            if obj.last_login < two_weeks_ago:
                return ActivityStatus.INACTIVE
            elif obj.last_login > last_week:
                return ActivityStatus.ACTIVE
            else:
                return ActivityStatus.CHURNING
        else:
            return ActivityStatus.NEW

    class Meta:
        model = User
        fields = [
            "id",
            "is_admin",
            "created_at",
            "updated_at",
            "person",
            "first_name",
            "last_name",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "zip5",
            "coordinates",
            "ngp_id",
            "last_login",
            "activity_status",
            "added_by",
            "self_reported_team_name",
            "is_mobilize_america_signup",
            "should_send_invite_email",
        ]
        # would want to update ngp_id on the person and not here
        read_only_fields = ["id", "created_at", "updated_at", "ngp_id", "is_admin"]
        # By default, email will have a uniqueness validator; we don't want to
        # validate uniqueness on email, because we allow upsert.
        extra_kwargs = {"email": {"validators": []}}

    def update(self, instance, validated_data):
        if "email" in validated_data:
            raise ValidationError("Changing email is not allowed through this endpoint")
        return super().update(instance, validated_data)

    def create(self, validated_data):
        """Create or update based on email.

        This results in POST behaving as an upsert based on email.
        """
        email = validated_data.pop("email")
        is_mobilize_america_signup = validated_data.pop(
            "is_mobilize_america_signup", None
        )
        should_send_invite_email = validated_data.pop("should_send_invite_email", False)
        request = self.context.get("request")
        if not request or not request.user:
            raise ValidationError("Cannot create outside of a request context")

        validated_data.update(added_by=request.user)
        user = None
        try:
            existing_user = User.objects.get_user_by_email(email)
            for k, v in validated_data.items():
                setattr(existing_user, k, v)
            existing_user.save()
            user = existing_user
        except User.DoesNotExist:
            user = User.objects.create_user(
                None, email, should_send_invite_email, **validated_data
            )
        if not is_mobilize_america_signup and user.verified_at is None:
            # we pass in is_demo for the mobilize america sync only
            VolProspectAssignment.objects.delete_demo_assignments(user)
            user.verified_at = timezone.now()
            user.save()
        return user


class MeSerializer(serializers.ModelSerializer):
    """Limited read-write User serializer for users to access their own data"""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "address",
            "city",
            "state",
            "zip5",
            "coordinates",
            "self_reported_team_name",
            "is_admin",
            "created_at",
            "updated_at",
        ]
        # Note: Users must not be allowed to change their email address
        read_only_fields = ["id", "email", "created_at", "updated_at", "is_admin"]

        # We do our own phone validation.
        extra_kwargs = {"phone": {"validators": []}}

    def validate_phone(self, value):
        # TODO: format number here 
        # canonical_phone = extract_phone_number_e164(value)
        canonical_phone= value
        if not canonical_phone:
            raise serializers.ValidationError("Phone number invalid format: {value}")
        return canonical_phone

    def validate(self, data):
        zip5 = data.get("zip5")
        if zip5:
            pieces = [data.get("address"), data.get("city"), data.get("state"), zip5]
            full_address = ", ".join((filter(None, pieces)))
            location = full_address
            # note will need to geocode aka get lat/long from address
            # location = geocode(full_address, settings.GOOGLE_MAPS_API_KEY)
            if location:
                data["coordinates"] = Point(location["lng"], location["lat"], srid=4326)
            else:
                raise serializers.ValidationError(
                    "No location from address geocode: {data}"
                )

        return super().validate(data)

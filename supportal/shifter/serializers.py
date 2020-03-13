import logging

from django.conf import settings
from localflavor.us.models import USZipCodeField
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.serializers import ModelSerializer

from supportal.services.mobilize_america import PUBLIC_VISIBILITY, get_global_client
from supportal.shifter.event_recommendation_strategies import (
    DBRecommendationStrategy,
    MobilizeAmericaAPIRecommendationStrategy,
)
from supportal.shifter.mobilize_america_helpers import (
    add_extras_for_mdata,
    filter_timeslots_for_time,
    remove_full_timeslots,
    sanitize_event_payload,
)
from supportal.shifter.models import (
    EventSignup,
    MobilizeAmericaEvent,
    MobilizeAmericaTimeslot,
    RecommendedEventRequestLog,
    USZip5,
)


class EventSignupSerializer(ModelSerializer):
    class Meta:
        model = EventSignup
        fields = [
            "session_id",
            "email",
            "phone",
            "given_name",
            "family_name",
            "heap_id",
            "sms_opt_in",
            "zip5",
            "metadata",
            "source",
            "ma_event_id",
            "ma_timeslot_ids",
            "ma_response",
            "ma_creation_successful",
            "created_at",
            "updated_at",
            "signed_up_via_shifter",
            "honor_ma_attendance",
        ]

        read_only_fields = [
            "ma_response",
            "ma_creation_successful",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        if (
            not validated_data.get("email")
            and not validated_data.get("phone")
            and not (validated_data.get("zip5"))
        ):
            raise ValidationError(
                {"detail": "Must include either phone or email or zip5"},
                code="required_field",
            )
        obj = super().create(validated_data)
        if not validated_data.get("email") or not validated_data.get("zip5"):
            return obj
        # MA doesn't provide a way to limit event attendance creation to public events
        # so we have to check permissions ourselves before syncing.
        # Note: we perform the check here rather than in sync_to_mobilize_america() since
        # there could be legitimate reasons for us to sign people up to private events,
        # we just don't want them to be able to do it themselves through a public API.
        if settings.MOBILIZE_AMERICA_DEFAULT_VISIBILITY == PUBLIC_VISIBILITY:
            event = MobilizeAmericaEvent.objects.filter(
                id=obj.ma_event_id, is_active=True
            )
            if not event.exists() or event.first().visibility != PUBLIC_VISIBILITY:
                raise NotFound()
        obj.sync_to_mobilize_america()
        return obj


class USZip5Serializer(ModelSerializer):
    class Meta:
        model = USZip5
        fields = ["zip5", "city", "state", "latitude", "longitude"]


class RecommendedEventRequestSerializer(serializers.Serializer):
    """Serializer responsible for serving event recommendations

    This is a kind of hacky way of using a Serializer, but it's the best way to
    get good endpoint validation in DRF :/
    """

    email = serializers.EmailField(required=False)
    event_types = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )
    is_virtual = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(max_value=20, default=3, required=False)
    max_dist = serializers.IntegerField(required=False)
    session_id = serializers.CharField(required=False)
    strategy = serializers.CharField(max_length=20, required=False)
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True, required=False
    )
    timeslot_start = serializers.DateTimeField(required=False)
    timeslot_end = serializers.DateTimeField(required=False)
    utm_source = serializers.CharField(required=False)
    zip5 = serializers.ModelField(USZipCodeField(), required=False)
    states = serializers.ListField(
        child=serializers.CharField(max_length=2), allow_empty=True, required=False
    )

    __rec_kwargs = {
        "zip5",
        "event_types",
        "max_dist",
        "tag_ids",
        "timeslot_start",
        "timeslot_end",
        "is_virtual",
        "states",
    }

    def validate(self, attrs):
        if not attrs.get("is_virtual") and not attrs.get("zip5"):
            raise ValidationError("Field 'zip5' is required for non-virtual events")
        return attrs

    def create(self, validated_data):
        log = RecommendedEventRequestLog()
        # Log the raw request, not the converted/validated data
        log.request_params = self.initial_data

        strategy = self.__get_recommendation_strategy(validated_data)
        rbkwargs = {k: v for k, v in validated_data.items() if k in self.__rec_kwargs}
        events = strategy.find_events(validated_data["limit"], **rbkwargs)
        log.recommended_ma_event_ids = [e["id"] for e in events]
        try:
            log.save()
        except Exception as e:
            logging.exception("Failed to save RecommendedEventRequestLog", e)
        finally:
            return self.__prepare_events(
                events,
                validated_data.get("utm_source"),
                validated_data.get("timeslot_start"),
                validated_data.get("timeslot_end"),
            )

    def __get_recommendation_strategy(self, data):
        if data.get("strategy") == "mobilize_america":
            return MobilizeAmericaAPIRecommendationStrategy
        elif data.get("strategy") == "shifter_engine":
            return DBRecommendationStrategy
        else:
            return MobilizeAmericaAPIRecommendationStrategy

    def __prepare_events(
        self, events, utm_source, timeslot_start=None, timeslot_end=None
    ):
        events_with_open_timeslots = [remove_full_timeslots(e) for e in events]
        events_with_extra_m_data = [
            add_extras_for_mdata(e, utm_source) for e in events_with_open_timeslots
        ]
        events_with_filtered_timeslots = [
            filter_timeslots_for_time(e, timeslot_start, timeslot_end)
            for e in events_with_extra_m_data
        ]
        # Don't recommend events without timeslots for users to signup with
        return [
            sanitize_event_payload(e)
            for e in events_with_filtered_timeslots
            if len(e["timeslots"])
        ]

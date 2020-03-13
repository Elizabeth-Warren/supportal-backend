from datetime import datetime, timezone

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import ArrayField, JSONField
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from enumfields import EnumIntegerField
from localflavor.us.models import USStateField, USZipCodeField
from phonenumber_field.modelfields import PhoneNumberField

from supportal.app.models.base_model_mixin import BaseModelMixin
from supportal.services.mobilize_america import (
    AttendanceRequestPerson,
    MobilizeAmericaAPIException,
    Referrer,
    get_global_client,
)
from supportal.shifter.common.error_codes import ErrorCodes

MAX_INTEGER_SIZE = 2147483647


class EventSignup(BaseModelMixin):
    email = models.EmailField(blank=True)
    family_name = models.CharField(blank=False, max_length=255)
    given_name = models.CharField(blank=False, max_length=255)
    ma_creation_successful = models.BooleanField(default=False)
    ma_event_id = models.IntegerField(null=False)
    ma_response = JSONField(null=True)
    ma_timeslot_ids = ArrayField(models.IntegerField(null=False), null=False)
    metadata = JSONField(null=True)
    phone = PhoneNumberField(blank=True)
    session_id = models.CharField(blank=True, max_length=255)
    # CAUTION: we are not allowed to collect opt-ins on Mobilize America's
    # behalf, so this field can only be used to opt people in to messaging
    # from our campaign.
    signed_up_via_shifter = ArrayField(models.IntegerField(null=False), null=True)
    honor_ma_attendance = models.BooleanField(default=True)
    sms_opt_in = models.BooleanField(default=False)
    source = models.CharField(blank=True, max_length=255)
    zip5 = USZipCodeField(blank=True)
    retried_at = models.DateTimeField(null=True)
    heap_id = models.CharField(max_length=1024, null=True)

    def sync_to_mobilize_america(self):
        if not self.ma_creation_successful and (self.email and self.zip5):
            try:
                referrer = Referrer(utm_source=self.source) if self.source else None
                self.ma_response, timeslots_signed_up = get_global_client().create_event_attendance(
                    self.ma_event_id,
                    list(self.ma_timeslot_ids),
                    person=AttendanceRequestPerson(
                        given_name=self.given_name,
                        family_name=self.family_name,
                        email_address=self.email,
                        postal_code=self.zip5,
                        phone_number=str(self.phone),
                    ),
                    referrer=referrer,
                    honor_ma_attendance=self.honor_ma_attendance,
                )
                self.ma_creation_successful = True
                self.signed_up_via_shifter = timeslots_signed_up
            except MobilizeAmericaAPIException as e:
                self.ma_response = e.response
                self.ma_creation_successful = False
            self.save()
        return self.ma_creation_successful, self.ma_response


class RecommendedEventRequestLog(BaseModelMixin):
    email = models.EmailField(blank=False, db_index=True)
    recommended_ma_event_ids = ArrayField(models.IntegerField(null=False), null=False)
    request_params = JSONField(null=False)
    session_id = models.CharField(blank=True, max_length=255)


class State(BaseModelMixin):
    state_code = USStateField()
    is_caucus = models.BooleanField(default=False)
    prioritization_doc = models.CharField(blank=True, max_length=1000)
    use_prioritization_doc = models.BooleanField(default=False)
    neighbor_states = models.ManyToManyField("self", symmetrical=False)


class MobilizeAmericaEventManager(models.Manager):
    @staticmethod
    def _timeslot_from_json(event_id, j):
        ts = MobilizeAmericaTimeslot()
        ts.event_id = event_id
        ts.end_date = _convert_ma_timestamp(j["end_date"])
        ts.start_date = _convert_ma_timestamp(j["start_date"])
        ts.id = j["id"]
        ts.is_full = j["is_full"]
        ts.raw = j
        return ts

    @transaction.atomic
    def update_or_create_from_json(self, payload):
        loc = payload.get("location")
        coordinates = None
        if loc is not None and "location" in loc:
            lat = loc["location"].get("latitude")
            lng = loc["location"].get("longitude")
            coordinates = Point(lng, lat, srid=4326)
        state = None
        if loc is not None and "region" in loc:
            state_code = loc["region"]
            state, _ = State.objects.get_or_create(state_code=state_code)
        event, created = self.update_or_create(
            id=payload["id"],
            defaults={
                "title": payload.get("title"),
                "event_type": payload.get("event_type"),
                "visibility": payload.get("visibility"),
                "high_priority": payload.get("high_priority"),
                "is_virtual": loc is None,
                "coordinates": coordinates,
                "tag_ids": [t["id"] for t in payload.get("tags", [])],
                "modified_date": _convert_ma_timestamp(payload.get("modified_date")),
                "raw": payload,
                "state": state,
                "is_active": True,
            },
        )
        if not created:
            # the update_or_create might do this automatically, but it was hard
            # to tell so I added it in
            event.updated_at = timezone.now()
            event.save()
            event.timeslots.all().delete()
        timeslots = [
            self._timeslot_from_json(event.id, j) for j in payload.get("timeslots", [])
        ]
        MobilizeAmericaTimeslot.objects.bulk_create(timeslots)
        return event, created


class MobilizeAmericaEvent(BaseModelMixin):
    objects = MobilizeAmericaEventManager()

    coordinates = gis_models.PointField(
        "coordinates", geography=True, srid=4326, null=True
    )
    event_type = models.CharField(null=True, max_length=30, db_index=True)
    # Note: we use the MA id as the primary key so we override Django's
    # auto-increment `id` field
    id = models.IntegerField(primary_key=True)
    is_virtual = models.BooleanField(default=False, db_index=True)
    high_priority = models.BooleanField(default=False, db_index=True)
    modified_date = models.DateTimeField(null=True, db_index=True)
    state = models.ForeignKey(State, null=True, on_delete=models.DO_NOTHING)
    raw = JSONField(null=False)
    tag_ids = ArrayField(models.IntegerField(), default=list)
    title = models.CharField(max_length=1024)
    visibility = models.CharField(null=True, max_length=30, db_index=True)
    state_prioritization = models.IntegerField(default=MAX_INTEGER_SIZE)
    is_active = models.BooleanField(default=True)


class MobilizeAmericaTimeslot(BaseModelMixin):
    end_date = models.DateTimeField(null=True)
    event = models.ForeignKey(
        MobilizeAmericaEvent,
        on_delete=models.DO_NOTHING,
        null=False,
        related_name="timeslots",
    )
    id = models.IntegerField(primary_key=True)
    is_full = models.BooleanField(default=False)
    raw = JSONField(null=False)
    start_date = models.DateTimeField(null=True)


class USZip5(models.Model):
    accuracy = models.IntegerField(null=True)
    city = models.CharField(max_length=1024, blank=True)
    coordinates = gis_models.PointField(
        "coordinates", geography=True, srid=4326, null=True
    )
    county = models.CharField(max_length=1024, blank=True)
    county_fips = models.IntegerField(null=True)
    state = USStateField(blank=True)
    zip5 = USZipCodeField(blank=False, primary_key=True)

    @property
    def longitude(self):
        return self.coordinates.x

    @property
    def latitude(self):
        return self.coordinates.y


def _convert_ma_timestamp(unix_time):
    return datetime.fromtimestamp(unix_time, timezone.utc)

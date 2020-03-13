from django.core.serializers import serialize
from rest_framework import serializers

from supportal.app.common.enums import VolProspectAssignmentStatus
from supportal.app.models import VolProspectAssignment
from supportal.app.serializers import LimitedPersonSerializer
from supportal.app.serializers.vol_prospect_contact_event_serializer import (
    VolProspectContactEventSerializer,
)


class LatLang(serializers.Serializer):
    latitude = serializers.IntegerField()
    longitude = serializers.IntegerField()


class VolProspectAssignmentSerializer(serializers.ModelSerializer):
    person = LimitedPersonSerializer(read_only=True)
    location = LatLang(required=False, write_only=True)
    vol_prospect_contact_events = VolProspectContactEventSerializer(many=True)

    class Meta:
        model = VolProspectAssignment
        fields = [
            "id",
            "user",
            "person",
            "suppressed_at",
            "expired_at",
            "status",
            "vol_prospect_contact_events",
            "created_at",
            "updated_at",
            "note",
            "location",
        ]
        read_only_fields = [
            "id",
            "user",
            "person",
            "status",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        data["status"] = VolProspectAssignmentStatus.from_name(data["status"])
        return super().to_internal_value(data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["status"] = instance.status.name
        return ret

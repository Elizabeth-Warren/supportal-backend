from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError

from supportal.app.common.enums import CanvassResult, CanvassResultCategory
from supportal.app.models import VolProspectAssignment, VolProspectContactEvent


class VolProspectContactEventSerializer(serializers.ModelSerializer):
    # TODO: drf-yasg doesn't understand our Enum -> String conversion without a little help
    # Do something like this to get strings rather than numbers in the docs:
    # https://github.com/axnsan12/drf-yasg/issues/478

    class Meta:
        model = VolProspectContactEvent
        fields = [
            "id",
            "vol_prospect_assignment",
            "ma_event_id",
            "ma_timeslot_ids",
            "result_category",
            "result",
            "metadata",
            "created_at",
            "updated_at",
            "note",
        ]
        read_only_fields = [
            "id",
            "user",
            "result_category",  # gets set automatically from result
            "created_at",
            "updated_at",
        ]
        required_fields = ["vol_prospect_assignment", "result"]

    def to_internal_value(self, data):
        data["result"] = CanvassResult.from_name(data["result"])
        result_cat = data.get("result_category")
        if result_cat:
            data["result_category"] = CanvassResultCategory.from_name(result_cat)
        return super().to_internal_value(data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["result"] = instance.result.name
        ret["result_category"] = instance.result_category.name
        return ret

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not request.user:
            raise ValidationError("Cannot create outside of a request context")
        assignment = validated_data["vol_prospect_assignment"]
        if assignment.user != request.user:
            raise NotFound()
        return assignment.create_contact_event(**validated_data)

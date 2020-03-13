from rest_framework import serializers

from supportal.app.models import Person


class FullPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = [
            "id",
            "created_at",
            "updated_at",
            "myc_state_and_id",
            "ngp_id",
            "first_name",
            "middle_name",
            "last_name",
            "suffix",
            "email",
            "phone",
            "address",
            "city",
            "state",
            "zip5",
            "coordinates",
            "is_vol_prospect",
            "vol_yes_at",
            "is_vol_leader",
        ]

        # By default, ngp_id will have a uniqueness validator; we don't want to
        # validate uniqueness on ngp_id, because we allow upsert.
        extra_kwargs = {"ngp_id": {"validators": []}, "address": {"write_only": True}}

    def create(self, validated_data):
        """Create or update based on ngp_id.

        This results in POST behaving as an upsert based on ngp_id.
        """
        ngp_id = validated_data.get("ngp_id", None)
        if ngp_id:
            person, created = Person.objects.update_or_create(
                ngp_id=ngp_id, defaults=validated_data
            )
            return person
        return super().create(validated_data)


class LimitedPersonSerializer(serializers.ModelSerializer):

    last_name = serializers.CharField(
        max_length=2, allow_blank=True, source="trimmed_last_name"
    )
    has_email = serializers.BooleanField(default=True, source="get_has_email")

    class Meta:
        model = Person
        fields = [
            "id",
            "created_at",
            "updated_at",
            "first_name",
            "last_name",
            "suffix",
            "phone",
            "city",
            "state",
            "is_demo",
            "has_email",
        ]
        read_only_fields = fields

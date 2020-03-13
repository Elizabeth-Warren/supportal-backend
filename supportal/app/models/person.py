from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db import models
from django.utils import timezone
from localflavor.us.models import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES
from phonenumber_field.modelfields import PhoneNumberField

from supportal.app.models.base_model_mixin import BaseModelMixin


class PersonQuerySet(models.QuerySet):
    def from_reference(self, coordinates, radius_mi):
        """Returns queryset with all people ordered by proximity to reference.coordinates."""
        return (
            self.filter(coordinates__distance_lte=(coordinates, D(mi=radius_mi)))
            .annotate(distance=Distance("coordinates", coordinates))
            .order_by("distance")
        )

    def get_queryset(self):
        return self.filter(is_demo=False)

    def get_demo_queryset(self):
        return self.filter(is_demo=True)


class Person(BaseModelMixin):
    objects = PersonQuerySet.as_manager()

    myc_state_and_id = models.CharField(max_length=255, unique=True, null=True)
    ngp_id = models.CharField(max_length=255, unique=True, null=True)

    # Personal Info
    first_name = models.CharField(max_length=255, blank=True)
    middle_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    suffix = models.CharField(max_length=255, blank=True)

    email = models.EmailField(blank=True, db_index=True)
    phone = PhoneNumberField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, blank=True)  # VAN's schema is VARCHAR(1)

    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=255, blank=True)
    state = USStateField(choices=STATE_CHOICES, blank=True)
    zip5 = USZipCodeField(blank=True)
    coordinates = gis_models.PointField(
        "coordinates", geography=True, srid=4326, null=True
    )

    is_vol_prospect = models.BooleanField(default=False)
    vol_yes_at = models.DateField(null=True, blank=True, db_index=True)

    is_vol_leader = models.BooleanField(default=False)
    suppressed_at = models.DateTimeField(null=True, db_index=True)
    is_demo = models.BooleanField(default=False)

    def suppress(self):
        if not self.suppressed_at:
            self.suppressed_at = timezone.now()
            self.save(update_fields=["suppressed_at"])

    def trimmed_last_name(self):
        if self.last_name:
            return f"{self.last_name[0:1]}."
        return ""

    def get_has_email(self):
        return self.email and self.email != ""

    @property
    def full_name(self):
        name_parts = [self.first_name]
        if self.middle_name:
            name_parts.append(self.middle_name)
        name_parts.append(self.last_name)
        if self.suffix:
            name_parts.append(self.suffix)
        return " ".join(name_parts)

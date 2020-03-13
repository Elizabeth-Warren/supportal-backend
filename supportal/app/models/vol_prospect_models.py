import datetime
import logging

from django.contrib.postgres.fields import ArrayField, JSONField
from django.db import models, transaction
from django.db.models import FilteredRelation, Q
from django.utils import timezone
from enumfields import EnumIntegerField

from supportal.app.common.enums import (
    CanvassResult,
    CanvassResultCategory,
    VolProspectAssignmentStatus,
)
from supportal.app.models import Person, User
from supportal.app.models.base_model_mixin import BaseModelMixin
from supportal.shifter.models import EventSignup

# Maximum number of vol prospects to assign at a time.
VOL_PROSPECT_ASSIGNMENT_BATCH_SIZE = 10

VOL_PROSPECT_ASSIGNMENT_RADII_MILES = [3, 9, 27, 81, 243, 729]


class VolProspectAssignmentQuerySet(models.QuerySet):
    def outstanding(self):
        """Filters to assignments that still need to be contacted."""
        return (
            self.filter(suppressed_at__isnull=True)
            .filter(expired_at__isnull=True)
            .filter(vol_prospect_contact_events=None)
        )

    def expiring(self, days, exact=False):
        """ Gets the users who are expiring in `days` days.
        Optional argument to use exact expirations. I
        left it to default as false because I think we
        should emails at a specific time of day for
        best response rate
        """
        if days >= VolProspectAssignment.VOL_PROSPECT_ASSIGNMENT_DURATION_DAYS:
            raise Exception(
                "Can't offset experation date by more than assignment duration"
            )

        day_start = timezone.now() - datetime.timedelta(
            days=VolProspectAssignment.VOL_PROSPECT_ASSIGNMENT_DURATION_DAYS - days
        )
        day_end = day_start + datetime.timedelta(days=1)

        if not exact:
            day_start.replace(hour=0, minute=0, second=0)
            day_end.replace(hour=0, minute=0, second=0)

        query = self.filter(
            suppressed_at__isnull=True,
            expired_at__isnull=True,
            created_at__lt=day_end,
            created_at__gte=day_start,
        ).exclude(
            vol_prospect_contact_events__result_category__exact=CanvassResultCategory.SUCCESSFUL
        )

        return query

    def expired(self):
        """Filters to assignments that have not been successfully contacted within one week of creation."""
        expire_earlier_than = timezone.now() - datetime.timedelta(
            days=VolProspectAssignment.VOL_PROSPECT_ASSIGNMENT_DURATION_DAYS
        )
        return self.filter(
            suppressed_at__isnull=True,
            expired_at__isnull=True,
            created_at__lt=expire_earlier_than,
        ).exclude(
            vol_prospect_contact_events__result_category__exact=CanvassResultCategory.SUCCESSFUL
        )


class VolProspectAssignmentManager(models.Manager):
    def get_queryset(self):
        return VolProspectAssignmentQuerySet(self.model, using=self._db)

    def get_demo_queryset(self):
        return VolProspectAssignmentQuerySet(self.model, using=self._db).filter(
            person__is_demo=True
        )

    def delete_demo_assignments(self, user):
        self.get_demo_queryset().filter(user=user).delete()

    def has_demo_assignments(self, user):
        self.get_demo_queryset().filter(user=user).exists()

    def has_outstanding_assignments(self, user):
        """Returns whether or not the user has assignments that they must complete before requesting more."""
        return self.get_queryset().filter(user=user).outstanding().exists()

    def expire_assignments(self):
        """Sets expired_at of all expired assignments."""
        return (
            self.get_queryset()
            .expired()
            .update(expired_at=timezone.now(), updated_at=timezone.now())
        )

    def _assign_to_unverified_user(self, user, num):
        demo_people = (
            Person.objects.get_demo_queryset()
            .filter(is_vol_prospect=True, suppressed_at__isnull=True)
            .annotate(
                my_assignments=FilteredRelation(
                    "vol_prospect_assignments",
                    condition=Q(vol_prospect_assignments__user=user),
                )
            )
            .filter(my_assignments=None)[:num]
        )
        return [self.create(user=user, person=assignee) for assignee in demo_people]

    def _assign_to_verified_user(self, user, num, location):
        """ Assign people to a given user.
        Searches for people in 3, 9, 27, 81, 243 mile radii.
        Within each tier, prioritizes by recency of their last vol-yes.
        """
        cumulative_assignees = []
        coordinates = location if location else user.coordinates
        for radius in VOL_PROSPECT_ASSIGNMENT_RADII_MILES:
            num_to_go = num - len(cumulative_assignees)

            if num_to_go <= 0:
                break

            people_pks_already_assigned = [
                assignee.pk for assignee in cumulative_assignees
            ]
            assignees = (
                self._assignable_people(user)
                .from_reference(coordinates, radius)
                .exclude(pk__in=people_pks_already_assigned)
                .order_by("-vol_yes_at")[:num_to_go]
            )

            cumulative_assignees.extend(assignees)

        return [
            self.create(user=user, person=assignee) for assignee in cumulative_assignees
        ]

    def assign(self, user, num=VOL_PROSPECT_ASSIGNMENT_BATCH_SIZE, location=None):
        """Assigns vol prospects to gven user. If the user is not
        verified will assign the demo prospects
        """
        num = min(num, VOL_PROSPECT_ASSIGNMENT_BATCH_SIZE)
        if user.verified_at:
            return self._assign_to_verified_user(user, num, location)
        else:
            return self._assign_to_unverified_user(user, num)

    def _assignable_people(self, user):
        return (
            Person.objects.get_queryset()
            .filter(is_vol_prospect=True)
            .filter(suppressed_at__isnull=True)
            # Exclude any person already assigned to this user.
            .annotate(
                my_assignments=FilteredRelation(
                    "vol_prospect_assignments",
                    condition=Q(vol_prospect_assignments__user=user),
                )
            )
            .filter(my_assignments=None)
            # Exclude any person with a live (not suppressed, not expired) assignment.
            .annotate(
                live_assignments=FilteredRelation(
                    "vol_prospect_assignments",
                    condition=Q(vol_prospect_assignments__suppressed_at__isnull=True)
                    & Q(vol_prospect_assignments__expired_at__isnull=True),
                )
            )
            .filter(live_assignments=None)
        )


class MobilizeAmericaEventSignupExcpetion(Exception):
    """ if you sign up with mobilize america and something goes wrong throw this"""

    def __init__(self, message):
        self.message = message


class VolProspectAssignment(BaseModelMixin):
    VOL_PROSPECT_ASSIGNMENT_DURATION_DAYS = 7

    objects = VolProspectAssignmentManager()

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="vol_prospect_assignments"
    )
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="vol_prospect_assignments"
    )
    suppressed_at = models.DateTimeField(null=True, db_index=True)
    expired_at = models.DateTimeField(null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.CharField(max_length=2500, blank=True, default="")

    @property
    def status(self):
        try:
            res_category = self.vol_prospect_contact_events.latest(
                field_name="created_at"
            ).result_category
        except VolProspectContactEvent.DoesNotExist:
            res_category = None
        suppressed = self.suppressed_at is not None
        person_supressed = self.person.suppressed_at is not None
        return VolProspectAssignmentStatus.from_db_state(
            suppressed, person_supressed, res_category
        )

    def create_contact_event(self, **kwargs):
        """Add a new VolProspectContactEvent to this assignment"""
        if "vol_prospect_assignment" in kwargs:
            del kwargs["vol_prospect_assignment"]
        return self.vol_prospect_contact_events.create(**kwargs)

    def suppress(self):
        if not self.suppressed_at:
            self.suppressed_at = timezone.now()
            self.save(update_fields=["suppressed_at"])

    class Meta:
        unique_together = ("user", "person")


class VolProspectContactEvent(BaseModelMixin):

    vol_prospect_assignment = models.ForeignKey(
        VolProspectAssignment,
        on_delete=models.CASCADE,
        related_name="vol_prospect_contact_events",
    )
    result_category = EnumIntegerField(CanvassResultCategory, db_index=True)
    result = EnumIntegerField(CanvassResult)
    metadata = JSONField(null=True)
    ma_event_id = models.IntegerField(null=True)
    ma_timeslot_ids = ArrayField(models.IntegerField(null=False), null=True)
    note = models.CharField(max_length=2500, blank=True, default="")

    def send_attendance_event_to_mobilize(self):
        person_to_sign_up = self.vol_prospect_assignment.person
        if not person_to_sign_up.email:
            raise MobilizeAmericaEventSignupExcpetion(
                {"error": {"detail": "Email Required"}}
            )
        if person_to_sign_up.is_demo:
            # Don't send demo people to mobilize
            return
        obj = EventSignup.objects.create(
            email=person_to_sign_up.email,
            given_name=person_to_sign_up.first_name,
            family_name=person_to_sign_up.last_name,
            phone=person_to_sign_up.phone,
            zip5=person_to_sign_up.zip5,
            ma_event_id=self.ma_event_id,
            ma_timeslot_ids=self.ma_timeslot_ids,
            source="switchboard",
        )
        ma_creation_successful, ma_response = obj.sync_to_mobilize_america()

        if not ma_creation_successful:
            raise MobilizeAmericaEventSignupExcpetion(ma_response)

    def save(self, *args, **kwargs):
        if not self.result_category:
            self.result_category = self.result.category()
        if self.result_category == CanvassResultCategory.UNREACHABLE:
            with transaction.atomic():
                self.vol_prospect_assignment.suppress()
                self.vol_prospect_assignment.person.suppress()
                return super().save(*args, **kwargs)
        if not self.pk and self.ma_event_id and self.ma_timeslot_ids:
            # when creating a new event, if there is an ma_event send it to MA
            self.send_attendance_event_to_mobilize()
        return super().save(*args, **kwargs)

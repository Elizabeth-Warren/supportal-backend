from django.contrib.gis.geos import Point
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.response import Response

from supportal.app.common.enums import VolProspectAssignmentStatus
from supportal.app.models import (
    MobilizeAmericaEventSignupExcpetion,
    VolProspectAssignment,
    VolProspectContactEvent,
)
from supportal.app.serializers import VolProspectAssignmentSerializer
from supportal.app.serializers.vol_prospect_contact_event_serializer import (
    VolProspectContactEventSerializer,
)


class VolProspectAssignmentViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = VolProspectAssignmentSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]
    base_throttle_scope = "vol_prospect_assignments"

    def get_throttles(self):
        """Custom action-level throttling using ScopedRateThrottle

        Based on:
        https://www.pedaldrivenprogramming.com/2017/05/throttling-django-rest-framwork-viewsets/
        """
        if self.action == "assign":
            self.throttle_scope = f"{self.base_throttle_scope}.assign"
        else:
            self.throttle_scope = self.base_throttle_scope
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user

        if not user.verified_at:
            return VolProspectAssignment.objects.get_demo_queryset().filter(user=user)

        queryset = VolProspectAssignment.objects.filter(
            user=user, expired_at__isnull=True, person__is_demo=False
        )
        status_param = self.request.query_params.get("status", None)
        if status_param:
            vpa_status = VolProspectAssignmentStatus.from_name(status_param)
            if vpa_status.result_category:
                queryset = queryset.filter(
                    vol_prospect_contact_events__result_category=vpa_status.result_category,
                    suppressed_at__isnull=not vpa_status.suppressed,
                )
            else:
                queryset = queryset.filter(
                    vol_prospect_contact_events=None,
                    suppressed_at__isnull=not vpa_status.suppressed,
                )
        return queryset

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed("PUT")

    # TODO: override swagger documentation
    @action(detail=False, methods=["post"])
    def assign(self, request, format=None, *args, **kwargs):
        """
        Assign 10 vol prospects to the authenticated user. Note that if the user
        is not verified, the assignments are made with demo people.
        """
        if VolProspectAssignment.objects.has_outstanding_assignments(request.user):
            return Response(
                {"error": "User has outstanding assignments"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.coordinates:
            return Response(
                {"error": "User missing coordinates"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        location = request.data.get("location", None)
        if location:
            location = Point(
                float(location["longitude"]), float(location["latitude"]), srid=4326
            )
        VolProspectAssignment.objects.assign(request.user, location=location)
        return Response(None, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        s = request.data.get("status")
        note = request.data.get("note")
        vpa = self.get_object()

        # get_object 404s if the request.user and vpa.user don't match
        # keepting things as proection as an extra check
        if vpa.user != request.user:
            return Response(None, status=status.HTTP_403_FORBIDDEN)

        if (
            s
            and VolProspectAssignmentStatus.from_name(s)
            == VolProspectAssignmentStatus.SKIPPED
        ):
            vpa.suppress()

        if note is not None:
            vpa.note = note
            vpa.save()

        return Response(None, status=status.HTTP_204_NO_CONTENT)


class VolProspectContactEventViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = VolProspectContactEventSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["vol_prospect_assignment"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    base_throttle_scope = "vol_prospect_contact_events"

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = f"{self.base_throttle_scope}.create"
        else:
            # Don't rate limit GETS. These should be removed anyway
            self.throttle_scope = None
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        queryset = VolProspectContactEvent.objects.filter(
            vol_prospect_assignment__user=user,
            vol_prospect_assignment__expired_at__isnull=True,
        )
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except MobilizeAmericaEventSignupExcpetion as e:
            return Response(e.message, status=status.HTTP_400_BAD_REQUEST)

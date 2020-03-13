import json
import logging

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db.models import Min
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (
    CreateAPIView,
    GenericAPIView,
    ListAPIView,
    RetrieveAPIView,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

# from ew_common.input_validation import extract_postal_code
from supportal.services.mobilize_america import (
    MobilizeAmericaAPIException,
    get_global_client,
)
from supportal.shifter import mobilize_america_helpers
from supportal.shifter.common.error_codes import (
    ErrorCodes,
    generate_error_for_code,
    get_error_code_and_status,
)
from supportal.shifter.models import MobilizeAmericaEvent, USZip5
from supportal.shifter.serializers import (
    EventSignupSerializer,
    RecommendedEventRequestSerializer,
    USZip5Serializer,
)

EARLY_STATES = ["IA", "NH", "NV", "SC"]


class ShifterWrappedExceptionView(GenericAPIView):
    def handle_exception(self, exc):
        """ wrap the serializer errors to conform to our exception format"""
        exception_response = super().handle_exception(exc)
        response_status = exception_response.status_text
        formated_response_code = response_status.upper().replace(" ", "_")
        error_response = generate_error_for_code(
            formated_response_code, exception_response.data
        )
        return Response(error_response, exception_response.status_code)


class ShifterIPThrottle(AnonRateThrottle):
    """IP-based rate limiter"""

    rate = settings.SHIFTER_IP_RATE_LIMIT


class ShifterViewMixin(ShifterWrappedExceptionView):
    """Default permissions and throttling for all shifter views"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ShifterIPThrottle]


class EventSignupView(CreateAPIView, ShifterViewMixin):
    serializer_class = EventSignupSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
        except ValidationError as e:
            # wrap and catch the exceptions from the serializer
            return Response(
                generate_error_for_code(ErrorCodes.VALIDATION.name, e.detail),
                status=e.status_code,
            )

        if not serializer.data.get("ma_creation_successful"):
            response = serializer.data.get("ma_response")
            if response:
                # if we don't even try to send it to MA, don't wory about this
                error_response, status_code = get_error_code_and_status(response)
                if (
                    status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
                    and status_code != status.HTTP_429_TOO_MANY_REQUESTS
                ):  # retry 500s and 429s on our side
                    return Response(error_response, status=status_code)

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class MobilizeAmericaEventView(RetrieveAPIView, ShifterViewMixin):
    def get(self, request, **kwargs):
        try:
            event_id = int(kwargs.get("id"))
        except ValueError:
            return Response(
                generate_error_for_code(
                    ErrorCodes.INVALID_EVENT_ID.name, {"detail": "Invalid Event ID"}
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        event = MobilizeAmericaEvent.objects.filter(id=event_id, is_active=True)
        if event.exists():
            res = event.first().raw
        else:
            try:
                # get the response from mobilize america if it's not in our DB
                res = get_global_client().get_organization_event(event_id)["data"]
            except MobilizeAmericaAPIException as e:
                error_response, status_code = get_error_code_and_status(e.response)
                return Response(error_response, status=status_code)

        # The frontend is responsible for removing the full timeslots for switchboard/embedded shifter
        sanitized_res = mobilize_america_helpers.sanitize_event_payload(res)
        return Response(sanitized_res, status=status.HTTP_200_OK)


class USZip5View(RetrieveAPIView, ShifterWrappedExceptionView):
    permission_classes = [permissions.AllowAny]
    serializer_class = USZip5Serializer
    lookup_field = "zip5"
    queryset = USZip5.objects.all()


class EarlyStateView(ListAPIView, ShifterViewMixin):
    def get(self, request, **kwargs):
        zip5 = request.query_params.get("zip5")
        if not zip5 or len(zip5) != 5:
            raise ValidationError("zip5 is required")
        try:
            coordinates = USZip5.objects.get(zip5=zip5).coordinates
        except USZip5.DoesNotExist:
            raise ValidationError(f"zip5 {zip5} not found!")

        fargs = {"state__in": EARLY_STATES}
        max_dist = request.query_params.get("max_dist")
        if max_dist:
            fargs["coordinates__distance_lte"] = (coordinates, D(mi=int(max_dist)))

        states = list(
            USZip5.objects.filter(**fargs)
            .values("state")
            # Using MIN here is kind of arbitrary, but it should work better than
            # other aggregates for people in border states.
            # If we actually start using max_dist, we may want to base this not
            # on the event table rather than the zip table.
            .annotate(distance=Min(Distance("coordinates", coordinates)))
            .order_by("distance")
        )
        res = {
            "count": len(states),
            "data": [
                {"state": s["state"], "min_distance": int(s["distance"].mi)}
                for s in states
            ],
        }
        return Response(res, 200)


class RecommendedEventView(ShifterViewMixin, APIView):
    __list_params = {"event_types", "tag_ids", "states"}

    def get(self, request: Request, **kwargs):
        """Returns list of events from Mobilize America."""
        params = get_query_parameter_dict(request, self.__list_params)
        self.__backwards_compat_convert_params(params)

        # Clean up zip5s for mdata. Because of this, the validator will throw
        # an incorrect error message for invalid zip5s (missing).
        # Maybe create a separate endpoint or add and additional param
        # for mdatas if this becomes a problem for the frontend.
        if "zip5" in params:
            # TODO: get the postal code from the zip of zip5
            # params["zip5"] = extract_postal_code(str(params["zip5"]))

        ser = RecommendedEventRequestSerializer(data=params)
        ser.is_valid(raise_exception=True)
        try:
            events = ser.save()
        except USZip5.DoesNotExist:
            return Response(
                generate_error_for_code(ErrorCodes.ZIP_INVALID.name, {}),
                status.HTTP_400_BAD_REQUEST,
            )
        except MobilizeAmericaAPIException as e:
            logging.exception("Got error from Mobilize America")
            error_response, status_code = get_error_code_and_status(e.response)
            return Response(error_response, status=status_code)
        return Response({"count": len(events), "data": events}, 200)

    def __backwards_compat_convert_params(self, params):
        """
        Temporary helper that converts request parameters passed by existing Mobile
        Commons mdatas to our new format.


        Differences:
          - tag_id is now tag_ids
          - while the new backend is being tested, default to the MA API strategy
        """
        if "tag_id" in params:
            params["tag_ids"] = params.pop("tag_id").split(",")


def get_query_parameter_dict(request: Request, list_fields):
    """
    Convert the request's query parameter MultiValueDict to a regular dictionary
    with special handling for list fields.

    For parameters where we expect a list, a caller may pass a comma-separated
    list of values, e.g 'recommended_events?tag_ids=1,2'. We don't, however,
    support repeating the query parameter, e.g, in 'recommended_events?tag_ids=1&tag_ids=2'
    the value of tag_id will be '[2]' not '[1, 2]'. This is different from the
    Mobilize America API, which supports the latter convention and not the former.
    """
    return {
        k: v.split(",") if k in list_fields else v
        for k, v in request.query_params.items()
    }

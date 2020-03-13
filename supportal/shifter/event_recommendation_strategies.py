import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db.models import Min
from rest_framework.exceptions import ValidationError

from supportal.services.mobilize_america import (
    CANVASS,
    MobilizeAmericaAPIException,
    get_global_client,
)
from supportal.shifter.models import MobilizeAmericaEvent, State, USZip5


class BaseRecommendationStrategy(ABC):
    """
    Base class for recommendation strategies

    Implementations must override the find_events method, which is a classmethod
    for now because we don't expect strategies to be stateful.
    """

    @classmethod
    @abstractmethod
    def find_events(
        cls,
        limit: int,
        zip5: Optional[str] = None,
        max_dist: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        timeslot_start: Optional[datetime] = None,
        timeslot_end: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        is_virtual: bool = False,
        states: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        pass


class MobilizeAmericaAPIRecommendationStrategy(BaseRecommendationStrategy):
    @classmethod
    def find_events(
        cls,
        limit,
        zip5=None,
        max_dist=None,
        tag_ids=None,
        timeslot_start=None,
        timeslot_end=None,
        event_types=None,
        is_virtual=False,
        states=None,
    ) -> List[Dict[str, Any]]:
        if timeslot_start:
            timeslot_start_param = f"gte_{int(timeslot_start.timestamp())}"
        else:
            timeslot_start_param = "gte_now"
        if timeslot_end:
            timeslot_end_param = f"lte_{int(timeslot_end.timestamp())}"
        else:
            timeslot_end_param = None

        if states:
            logging.warning(
                "Cannot pass states param when using Mobilize America Recomendation Strategy"
            )

        params = {
            "timeslot_start": timeslot_start_param,
            "tag_id": tag_ids,
            "event_types": event_types,
        }
        if timeslot_end_param:
            params["timeslot_end"] = timeslot_end_param

        if is_virtual:
            params["is_virtual"] = True
        else:
            params["zipcode"] = zip5
            params["max_dist"] = max_dist

        res = get_global_client().list_organization_events(params)
        return next(res)["data"][0:limit]


class DBRecommendationStrategy(BaseRecommendationStrategy):
    @classmethod
    def _should_use_doc_prio(cls, states) -> bool:
        if states:
            states_with_doc_prio = cls._filter_to_states_with_prio(states)
            return len(states_with_doc_prio) > 0
        return False

    @classmethod
    def _filter_to_states_with_prio(cls, state_codes):
        return (
            State.objects.filter(state_code__in=state_codes)
            .filter(use_prioritization_doc=True)
            .exclude(prioritization_doc="")
            .values("state_code")
        )

    @classmethod
    def find_events(
        cls,
        limit,
        zip5=None,
        max_dist=None,
        tag_ids=None,
        timeslot_start=None,
        timeslot_end=None,
        event_types=None,
        is_virtual=False,
        states=None,
    ):
        filter_args = {
            "is_virtual": is_virtual,
            "visibility": settings.MOBILIZE_AMERICA_DEFAULT_VISIBILITY,
            "is_active": True,
        }
        if tag_ids:
            filter_args["tag_ids__overlap"] = tag_ids

        filter_args["timeslots__start_date__gte"] = timeslot_start or datetime.now(
            tz=timezone.utc
        )
        if timeslot_end:
            filter_args["timeslots__end_date__lte"] = timeslot_end
        if event_types:
            filter_args["event_type__in"] = event_types

        if is_virtual:
            events = list(
                MobilizeAmericaEvent.objects.filter(**filter_args)
                .annotate(earliest_timeslot=Min("timeslots__start_date"))
                .order_by("-high_priority", "earliest_timeslot")
                .all()[0:limit]
            )
        else:
            coordinates = USZip5.objects.get(zip5=zip5).coordinates
            if max_dist:
                filter_args["coordinates__distance_lte"] = (
                    coordinates,
                    D(mi=int(max_dist)),
                )

            order_by_list = ["distance", "earliest_timeslot"]

            if cls._should_use_doc_prio(states):
                # If the event is a canvas and the states are in prio mode
                filter_args["state__state_code__in"] = cls._filter_to_states_with_prio(
                    states
                )
                order_by_list = ["state_prioritization", *order_by_list]
            else:
                if states:
                    filter_args["state__state_code__in"] = states

            events = list(
                MobilizeAmericaEvent.objects.filter(**filter_args)
                .annotate(
                    distance=Distance("coordinates", coordinates),
                    earliest_timeslot=Min("timeslots__start_date"),
                )
                .order_by(*order_by_list)
                .all()[0:limit]
            )
        return [e.raw for e in events]

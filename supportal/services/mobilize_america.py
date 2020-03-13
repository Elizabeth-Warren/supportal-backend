import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterator, List, Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from requests import Session
from requests.adapters import HTTPAdapter
from requests.auth import AuthBase
from requests.exceptions import ConnectionError

from urllib3 import Retry

# from ew_common.telemetry import telemetry  # isort:skip

PUBLIC_VISIBILITY = "PUBLIC"
PRIVATE_VISIBILITY = "PRIVATE"
VISIBILITY_TYPES = [PUBLIC_VISIBILITY, PRIVATE_VISIBILITY]
STAGING_URL = "https://staging-api.mobilize.us/v1"

CANVASS = "CANVASS"
EVENT_TYPES = [
    CANVASS,
    "PHONE_BANK",
    "TEXT_BANK",
    "MEETING",
    "COMMUNITY",
    "FUNDRAISER",
    "MEET_GREET",
    "HOUSE_PARTY",
    "VOTER_REG",
    "TRAINING",
    "FRIEND_TO_FRIEND_OUTREACH",
    "DEBATE_WATCH_PARTY",
    "ADVOCACY_CALL",
    "RALLY",
    "TOWN_HALL",
    "OFFICE_OPENING",
    "BARNSTORM",
    "SOLIDARITY_EVENT",
    "COMMUNITY_CANVASS",
    "SIGNATURE_GATHERING",
    "CARPOOL",
    "OTHER",
]

__CLIENT = None


def get_global_client():
    global __CLIENT
    if not __CLIENT:
        org_id = settings.MOBILIZE_AMERICA_ORG_ID
        vis = settings.MOBILIZE_AMERICA_DEFAULT_VISIBILITY
        url = settings.MOBILIZE_AMERICA_BASE_URL
        key = settings.MOBILIZE_AMERICA_API_KEY
        args = [org_id, vis, url, key]
        if not all(args):
            raise ImproperlyConfigured("Missing required Mobilize America settings")
        __CLIENT = MobilizeAmericaClient(*args)

    return __CLIENT


class MobilizeAmericaAPIException(Exception):
    def __init__(self, response, status_code):
        errors = response.get("error", {})
        errors["status_code"] = status_code
        response["error"] = errors
        self.response = response
        self.status_code = status_code
        super().__init__(response, status_code)


class MobilizeAmericaAPIAuth(AuthBase):
    """https://github.com/mobilizeamerica/api#authentication"""

    def __init__(self, api_key):
        self.__bearer = f"Bearer {api_key}"

    def __call__(self, r):
        r.headers["Authorization"] = self.__bearer
        return r


@dataclass
class AttendanceRequestPerson:
    given_name: str
    family_name: str
    email_address: str
    postal_code: str
    phone_number: Optional[str] = None


@dataclass
class Referrer:
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None
    url: Optional[str] = None


class MobilizeAmericaClient:
    def __init__(
        self,
        organization_id,
        default_visibility,
        base_url,
        api_key,
        retries=3,
        backoff_factor=1,
        retry_statuses=(429,),
    ):
        self.organization_id = organization_id
        self.default_visibility = default_visibility
        self.__retries = retries
        self.__backoff_factor = backoff_factor
        self.__retry_statuses = retry_statuses

        self.__session_auth = None
        if api_key is None:
            logging.warning("Instantiating MobilizeAmericaClient without an API key")
        else:
            self.__session_auth = MobilizeAmericaAPIAuth(api_key)
        self.__session = self.__new_session()
        self.__base_url = base_url.strip("/")
        self.__cached_attendances = {}

    def __new_session(self):
        s = Session()
        s.auth = self.__session_auth
        retry = Retry(
            total=self.__retries,
            read=self.__retries,
            connect=self.__retries,
            backoff_factor=self.__backoff_factor,
            status_forcelist=self.__retry_statuses,
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def __make_request(self, method, url, **kwargs):
        logging.debug(f"Making MA API call {method} {url} w/ args {kwargs}")
        try:
            res = self.__session.request(method=method, url=url, **kwargs)
        # retry connection errors once
        except ConnectionError as e:
            logging.warning(
                f"Refreshing session. Error connecting to Mobilize America: {e}"
            )
            self.__session = self.__new_session()
            res = self.__session.request(method=method, url=url, **kwargs)

        try:
            payload = json.loads(res.text)
        except json.decoder.JSONDecodeError:
            payload = {}
            # Still want Mobilize America errors to blow up our spot
            # telemetry.event(
            #     "Mobilize America Json Decode Error",
            #     status_code=res.status_code,
            #     method=method,
            #     url=url,
            # )
        if res.status_code > 399:
            raise MobilizeAmericaAPIException(payload, status_code=res.status_code)
        return payload

    def __paginate(
        self, first_page_response: Dict[str, Any]
    ) -> Iterator[Dict[str, Any]]:
        """Generic method to paginate through Mobilize America GET results"""
        page = first_page_response
        while True:
            yield page
            next_page = page.get("next")
            if not next_page:
                break
            page = self.__make_request("GET", next_page)

    def list_organization_events(self, params=None) -> Iterator[Dict[str, Any]]:
        """List organization events, returns a generator for paging

        See: https://github.com/mobilizeamerica/api#list-organization-events
        """
        params = {"visibility": self.default_visibility, **(params or {})}
        url = f"{self.__base_url}/organizations/{self.organization_id}/events"
        return self.__paginate(self.__make_request("GET", url, params=params))

    def get_organization_event(self, event_id):
        url = (
            f"{self.__base_url}/organizations/{self.organization_id}/events/{event_id}"
        )
        return self.__make_request("GET", url)

    def __is_email_in_attendance(self, email, attendance):
        email_addresses = attendance.get("person", {}).get("email_addresses", [])
        if len(email_addresses) < 1:
            return None
        if email_addresses[0].get("address", None) == email:
            return attendance
        return None

    def __check_cache_for_attendance(self, event_id, timeslot_ids, email):
        event_attendances_in_cache = self.__cached_attendances.get(event_id, {})
        attendances, remaining_timeslots = [], timeslot_ids

        for attendance in event_attendances_in_cache:
            timeslot = attendance.get("timeslot", {}).get("id", None)
            if (
                timeslot
                and (timeslot in timeslot_ids)
                and self.__is_email_in_attendance(email, attendance)
            ):
                attendances.append(attendance)
                remaining_timeslots.remove(timeslot)

        return attendances, remaining_timeslots

    def __update_cache_attendances(self, event_id):
        url = f"{self.__base_url}/organizations/{self.organization_id}/events/{event_id}/attendances"
        all_attendances_for_all_timeslots = self.__make_request("GET", url)["data"]
        self.__cached_attendances[event_id] = all_attendances_for_all_timeslots

    def check_for_event_attendance(self, event_id, timeslot_ids, email):
        attedances, remaining_timeslots = self.__check_cache_for_attendance(
            event_id, timeslot_ids, email
        )
        if not attedances:
            self.__update_cache_attendances(event_id)
            attedances, remaining_timeslots = self.__check_cache_for_attendance(
                event_id, timeslot_ids, email
            )
        return attedances, remaining_timeslots

    def __post_event_attendance(
        self,
        event_id: int,
        timeslot_ids: List[int],
        person: AttendanceRequestPerson,
        referrer: Optional[Referrer] = None,
    ):
        if len(timeslot_ids) == 0:
            return []
        url = f"{self.__base_url}/organizations/{self.organization_id}/events/{event_id}/attendances"
        payload = {
            "person": asdict(person),
            "timeslots": [{"timeslot_id": tid} for tid in timeslot_ids],
            "sms_opt_in": "UNSPECIFIED",
            "transactional_sms_opt_in_status": "UNSPECIFIED",
        }
        if referrer:
            payload["referrer"] = {k: v for k, v in asdict(referrer).items() if v}

        is_ew_email = person.email_address.endswith("@elizabethwarren.com")
        if self.__base_url == STAGING_URL and not is_ew_email:
            return []
        return self.__make_request("POST", url, json=payload)

    def create_event_attendance(
        self,
        event_id: int,
        timeslot_ids: List[int],
        person: AttendanceRequestPerson,
        referrer: Optional[Referrer] = None,
        honor_ma_attendance: bool = True,
    ):
        """Create an event attendance (one or more shifts for a MA event)

         See: https://github.com/mobilizeamerica/api#create-organization-event-attendance
         """
        person_dict = asdict(person)
        existing_attendances, remaining_timeslots = [], timeslot_ids

        if honor_ma_attendance:
            # if we honor MA as source of truth, fitler out timeslots already in MA
            existing_attendances, remaining_timeslots = self.check_for_event_attendance(
                event_id, timeslot_ids, person_dict["email_address"]
            )
        new_attendances_response = self.__post_event_attendance(
            event_id, remaining_timeslots, person, referrer
        )
        if new_attendances_response and len(new_attendances_response["data"]) > 0:
            new_attendances_response["data"].extend(existing_attendances)
            return new_attendances_response, remaining_timeslots
        return {"data": existing_attendances}, []

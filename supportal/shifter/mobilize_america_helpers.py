import itertools
import logging
import urllib
from copy import deepcopy
from datetime import datetime

import pytz

import zipcodes
from supportal.services.mobilize_america import PUBLIC_VISIBILITY

__MA_FIELD_WHITELIST = {
    "browser_url",
    "description",
    "event_type",
    "high_priority",
    "id",
    "location",
    "tags",
    "timeslots",
    "timezone",
    "title",
    # our added fields:
    "formatted_time",
    "local_start_time",
    "times_synopsis",
}


def sanitize_event_payload(payload):
    """
    Remove potentially sensitive fields from the Mobilize America API event
    response.

    This method is required because we fetch events using the authenticated GET
    /events API, which can return private fields that we don't want to serve
    """
    location = payload.pop("location", None)
    address_vis = payload.pop("address_visibility", None)
    sanitized = {k: v for k, v in payload.items() if k in __MA_FIELD_WHITELIST}
    if address_vis == PUBLIC_VISIBILITY:
        sanitized["location"] = location
    elif location and location.get("postal_code"):
        matching_codes = zipcodes.matching(location.get("postal_code"))
        if len(matching_codes) > 0:
            zip_code_data = matching_codes[0]
            location_from_zip = {
                "location": {
                    "longitude": float(zip_code_data["long"]),
                    "latitude": float(zip_code_data["lat"]),
                }
            }
            sanitized["location"] = location_from_zip

    return sanitized


def filter_timeslots_for_time(event, timeslot_start_after_utc, timeslot_end_before_utc):
    event_dupe = deepcopy(event)
    tz = pytz.timezone(event["timezone"])

    timeslots_within_range = []
    for timeslot in event_dupe["timeslots"]:
        timeslot_start = __timestamp_to_datetime_in_zone(timeslot["start_date"], tz)
        timeslot_end = __timestamp_to_datetime_in_zone(timeslot["end_date"], tz)
        is_valid_timeslot = True

        if timeslot_start_after_utc:
            is_valid_timeslot = timeslot_start > timeslot_start_after_utc
        if timeslot_end_before_utc:
            is_valid_timeslot = is_valid_timeslot and (
                timeslot_end < timeslot_end_before_utc
            )

        if is_valid_timeslot:
            timeslots_within_range.append(timeslot)

    event_dupe["timeslots"] = timeslots_within_range
    return event_dupe


def remove_full_timeslots(event):
    event_dupe = deepcopy(event)

    open_timeslots = []
    for timeslot in event_dupe["timeslots"]:
        if not timeslot["is_full"]:
            open_timeslots.append(timeslot)

    event_dupe["timeslots"] = open_timeslots
    return event_dupe


def add_extras_for_mdata(event, utm_source):
    """Given raw Mobilize America event dict, adds extra useful fields.

    - Adds "formatted_time" to each timeslot.
    - Adds "times_synopsis" to the top-level event synopsizing all timeslots.
    - Adds utm_source to browser URL.
    """
    tz = pytz.timezone(event["timezone"])
    for timeslot in event["timeslots"]:
        local_timestamp = __timestamp_to_datetime_in_zone(timeslot["start_date"], tz)
        timeslot["formatted_time"] = __format_event_start_date_and_time(local_timestamp)
        timeslot["local_start_time"] = local_timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    event["times_synopsis"] = __format_event_times_synopsis(
        event["timeslots"], pytz.timezone(event["timezone"])
    )
    event["browser_url"] = __add_utm_source(event["browser_url"], utm_source)
    return event


def __timestamp_to_datetime_in_zone(timestamp, tz):
    return pytz.utc.localize(datetime.utcfromtimestamp(timestamp)).astimezone(tz)


def __format_event_times_synopsis(timeslots, tz):
    """Given an event's timeslots and timezone, returns string summarizing dates and times."""
    timeslots_by_date = itertools.groupby(
        timeslots, lambda x: __timestamp_to_datetime_in_zone(x["start_date"], tz).date()
    )
    date_synopses = []
    times_summaries = []
    formatted_dates = []
    for d, day_timeslots in timeslots_by_date:
        times = []
        for timeslot in day_timeslots:
            timeslot_start = __timestamp_to_datetime_in_zone(timeslot["start_date"], tz)
            times.append(__format_event_start_time(timeslot_start))
        times_summary = __join_with_or(times)
        formatted_date = __format_date(d)
        date_synopses.append(f"{times_summary} on {formatted_date}")

        times_summaries.append(times_summary)
        formatted_dates.append(formatted_date)

    if len(times_summaries) > 1 and times_summaries[1:] == times_summaries[:-1]:
        dates_summary = __join_with_or(formatted_dates)
        summary = f"{times_summaries[0]} on {dates_summary}"
    else:
        summary = "; or ".join(date_synopses)

    return summary


def __join_with_or(times):
    """Returns 'a', 'a or b', or 'a, b, or c'."""
    if not times:
        return ""
    if len(times) == 1:
        return times[0]
    if len(times) == 2:
        return " or ".join(times)
    return ", or ".join([", ".join(times[:-1]), times[-1]])


def __format_event_start_time(t):
    """Formats datetime into e.g. 5PM"""
    strftime_format = "%-I:%M%p"
    return t.strftime(strftime_format).replace(":00", "")


def __format_event_start_date_and_time(t):
    """Formats datetime into e.g. Tue Jul 30 at 5PM"""
    strftime_format = "%a %b %-d at %-I:%M %p"
    return t.strftime(strftime_format)


def __format_date(d):
    """Return e.g. 'Sun 9 Sep'."""
    return d.strftime("%a %b %-d")


def __add_utm_source(browser_url, utm_source):
    """Adds utm_source to browser_url.

    This is the URL parameter Mobilize America uses for attribution tracking.
    """
    if not utm_source:
        return browser_url

    if "?" in browser_url:
        logging.warning(
            f"Mobilize America unexpectedly returned query params in event URL: {browser_url}"
        )
        return browser_url

    return f"{browser_url}?utm_source={urllib.parse.quote(utm_source)}"

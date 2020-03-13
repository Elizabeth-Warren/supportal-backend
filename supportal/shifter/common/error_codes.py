from enum import IntEnum

from rest_framework import status


def get_error_code_and_status(ma_response):
    """ Gets the error response we want to send back to the client
    and the status from the original mobilize america response.
    """
    ma_error = ma_response.get("error", {})
    status_code = ma_error.pop("status_code", status.HTTP_400_BAD_REQUEST)
    error_enum = ErrorCodes.from_error(ma_error)
    error_response = generate_error_for_code(error_enum.name, ma_error)
    return error_response, status_code


def format_zip_error():
    """ Format a zip error response to imitate Mobilizer America's zip error--
    This ensures consistency to the frontend.
    """
    return {"zip5": ["The zip entered is not valid."]}


def generate_error_for_code(code_name, full_error):
    """ Generate an error response object from the code and error message.
    Used to pass through the mobilize america error so
    that the front end has access to it.
    """
    detail = full_error.get("detail")
    if code_name == ErrorCodes.ZIP_INVALID.name:
        return {"code": ErrorCodes.VALIDATION.name, "detail": format_zip_error()}
    return {"code": code_name, "detail": detail or full_error}


class ErrorCodes(IntEnum):
    """ The Enums do not include all the possible errors as it's set up to
    return from the HTTP Status codes that are detailed in
    https://www.django-rest-framework.org/api-guide/status-codes/, but
    without the HTTP_XYZ_ appeneded to the beginning """

    TIMESLOT_FULL = 1
    TIMESLOT_NOT_FOUND = 2
    TIMESLOT_NOT_ASSOCIATED_WITH_EVENT = 3
    ZIP_INVALID = 4
    TIMESLOT_IN_THE_PAST = 5
    UNKNOWN = 6
    GENERIC_PERSON = 7
    NOT_FOUND = 8
    GENERIC_TIMESLOT = 9
    MA_500 = 10
    INVALID_EVENT_ID = 11
    VALIDATION = 12
    BAD_REQUEST = 13
    UNAUTHORIZED = 14
    FORBIDDEN = 15
    METHOD_NOT_ALLOWED = 17
    REQUEST_TIMEOUT = 18
    TOO_MANY_REQUESTS = 19

    @classmethod
    def _map_error_to_code(cls, error_type, error_string):
        if error_string == "Cannot create an attendance for a timeslot in the past.":
            return cls.TIMESLOT_IN_THE_PAST
        elif error_string == "Timeslot does not exist.":
            return cls.TIMESLOT_NOT_FOUND
        elif error_string == "Timeslot is full.":
            return cls.TIMESLOT_FULL
        elif error_string == "Timeslot is not associated with event.":
            return cls.TIMESLOT_NOT_ASSOCIATED_WITH_EVENT
        elif error_string == "Please enter a valid 5-digit US zipcode.":
            return cls.ZIP_INVALID
        elif error_string.endswith("does not appear to be a valid U.S. zipcode."):
            return cls.ZIP_INVALID
        elif error_string == "Not found.":
            return cls.NOT_FOUND
        elif error_type == "person":
            return cls.GENERIC_PERSON
        elif error_type == "timeslots":
            return cls.GENERIC_TIMESLOT
        else:
            return cls.UNKNOWN

    @classmethod
    def from_error(cls, error_object):
        """ If the error is something from the input then throw an
            actual error
        """
        error_code = None
        postal_code_error = error_object.get("person", {}).get("postal_code", [])
        if len(postal_code_error) > 0:
            error_code = cls._map_error_to_code("person", postal_code_error[0])

        timeslot_error = error_object.get("timeslots", [])
        if len(timeslot_error) > 0:
            error_code = cls._map_error_to_code("timeslots", timeslot_error[0])

        toplevel_zipcode_error = error_object.get("zipcode", [])
        if len(toplevel_zipcode_error) > 0:
            error_code = cls._map_error_to_code("zipcode", toplevel_zipcode_error[0])

        event_not_found = error_object.get("detail")
        if event_not_found:
            error_code = cls._map_error_to_code("", event_not_found)

        ma_500_error = error_object.get("status_code", None)

        if ma_500_error and ma_500_error >= 500:
            error_code = cls.MA_500

        if error_code is None:
            error_code = cls.UNKNOWN
        return error_code

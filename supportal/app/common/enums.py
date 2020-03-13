from enum import Enum, IntEnum

from rest_framework.exceptions import ValidationError


class ActivityStatus(IntEnum):
    ACTIVE = 1
    INACTIVE = 2
    CHURNING = 3
    NEW = 4


def enum_from_name(enum_cls, name):
    try:
        return next(i for i in enum_cls if i.name == name)
    except StopIteration:
        raise ValidationError(f"Unknown enum name: {name}")


class CanvassResultCategory(IntEnum):
    SUCCESSFUL = 1
    UNAVAILABLE = 2
    UNREACHABLE = 3

    @classmethod
    def from_name(cls, name):
        return enum_from_name(cls, name)


class CanvassResult(IntEnum):
    """Result codes *must* match VAN canvass results, see vansync.results"""

    UNAVAILABLE_CALL_BACK = 17
    UNAVAILABLE_LEFT_MESSAGE = 19
    UNAVAILABLE_BUSY = 18
    UNREACHABLE_WRONG_NUMBER = 20
    UNREACHABLE_DISCONNECTED = 25
    UNREACHABLE_REFUSED = 2
    UNREACHABLE_MOVED = 5
    UNREACHABLE_DECEASED = 4
    SUCCESSFUL_CANVASSED = 14

    @classmethod
    def from_name(cls, name):
        return enum_from_name(cls, name)

    def category(self):
        prefix = self.name.split("_")[0]
        return CanvassResultCategory.from_name(prefix)


class VolProspectAssignmentStatus(Enum):
    ASSIGNED = (False, None)
    CONTACTED_SUCCESSFUL = (False, CanvassResultCategory.SUCCESSFUL)
    CONTACTED_UNAVAILABLE = (False, CanvassResultCategory.UNAVAILABLE)
    CONTACTED_UNREACHABLE = (True, CanvassResultCategory.UNREACHABLE)
    SKIPPED = (True, None)

    def __init__(self, suppressed, result_category):
        self.suppressed = suppressed
        self.result_category = result_category

    @classmethod
    def from_db_state(
        cls, suppressed, person_supressed, latest_event_result_category=None
    ):
        if not latest_event_result_category:
            if suppressed:
                return cls.SKIPPED
            return cls.ASSIGNED

        if suppressed and not person_supressed:
            return cls.SKIPPED

        if latest_event_result_category == CanvassResultCategory.SUCCESSFUL:
            return cls.CONTACTED_SUCCESSFUL
        elif latest_event_result_category == CanvassResultCategory.UNAVAILABLE:
            return cls.CONTACTED_UNAVAILABLE
        else:
            return cls.CONTACTED_UNREACHABLE

    @classmethod
    def from_name(cls, name):
        return enum_from_name(cls, name)

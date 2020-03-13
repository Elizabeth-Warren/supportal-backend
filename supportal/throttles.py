from django.core.exceptions import ImproperlyConfigured
from rest_framework.throttling import ScopedRateThrottle


class PrefixScopedRateThrottle(ScopedRateThrottle):
    """A Composable ScopedRateThrottle

    The Problem:
      While DRF allows you to use multiple throttle classes, it's not possible to use
      multiple ScopedRateThrottles, for example to limit a specific endpoint to X
      requests a minute and Y requests a day, because they would end up using the
      same cache key. This class allows you to supply a prefix for ScopedRateThrottle's
      cache keys, and therefore to use multiple throttles without cache key collisions.

    Usage:
      Subclass this class and provide a `scope_prefix`. When defining throttle rates in
      in settings.py, prefix the view's throttle scope with your throttle's prefix separated
      by a period: "{prefix}.{view_scope}".

      Note: Throttle rates need to be defined for all views that have throttle_scope defined.
      To change this behavior, override ScopedRateThrottle#allow_request and have it handle
      errors thrown by the `get_rate` function.


    Example:
      # define your throttle in path/to/throttles.py
      class FooThrottle(PrefixScopedRateThrottle):
        scope_prefix = "foo"

      class BarThrottle(PrefixScopedRateThrottle):
        scope_prefix = "bar"

      # In settings.py:
      REST_FRAMEWORK = {
        'DEFAULT_THROTTLE_CLASSES': [
            'path.to.throttles.FooThrottle',
            'path.to.throttles.BarThrottle',
        ],
        'DEFAULT_THROTTLE_RATES': {
            'foo.view_1_scope': '100/day',
            'bar.view_1_scope': '1/minute',
            'foo.view_2_scope': '200/day',
            'bar.view_2_scope': '2/minute',
        }
      }
    """

    scope_prefix = None

    def __init__(self):
        if not getattr(self, "scope_prefix", None):
            raise ImproperlyConfigured(
                f"Missing scope prefix for {self.__class__.__name__}"
            )
        super().__init__()

    def get_rate(self):
        """Determine the string representation of the allowed request rate in DEFAULT_THROTTLES"""
        throttle_rate_key = f"{self.scope_prefix}.{self.scope}"
        try:
            return self.THROTTLE_RATES[throttle_rate_key]
        except KeyError:
            raise ImproperlyConfigured(
                f"No default throttle rate set for {throttle_rate_key} scope"
            )

    def get_cache_key(self, request, view):
        original_cache_key = super().get_cache_key(request, view)
        return f"{self.scope_prefix}_{original_cache_key}"


class HourScopedRateThrottle(PrefixScopedRateThrottle):
    scope_prefix = "hour"

    def parse_rate(self, rate):
        num_requests, duration = super().parse_rate(rate)
        if duration != 3600:
            raise ImproperlyConfigured(
                "HourScopedRateThrottle only accepts rates in hours"
            )
        return num_requests, duration


class DayScopedRateThrottle(PrefixScopedRateThrottle):
    scope_prefix = "day"

    def parse_rate(self, rate):
        num_requests, duration = super().parse_rate(rate)
        if duration != 86400:
            raise ImproperlyConfigured(
                "DayScopedRateThrottle only accepts rates in days"
            )
        return num_requests, duration

from time import sleep

from rest_framework import permissions
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from supportal.throttles import PrefixScopedRateThrottle


class FooThrottle(PrefixScopedRateThrottle):
    scope_prefix = "foo"


class BarThrottle(PrefixScopedRateThrottle):
    scope_prefix = "bar"


class ThrottleTestView(GenericAPIView):
    throttle_classes = [FooThrottle, BarThrottle]
    throttle_scope = "test"
    permission_classes = [permissions.AllowAny]

    def get_throttles(self):
        return super().get_throttles()

    def get(self, r):
        return Response(None, status=204)


def test_throttles_compose(rf, settings):
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
        {"foo.test": "1/sec", "bar.test": "3/hour"}
    )

    view = ThrottleTestView().as_view()
    assert view(rf.get("/")).status_code == 204
    # Trip the sec throttle
    assert view(rf.get("/")).status_code == 429
    sleep(2)
    assert view(rf.get("/")).status_code == 204
    # Trip the hour throttle
    assert view(rf.get("/")).status_code == 429

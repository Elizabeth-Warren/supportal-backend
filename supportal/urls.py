"""supportal URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import json

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseNotFound
from django.urls import include, path, re_path
from rest_framework import routers

from supportal.app import views
from supportal.app.views.email_views import UnsubscribeView
from supportal.app.views.invite_views import InviteViewSet, VerifyView
from supportal.app.views.person_views import PersonViewSet
from supportal.app.views.user_views import FullUserViewSet, MeView
from supportal.app.views.vol_prospect_views import (
    VolProspectAssignmentViewSet,
    VolProspectContactEventViewSet,
)
from supportal.docs import documentation_urls
from supportal.shifter.views import (
    EarlyStateView,
    EventSignupView,
    MobilizeAmericaEventView,
    RecommendedEventView,
    USZip5View,
)

app_name = "supportal"

router = routers.DefaultRouter()
router.register(r"people", PersonViewSet)
router.register(r"users", FullUserViewSet)
router.register(
    r"vol_prospect_assignments",
    VolProspectAssignmentViewSet,
    basename="volprospectassignment",
)
# should events be nested under assignments?
router.register(
    r"vol_prospect_contact_events",
    VolProspectContactEventViewSet,
    basename="volprospectcontactevent",
)

router.register(r"invites", InviteViewSet, basename="invites")

app_urls = router.urls + [
    path("me", MeView.as_view()),
    path("unsubscribe", UnsubscribeView.as_view(), name="unsubscribe"),
    path("verify", VerifyView.as_view()),
]

shifter_urls = [
    path("event_signups", EventSignupView.as_view()),
    path("early_states", EarlyStateView.as_view()),
    path("events/<id>", MobilizeAmericaEventView.as_view()),
    path("recommended_events", RecommendedEventView.as_view()),
    re_path("^zip5s/(?P<zip5>\d+)$", USZip5View.as_view()),
]

api_urls = [
    path("", views.index),
    re_path("^(?P<version>(v1))/", include(app_urls)),
    re_path("^(?P<version>(v1))/shifter/", include(shifter_urls)),
]


urlpatterns = documentation_urls
if settings.DJANGO_ADMIN_ONLY:
    # Production, admin-only instance
    urlpatterns += [path("", admin.site.urls)]
elif settings.DJANGO_ADMIN_ENABLED:
    # Development, full app with the admin interface
    urlpatterns += [path("admin/", admin.site.urls)] + api_urls
else:
    # Production, full app no admin
    urlpatterns += api_urls

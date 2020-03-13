from django.conf.urls import url
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

# TODO: Password-protect the docs. AWS Lambda remaps WWW-Authenticate, so we can't
# use this approach:
# class DocsBasicAuth(BasicAuthentication):
#     """Basic Auth used to provide simple password protection for doc pages
#
#     Using the shared password displays docs for regular users. To see the full
#     API documentation pass your superuser name and password to the browser
#      basic auth prompt.
#     """
#
#     def authenticate_credentials(self, userid, password, request=None):
#         if (
#             settings.DOCUMENTATION_SHARED_USER
#             and userid == settings.DOCUMENTATION_SHARED_USER
#             and settings.DOCUMENTATION_SHARED_PASSWORD
#             and password == settings.DOCUMENTATION_SHARED_PASSWORD
#         ):
#             return (AnonymousUser, None)
#
#         # fall back to BasicAuthentication's default username/password authentication
#         return super().authenticate_credentials(userid, password, request)


schema_view = get_schema_view(
    openapi.Info(
        title="Supportal API",
        default_version="v1",
        description="API Docs for the Supportal!",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

documentation_urls = [
    url(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    url(
        r"^swagger/$",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    url(
        r"^redoc/$", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"
    ),
]

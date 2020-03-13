from django.db.models import Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from supportal.app.models import User
from supportal.app.permissions import IsSupportalAdminUser
from supportal.app.serializers import FullUserSerializer, MeSerializer
from supportal.app.views.pagination import StandardResultsSetPagination


class FullUserViewSet(viewsets.ModelViewSet):
    """Full CRUD User API for superusers"""

    queryset = User.objects.all().filter(is_active=True).order_by("-created_at")
    serializer_class = FullUserSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsSupportalAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["state"]
    ordering_fields = ["state", "city", "email"]

    def _bulk_create(self, request):
        response = []

        for user in request.data:
            serializer = self.get_serializer(data=user, context={"request": request})

            if serializer.is_valid(raise_exception=False):
                self.perform_create(serializer)
                response.append(serializer.data)
            else:
                response.append(
                    {"error": "Invalid user creation", "email": user.get("email")}
                )
        return Response(response, status=201)

    def create(self, request, *args, **kwargs):
        """ Wrapping this to allow the request object
        to be sent to the user_serializer. The requesting
        user gets set as added_by """
        if isinstance(request.data, list):
            return self._bulk_create(request)
        else:
            serializer = self.serializer_class(
                data=request.data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def meta(self, *args, **kwargs):
        data = (
            User.objects.filter(is_active=True)
            .values("state")
            .annotate(count=Count("state"))
            .order_by("state")
        )
        response_data = {
            "all": {"count": User.objects.all().filter(is_active=True).count()},
            "states": list(data),
        }
        return Response(response_data, status=status.HTTP_200_OK)


class MeView(GenericAPIView):
    """User API for normal users to read and update their own information"""

    serializer_class = MeSerializer

    def get(self, request, *args, **kwargs):
        s = self.serializer_class(request.user)
        return Response(s.data)

    def patch(self, request, *args, **kwargs):
        s = self.serializer_class(request.user, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data, status=status.HTTP_201_CREATED)
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

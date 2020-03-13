from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from supportal.app.models import Person
from supportal.app.serializers import FullPersonSerializer


class PersonViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows people to be viewed or edited.
    """

    permission_classes = [IsAdminUser]
    queryset = Person.objects.all().order_by("-vol_yes_at")
    serializer_class = FullPersonSerializer

    def get_serializer(self, *args, **kwargs):
        """Set many=True for lists, so we can serialize multiple incoming objects"""
        if isinstance(kwargs.get("data", {}), list):
            kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

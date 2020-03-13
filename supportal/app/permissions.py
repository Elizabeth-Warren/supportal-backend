from rest_framework.permissions import BasePermission


def check_user_attribute(user, attribute):
    return hasattr(user, attribute) and bool(getattr(user, attribute))


class IsSuperuser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and check_user_attribute(request.user, "is_superuser"))


class IsSupportalAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and (
                check_user_attribute(request.user, "is_admin")
                or check_user_attribute(request.user, "is_staff")
            )
        )


class HasInvite(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and check_user_attribute(request.user, "has_invite"))

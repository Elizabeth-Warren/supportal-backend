from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.gis import admin as gis_admin

from supportal.app.models import APIKey, Person

User = get_user_model()


class CustomUserAdmin(UserAdmin, gis_admin.GeoModelAdmin):
    model = User
    list_display = [
        "username",
        "email",
        "is_staff",
        "is_superuser",
        "date_joined",
        "last_login",
    ]
    ordering = ["username"]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "phone")}),
        ("Address", {"fields": ("address", "city", "state", "zip5", "coordinates")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ["wide"],
                "fields": [
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ],
            },
        ),
    )


class CustomPersonAdmin(admin.ModelAdmin):
    model = Person
    list_display = [
        "ngp_id",
        "first_name",
        "last_name",
        "state",
        "is_vol_prospect",
        "vol_yes_at",
        "is_vol_leader",
        "created_at",
        "updated_at",
    ]
    ordering = ["-updated_at"]


admin.site.register(User, CustomUserAdmin)
admin.site.register(APIKey, admin.ModelAdmin)
admin.site.register(Person, CustomPersonAdmin)

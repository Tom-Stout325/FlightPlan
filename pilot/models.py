# pilot/models.py

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now

from flightlogs.models import FlightLog


# -----------------------------------------------------------------------------
# Ownership / Scoping
# -----------------------------------------------------------------------------

def _ownership_error():
    return "You do not have permission to access or modify this object."


class OwnedModelMixin(models.Model):
    """
    Abstract mixin for user-owned rows.

    - Requires a `user` FK on the model.
    - Provides `_assert_owned_fk()` to validate related objects belong to the same user.
    - Calls full_clean() on save to enforce clean() and field validation.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True

    def _assert_owned_fk(self, field_name: str, obj):
        """
        Validate that a related FK object's `user_id` matches this object's `user_id`.
        Adds a form-friendly ValidationError for the field.
        """
        if obj is None:
            return
        obj_user_id = getattr(obj, "user_id", None)
        if obj_user_id is None:
            # Related object does not expose a user_id; can't validate ownership here
            return
        if self.user_id and obj_user_id != self.user_id:
            raise ValidationError({field_name: _ownership_error()})

    def save(self, *args, **kwargs):
        # Enforce validation consistency (same pattern you use elsewhere)
        self.full_clean()
        return super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# Upload paths (user-scoped)
# -----------------------------------------------------------------------------

def license_upload_path(instance: "PilotProfile", filename: str) -> str:
    username = instance.user.username if instance.user_id else "unknown"
    return f"pilot_licenses/{username}/{filename}"


def training_certificate_upload_path(instance: "Training", filename: str) -> str:
    username = instance.user.username if instance.user_id else "unknown"
    return f"training_certificates/{username}/{filename}"


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class PilotProfile(models.Model):
    """
    Pilot profile is already user-anchored via OneToOneField.
    This is effectively "owned" by the user by design.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    license_number = models.CharField(max_length=100, blank=True, null=True)
    license_date = models.DateField(blank=True, null=True)
    license_image = models.ImageField(upload_to=license_upload_path, blank=True, null=True)

    def flights_this_year(self):
        return FlightLog.objects.filter(
            pilot_in_command__iexact=f"{self.user.first_name} {self.user.last_name}",
            flight_date__year=now().year,
        ).count()

    def flights_total(self):
        return FlightLog.objects.filter(
            pilot_in_command__iexact=f"{self.user.first_name} {self.user.last_name}",
        ).count()

    def flight_time_this_year(self):
        logs = FlightLog.objects.filter(
            pilot_in_command__iexact=f"{self.user.first_name} {self.user.last_name}",
            flight_date__year=now().year,
        ).values_list("air_time", flat=True)
        return sum((t.total_seconds() for t in logs if t), 0)

    def flight_time_total(self):
        logs = FlightLog.objects.filter(
            pilot_in_command__iexact=f"{self.user.first_name} {self.user.last_name}",
        ).values_list("air_time", flat=True)
        return sum((t.total_seconds() for t in logs if t), 0)

    def __str__(self):
        return self.user.username

    class Meta:
        db_table = "app_pilotprofile"


class Training(OwnedModelMixin):
    """
    User-owned training record.

    Ownership rules:
    - Training.user is the canonical owner
    - Training.pilot must belong to the same user (PilotProfile.user == Training.user)
    """
    pilot = models.ForeignKey(
        "PilotProfile",
        on_delete=models.CASCADE,
        related_name="trainings",
    )

    title = models.CharField(max_length=200)
    date_completed = models.DateField()
    required = models.BooleanField(default=False)
    certificate = models.FileField(
        upload_to=training_certificate_upload_path,
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "app_training"
        ordering = ["-date_completed"]

    def clean(self):
        super().clean()

        errors = {}

        # Ensure pilot belongs to the same user
        if self.pilot_id:
            if not self.user_id and self.pilot.user_id:
                # If user not set yet, default it from pilot
                self.user_id = self.pilot.user_id
            elif self.user_id and self.pilot.user_id != self.user_id:
                errors["pilot"] = _ownership_error()

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.title} ({self.date_completed})"

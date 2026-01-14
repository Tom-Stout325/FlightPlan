# common/models.py
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

def _ownership_error():
    return "Invalid related object."

class OwnedModelMixin(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if not self.user_id:
            raise ValidationError("Owner must be set.")

    def _assert_owned_fk(self, field_name: str, obj) -> None:
        if obj is None:
            return
        if not hasattr(obj, "user_id"):
            return
        if not self.user_id:
            raise ValidationError({field_name: "Owner must be set before validating related objects."})
        if obj.user_id != self.user_id:
            raise ValidationError({field_name: _ownership_error()})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

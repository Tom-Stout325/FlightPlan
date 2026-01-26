# money/forms/clients/clients.py

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from money.models import Client


class ClientForm(forms.ModelForm):
    """
    Client form that:
      - normalizes/validates fields
      - enforces per-user unique email
      - (critical) ensures instance.user is set early so OwnedModelMixin / model.clean()
        does not raise "Owner must be set" during is_valid() / full_clean().
    """

    class Meta:
        model = Client
        fields = [
            "business",
            "first",
            "last",
            "street",
            "address2",
            "email",
            "phone",
        ]
        widgets = {
            "business": forms.TextInput(attrs={"class": "form-control"}),
            "first": forms.TextInput(attrs={"class": "form-control"}),
            "last": forms.TextInput(attrs={"class": "form-control"}),
            "street": forms.TextInput(attrs={"class": "form-control"}),
            "address2": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # IMPORTANT:
        # Django ModelForms call instance.full_clean() during form.is_valid().
        # If Client inherits OwnedModelMixin (or model.clean requires user),
        # we must set instance.user BEFORE validation runs.
        if self.user and not getattr(self.instance, "user_id", None):
            self.instance.user = self.user

    # --- normalizers ---------------------------------------------------------

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()

        # Strip common text inputs
        for f in ("business", "first", "last", "street", "address2", "phone"):
            val = cleaned.get(f)
            if isinstance(val, str):
                cleaned[f] = val.strip()

        # Ensure instance owner is set even if something re-instantiated the form
        if self.user and not getattr(self.instance, "user_id", None):
            self.instance.user = self.user

        # Per-user unique email check (case-insensitive normalization above)
        email = cleaned.get("email")
        if email and self.user:
            qs = Client.objects.filter(user=self.user, email=email)
            if getattr(self.instance, "pk", None):
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({"email": "You already have a client with this email."})

        return cleaned

    # --- persistence ---------------------------------------------------------

    def save(self, commit=True):
        obj = super().save(commit=False)

        # Make absolutely sure we persist the owner
        if self.user and not getattr(obj, "user_id", None):
            obj.user = self.user

        if commit:
            obj.save()
            self.save_m2m()

        return obj

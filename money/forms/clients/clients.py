# money/forms/clients/clients.py

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from money.models import Client


class ClientForm(forms.ModelForm):
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

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()

        for f in ("business", "first", "last", "street", "address2", "phone"):
            if cleaned.get(f):
                cleaned[f] = cleaned[f].strip()

        email = cleaned.get("email")
        if email and self.user:
            qs = Client.objects.filter(user=self.user, email=email)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({"email": "You already have a client with this email."})

        return cleaned

# _FLIGHTPLAN/money/forms/taxes/taxes.py

from __future__ import annotations

from django import forms

from money.models import (
    Category,
    Client,
    Event,
    InvoiceV2,
    Miles,
    MileageRate,
    SubCategory,
    Vehicle,
)


class UserOwnedModelFormMixin:
    """
    Ensures:
    - FK dropdowns are user-scoped (where applicable)
    - instance.user is set on save for OwnedModelMixin models
    """

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def _require_user(self):
        if not self.user:
            raise ValueError("This form requires user=... for proper queryset scoping.")

    def save(self, commit=True):
        obj = super().save(commit=False)
        if hasattr(obj, "user_id"):
            self._require_user()
            obj.user = self.user
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class CategoryForm(UserOwnedModelFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["category"]
        widgets = {
            "category": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Enter category name"}
            ),
        }


class SubCategoryForm(UserOwnedModelFormMixin, forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = ["sub_cat", "category"]
        widgets = {
            "sub_cat": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Enter sub-category name"}
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.user and "category" in self.fields:
            self.fields["category"].queryset = (
                Category.objects.filter(user=self.user).order_by("category")
            )


class MileageForm(UserOwnedModelFormMixin, forms.ModelForm):
    class Meta:
        model = Miles
        fields = [
            "date",
            "begin",
            "end",
            "client",
            "event",
            "invoice_v2",
            "invoice_number",
            "vehicle",
            "mileage_type",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "begin": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
            "end": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
            "client": forms.Select(attrs={"class": "form-select"}),
            "event": forms.Select(attrs={"class": "form-select"}),
            "invoice_v2": forms.Select(attrs={"class": "form-select"}),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "vehicle": forms.Select(attrs={"class": "form-select"}),
            "mileage_type": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.user:
            return

        if "vehicle" in self.fields:
            self.fields["vehicle"].queryset = (
                Vehicle.objects.filter(user=self.user, is_active=True)
                .order_by("-is_active", "name")
            )

        if "client" in self.fields:
            self.fields["client"].queryset = (
                Client.objects.filter(user=self.user)
                .order_by("business", "last", "first")
            )

        if "event" in self.fields:
            self.fields["event"].queryset = (
                Event.objects.filter(user=self.user)
                .order_by("-event_year", "title")
            )

        if "invoice_v2" in self.fields:
            self.fields["invoice_v2"].queryset = (
                InvoiceV2.objects.filter(user=self.user)
                .order_by("-date", "-invoice_number")
            )

    def clean(self):
        cleaned = super().clean()
        begin = cleaned.get("begin")
        end = cleaned.get("end")
        if begin is not None and end is not None and end < begin:
            self.add_error("end", "End mileage must be greater than or equal to Begin mileage.")
        return cleaned

    def save(self, commit=True):
        obj: Miles = super().save(commit=False)

        if hasattr(obj, "user_id"):
            self._require_user()
            obj.user = self.user

        if obj.invoice_v2 and not obj.invoice_number:
            obj.invoice_number = obj.invoice_v2.invoice_number

        if commit:
            obj.save()
            self.save_m2m()
        return obj


class MileageRateForm(forms.ModelForm):
    """
    MileageRate is NOT OwnedModelMixin; it has optional user for per-user overrides.
    """

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = MileageRate
        fields = ["rate"]
        widgets = {
            "rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
        }

    def save(self, commit=True):
        obj: MileageRate = super().save(commit=False)
        if self.user is not None:
            obj.user = self.user
        if commit:
            obj.save()
        return obj

# money/forms/invoices/invoice_v2.py

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, ModelChoiceField, inlineformset_factory

from money.models import Client, Event, InvoiceItemV2, InvoiceV2, Service, SubCategory


# -----------------------------------------------------------------------------
# Choice fields
# -----------------------------------------------------------------------------
class ClientChoiceField(ModelChoiceField):
    """
    Purely controls how each Client appears in the <select>.
    Does NOT affect what gets saved.
    """

    def label_from_instance(self, obj):
        business = (getattr(obj, "business", "") or "").strip()
        if business:
            return business

        last = (getattr(obj, "last", "") or "").strip()
        first = (getattr(obj, "first", "") or "").strip()
        if last and first:
            return f"{last}, {first}"
        return last or first or "Unnamed Client"


# -----------------------------------------------------------------------------
# Invoice header form
# -----------------------------------------------------------------------------
class InvoiceV2Form(forms.ModelForm):
    client = ClientChoiceField(queryset=Client.objects.none())

    class Meta:
        model = InvoiceV2
        fields = [
            "client",
            "service",
            "event",
            "event_name",
            "location",
            "date",
            "due",
            "paid_date",
            "status",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "due": forms.DateInput(attrs={"type": "date"}),
            "paid_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Bootstrap-ish widgets (matches your template expectations)
        for field in self.fields.values():
            w = field.widget
            existing = w.attrs.get("class", "")
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs["class"] = (existing + " form-select").strip()
            else:
                w.attrs["class"] = (existing + " form-control").strip()

        # Scope dropdowns by owner
        if user is not None:
            self.fields["client"].queryset = (
                Client.objects.filter(user=user).order_by("business", "last", "first")
            )
            self.fields["service"].queryset = (
                Service.objects.filter(user=user).order_by("service")
            )
            self.fields["event"].queryset = (
                Event.objects.filter(user=user).order_by("-event_year", "title")
            )

        # Optional placeholder for event
        if "event" in self.fields:
            self.fields["event"].required = False

    def clean(self):
        cleaned = super().clean()

        # Nice UX: if event is selected and event_name is blank, default it.
        event = cleaned.get("event")
        event_name = cleaned.get("event_name")
        if event and not (event_name or "").strip():
            cleaned["event_name"] = getattr(event, "title", "") or ""

        # Optional UX: if paid_date exists, auto-set status to Paid (but still allow user override if needed)
        paid_date = cleaned.get("paid_date")
        status = cleaned.get("status")
        if paid_date and status != InvoiceV2.STATUS_PAID:
            cleaned["status"] = InvoiceV2.STATUS_PAID

        return cleaned


# -----------------------------------------------------------------------------
# Line item form
# -----------------------------------------------------------------------------
class InvoiceItemV2Form(forms.ModelForm):
    class Meta:
        model = InvoiceItemV2
        fields = ["description", "qty", "price", "sub_cat"]
        widgets = {
            "description": forms.TextInput(),
            "qty": forms.NumberInput(),
            "price": forms.NumberInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Table-friendly widgets (your template renders raw fields)
        self.fields["description"].widget.attrs.update({"class": "form-control"})
        self.fields["qty"].widget.attrs.update(
            {"class": "form-control text-end", "inputmode": "decimal", "step": "0.01", "min": "0"}
        )
        self.fields["price"].widget.attrs.update(
            {"class": "form-control text-end", "inputmode": "decimal", "step": "0.01", "min": "0"}
        )
        self.fields["sub_cat"].widget.attrs.update({"class": "form-select"})

        # Scope sub-categories by owner (and keep ordering stable)
        if user is not None:
            self.fields["sub_cat"].queryset = (
                SubCategory.objects.filter(user=user)
                .select_related("category")
                .order_by("category__category", "sub_cat")
            )

    def clean_qty(self):
        qty = self.cleaned_data.get("qty")
        if qty is None:
            return qty
        if qty <= Decimal("0"):
            raise ValidationError("Qty must be greater than 0.")
        return qty

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is None:
            return price
        if price < Decimal("0"):
            raise ValidationError("Price cannot be negative.")
        return price


# -----------------------------------------------------------------------------
# Line item formset
# -----------------------------------------------------------------------------
class BaseInvoiceItemV2FormSet(BaseInlineFormSet):
    """
    CRITICAL for OwnedModelMixin:
    - InvoiceItemV2.clean() requires item.user to be set BEFORE validation.
    - This formset ensures each child form.instance.user is set pre-is_valid().
    - Also enforces at least one meaningful (non-deleted) line item.
    """

    def __init__(self, *args, user=None, **kwargs):
        self._user = user
        super().__init__(*args, **kwargs)

        if self._user is not None:
            for f in self.forms:
                f.instance.user = self._user

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        has_item = False
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            desc = (form.cleaned_data.get("description") or "").strip()
            qty = form.cleaned_data.get("qty")
            price = form.cleaned_data.get("price")
            sub_cat = form.cleaned_data.get("sub_cat")

            # Count row if anything was entered (and not deleted)
            if desc or qty is not None or price is not None or sub_cat is not None:
                has_item = True
                break

        if not has_item:
            raise ValidationError("Add at least one line item.")

    def save_new(self, form, commit=True):
        """
        Ensure user is set on NEW inline objects before model validation/save.
        """
        obj = super().save_new(form, commit=False)
        if self._user is not None and not obj.user_id:
            obj.user = self._user
        if commit:
            obj.save()
        return obj


InvoiceItemV2FormSet = inlineformset_factory(
    parent_model=InvoiceV2,
    model=InvoiceItemV2,
    form=InvoiceItemV2Form,
    formset=BaseInvoiceItemV2FormSet,
    extra=1,
    can_delete=True,
)

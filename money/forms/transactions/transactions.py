# money/forms/transactions/transactions.py

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from ...models import Category, Event, RecurringTransaction, SubCategory, Team, Transaction


class TransForm(forms.ModelForm):
    """
    Transaction form.

    Notes:
    - `Transaction.category` is REQUIRED at the model level.
    - This form intentionally does NOT expose `category` directly.
      Category is derived from the selected SubCategory (sub_cat).
    - Views also enforce category alignment as an extra safety net.
    """

    invoice_number = forms.CharField(
        label="Invoice Number (Optional)",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    event = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        label="Event",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        label="Team",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    sub_cat = forms.ModelChoiceField(
        queryset=SubCategory.objects.none(),
        label="Sub-Category",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Transaction
        fields = (
            "invoice_number",
            "date",
            "trans_type",
            "sub_cat",
            "amount",
            "team",
            "transaction",
            "receipt",
            "transport_type",
            "event",
        )
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "trans_type": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "transaction": forms.TextInput(attrs={"class": "form-control"}),
            "receipt": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "transport_type": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        """
        If the view passes `user`, scope dropdowns to that user.
        Falls back to unscoped querysets (useful for admin/tests),
        but your views should pass user to prevent leakage.
        """
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user is not None:
            self.fields["event"].queryset = Event.objects.filter(user=self.user).order_by("title")
            self.fields["team"].queryset = Team.objects.filter(user=self.user).order_by("name")
            self.fields["sub_cat"].queryset = SubCategory.objects.filter(user=self.user).order_by(
                "category__category",
                "sub_cat",
            )
        else:
            # Fallbacks
            self.fields["event"].queryset = Event.objects.all().order_by("title")
            self.fields["team"].queryset = Team.objects.all().order_by("name")
            self.fields["sub_cat"].queryset = SubCategory.objects.all().order_by("category__category", "sub_cat")

    def clean_receipt(self):
        receipt = self.cleaned_data.get("receipt")
        if receipt and hasattr(receipt, "content_type"):
            if receipt.content_type not in ["application/pdf", "image/jpeg", "image/png"]:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return receipt

    def clean_sub_cat(self):
        sub_cat = self.cleaned_data.get("sub_cat")
        if sub_cat and self.user is not None:
            # Defensive: prevent cross-user FK selection even if someone tampers POST data.
            if getattr(sub_cat, "user_id", None) != self.user.id:
                raise ValidationError("Invalid sub-category selection.")
        return sub_cat

    def clean_event(self):
        event = self.cleaned_data.get("event")
        if event and self.user is not None:
            if getattr(event, "user_id", None) != self.user.id:
                raise ValidationError("Invalid event selection.")
        return event

    def clean_team(self):
        team = self.cleaned_data.get("team")
        if team and self.user is not None:
            if getattr(team, "user_id", None) != self.user.id:
                raise ValidationError("Invalid team selection.")
        return team

    def clean(self):
        cleaned = super().clean()

        # Ensure category is set based on selected sub_cat (since category is required).
        sub_cat = cleaned.get("sub_cat")
        if sub_cat:
            cleaned["category"] = sub_cat.category
        else:
            # Without a sub_cat, we can't satisfy required Transaction.category because
            # category is not exposed in this form.
            raise ValidationError("Please select a Sub-Category.")

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Ensure user is set by the view; keep form safe if used elsewhere.
        if self.user is not None and not instance.user_id:
            instance.user = self.user

        # Force category alignment
        if instance.sub_cat_id:
            instance.category = instance.sub_cat.category

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RecurringTransactionForm(forms.ModelForm):
    """
    Recurring transaction template form.

    - Category can be selected directly OR derived from sub_cat.
    - In your views we also force-align category if sub_cat is present.
    """

    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        label="Team",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    event = forms.ModelChoiceField(
        queryset=Event.objects.none(),
        label="Event",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        label="Category (Optional)",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Auto-filled from Sub-Category if selected.",
    )

    sub_cat = forms.ModelChoiceField(
        queryset=SubCategory.objects.none(),
        label="Sub-Category (Optional)",
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = RecurringTransaction
        fields = [
            "trans_type",
            "category",
            "sub_cat",
            "amount",
            "transaction",
            "day",
            "team",
            "event",
            "receipt",
            "active",
        ]
        widgets = {
            "trans_type": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "transaction": forms.TextInput(attrs={"class": "form-control"}),
            "day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 31}),
            "receipt": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user is not None:
            self.fields["event"].queryset = Event.objects.filter(user=self.user).order_by("title")
            self.fields["team"].queryset = Team.objects.filter(user=self.user).order_by("name")
            self.fields["category"].queryset = Category.objects.filter(user=self.user).order_by("category")
            self.fields["sub_cat"].queryset = SubCategory.objects.filter(user=self.user).order_by(
                "category__category",
                "sub_cat",
            )
        else:
            self.fields["event"].queryset = Event.objects.all().order_by("title")
            self.fields["team"].queryset = Team.objects.all().order_by("name")
            self.fields["category"].queryset = Category.objects.all().order_by("category")
            self.fields["sub_cat"].queryset = SubCategory.objects.all().order_by("category__category", "sub_cat")

    def clean_sub_cat(self):
        sub_cat = self.cleaned_data.get("sub_cat")
        if sub_cat and self.user is not None:
            if getattr(sub_cat, "user_id", None) != self.user.id:
                raise ValidationError("Invalid sub-category selection.")
        return sub_cat

    def clean_category(self):
        category = self.cleaned_data.get("category")
        if category and self.user is not None:
            if getattr(category, "user_id", None) != self.user.id:
                raise ValidationError("Invalid category selection.")
        return category

    def clean_event(self):
        event = self.cleaned_data.get("event")
        if event and self.user is not None:
            if getattr(event, "user_id", None) != self.user.id:
                raise ValidationError("Invalid event selection.")
        return event

    def clean_team(self):
        team = self.cleaned_data.get("team")
        if team and self.user is not None:
            if getattr(team, "user_id", None) != self.user.id:
                raise ValidationError("Invalid team selection.")
        return team

    def clean(self):
        cleaned = super().clean()
        sub_cat = cleaned.get("sub_cat")
        category = cleaned.get("category")

        if sub_cat:
            cleaned["category"] = sub_cat.category
        elif not category:
            raise ValidationError("Select either a Sub-Category or a Category.")

        # Validate day range a bit more strictly (optional but nice)
        day = cleaned.get("day")
        if day is not None and not (1 <= int(day) <= 31):
            raise ValidationError("Day must be between 1 and 31.")

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        if self.user is not None and not instance.user_id:
            instance.user = self.user

        if instance.sub_cat_id:
            instance.category = instance.sub_cat.category

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RunRecurringForMonthForm(forms.Form):
    month = forms.IntegerField(min_value=1, max_value=12)
    year = forms.IntegerField(min_value=1900, max_value=9999)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["month"].initial = today.month
        self.fields["year"].initial = today.year

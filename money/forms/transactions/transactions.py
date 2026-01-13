# money/forms/transactions/transactions.py

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from ...models import Category, Event, RecurringTransaction, SubCategory, Team, Transaction




class TransForm(forms.ModelForm):
    """
    Transaction form (mobile-friendly Bootstrap widgets).

    Key rules:
    - Transaction.category is REQUIRED on the model, but not exposed on the form.
      We derive category from the selected sub_cat.
    - Transaction is OwnedModelMixin-backed and calls full_clean() in save(),
      so we MUST set instance.user (owner) and instance.category BEFORE model validation.
    - All dropdowns are user-scoped when `user` is provided.
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
        required=True,  # you said no blank subcategories allowed
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

    def __init__(self, *args, user=None, **kwargs):
        """
        Views should pass `user=request.user`.

        This scopes all FK dropdowns and also sets instance.user early so that:
        - ModelForm._post_clean -> instance.full_clean() doesn't fail with "Owner must be set."
        """
        super().__init__(*args, **kwargs)
        self.user = user

        # Set owner EARLY (critical for OwnedModelMixin + model.save() calling full_clean())
        if self.user is not None and not getattr(self.instance, "user_id", None):
            self.instance.user = self.user

        # User-scoped dropdowns
        if self.user is not None:
            self.fields["event"].queryset = Event.objects.filter(user=self.user).order_by("title")
            self.fields["team"].queryset = Team.objects.filter(user=self.user).order_by("name")
            self.fields["sub_cat"].queryset = SubCategory.objects.filter(user=self.user).order_by(
                "category__category",
                "sub_cat",
            )
        else:
            # Fallbacks (admin/tests)
            self.fields["event"].queryset = Event.objects.all().order_by("title")
            self.fields["team"].queryset = Team.objects.all().order_by("name")
            self.fields["sub_cat"].queryset = SubCategory.objects.all().order_by("category__category", "sub_cat")

    # ----------------------------
    # Field-level validation (ownership)
    # ----------------------------

    def clean_sub_cat(self):
        sub_cat = self.cleaned_data.get("sub_cat")
        if sub_cat and self.user is not None and getattr(sub_cat, "user_id", None) != self.user.id:
            raise ValidationError("Invalid sub-category selection.")
        return sub_cat

    def clean_event(self):
        event = self.cleaned_data.get("event")
        if event and self.user is not None and getattr(event, "user_id", None) != self.user.id:
            raise ValidationError("Invalid event selection.")
        return event

    def clean_team(self):
        team = self.cleaned_data.get("team")
        if team and self.user is not None and getattr(team, "user_id", None) != self.user.id:
            raise ValidationError("Invalid team selection.")
        return team

    # ----------------------------
    # Form-wide validation
    # ----------------------------

    def clean(self):
        cleaned = super().clean()

        # Defensive: ensure owner is still present
        if self.user is not None and not getattr(self.instance, "user_id", None):
            self.instance.user = self.user

        # sub_cat is required by business rule and by this form design
        if not cleaned.get("sub_cat"):
            raise ValidationError("Please select a Sub-Category.")

        return cleaned

    def _post_clean(self):
        """
        Critical hook: called before the model instance is validated.

        We must set:
        - instance.user (owner)
        - instance.category (required field) derived from sub_cat

        BEFORE instance.full_clean() runs, otherwise model validation may fail.
        """
        # Ensure owner BEFORE model validation
        if self.user is not None and not getattr(self.instance, "user_id", None):
            self.instance.user = self.user

        sub_cat = self.cleaned_data.get("sub_cat")
        if sub_cat:
            # Ensure instance has required FK set before validation
            self.instance.sub_cat = sub_cat
            self.instance.category = sub_cat.category

        super()._post_clean()

    # ----------------------------
    # Save
    # ----------------------------

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Final guard: user should always be set
        if self.user is not None and not instance.user_id:
            instance.user = self.user

        # Final guard: align category with sub_cat
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

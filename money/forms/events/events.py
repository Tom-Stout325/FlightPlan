# money/forms/events/events.py

from django import forms
from django.utils import timezone
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit

from money.models import Client, Event


def year_choices(start=2020, years_ahead=2):
    current = timezone.localdate().year
    return [(y, str(y)) for y in range(start, current + years_ahead + 1)]


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "client",
            "event_year",
            "event_type",
            "location_address",
            "location_city",
            "notes",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "client": forms.Select(attrs={"class": "form-select"}),
            "event_year": forms.Select(choices=year_choices(), attrs={"class": "form-select"}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "location_address": forms.TextInput(attrs={"class": "form-control"}),
            "location_city": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        # Try to accept user from the view so we can scope the client dropdown.
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Dynamic year choices
        self.fields["event_year"].choices = year_choices()

        if self.user is not None:
            self.fields["client"].queryset = Client.objects.filter(user=self.user).order_by("business", "last", "first")
        else:
            self.fields["client"].queryset = Client.objects.none()

        self.fields["client"].required = False

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.label_class = "fw-semibold"
        self.helper.layout = Layout(
            Row(
                Column("title", css_class="col-12 col-md-6"),
                Column("client", css_class="col-12 col-md-6"),
            ),
            Row(
                Column("event_type", css_class="col-12 col-md-4"),
                Column("event_year", css_class="col-12 col-md-4"),
                Column("location_city", css_class="col-12 col-md-4"),
            ),
            Row(
                Column("location_address", css_class="col-12"),
            ),
            Row(Column("notes", css_class="col-12")),
            Submit("submit", "Save Job", css_class="btn btn-primary float-end"),
        )

    def clean(self):
        cleaned = super().clean()
        for f in ("title", "location_city", "location_address"):
            if cleaned.get(f):
                cleaned[f] = cleaned[f].strip()
        if cleaned.get("notes"):
            cleaned["notes"] = cleaned["notes"].strip()
        return cleaned

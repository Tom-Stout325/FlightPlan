# money/forms/events/events.py

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit

from money.models import Event


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "event_type",
            "location_city",
            "location_address",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "location_city": forms.TextInput(attrs={"class": "form-control"}),
            "location_address": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.label_class = "fw-semibold"
        self.helper.layout = Layout(
            Row(
                Column("title", css_class="col-12 col-md-6"),
                Column("event_type", css_class="col-12 col-md-6"),
            ),
            Row(
                Column("location_city", css_class="col-12 col-md-6"),
                Column("location_address", css_class="col-12 col-md-6"),
            ),
            Row(Column("notes", css_class="col-12")),
            Submit("submit", "Save Event", css_class="btn btn-primary float-end"),
        )

    def clean(self):
        cleaned = super().clean()
        for f in ("title", "location_city", "location_address"):
            if cleaned.get(f):
                cleaned[f] = cleaned[f].strip()
        if cleaned.get("notes"):
            cleaned["notes"] = cleaned["notes"].strip()
        return cleaned

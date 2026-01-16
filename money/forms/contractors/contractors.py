# money/forms/contractors.py

from __future__ import annotations

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Fieldset, Layout, Row, Submit
from django import forms

from money.models import Contractor


class ContractorForm(forms.ModelForm):
    class Meta:
        model = Contractor
        fields = [
            "contractor_number",
            "first_name",
            "last_name",
            "business_name",
            "email",
            "phone",
            "address1",
            "address2",
            "city",
            "state",
            "zip_code",
            "entity_type",
            "tin_type",
            "tin_last4",
            "is_1099_eligible",
            "w9_status",
            "w9_sent_date",
            "w9_received_date",
            "w9_document",
            "edelivery_consent",
            "notes",
            "is_active",
        ]
        widgets = {
            "w9_sent_date": forms.DateInput(attrs={"type": "date"}),
            "w9_received_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_enctype = "multipart/form-data"

        # Mobile-first: stacked on xs, multi-column on md+
        self.helper.layout = Layout(
            Fieldset(
                "Identity",
                Row(
                    Column("contractor_number", css_class="col-12 col-md-4"),
                    Column("first_name", css_class="col-12 col-md-4"),
                    Column("last_name", css_class="col-12 col-md-4"),
                    css_class="g-3",
                ),
                Row(
                    Column("business_name", css_class="col-12"),
                    css_class="g-3",
                ),
                Row(
                    Column("email", css_class="col-12 col-md-6"),
                    Column("phone", css_class="col-12 col-md-6"),
                    css_class="g-3",
                ),
            ),
            Fieldset(
                "Mailing Address",
                Row(Column("address1", css_class="col-12"), css_class="g-3"),
                Row(Column("address2", css_class="col-12"), css_class="g-3"),
                Row(
                    Column("city", css_class="col-12 col-md-5"),
                    Column("state", css_class="col-6 col-md-2"),
                    Column("zip_code", css_class="col-6 col-md-3"),
                    css_class="g-3",
                ),
            ),
            Fieldset(
                "Tax Classification",
                Row(
                    Column("entity_type", css_class="col-12 col-md-6"),
                    Column("tin_type", css_class="col-6 col-md-3"),
                    Column("tin_last4", css_class="col-6 col-md-3"),
                    css_class="g-3",
                ),
                Row(
                    Column("is_1099_eligible", css_class="col-12 col-md-4"),
                    Column("edelivery_consent", css_class="col-12 col-md-8"),
                    css_class="g-3",
                ),
            ),
            Fieldset(
                "W-9",
                Row(
                    Column("w9_status", css_class="col-12 col-md-4"),
                    Column("w9_sent_date", css_class="col-6 col-md-4"),
                    Column("w9_received_date", css_class="col-6 col-md-4"),
                    css_class="g-3",
                ),
                Row(Column("w9_document", css_class="col-12"), css_class="g-3"),
            ),
            Fieldset(
                "Notes & Status",
                Row(Column("notes", css_class="col-12"), css_class="g-3"),
                Row(Column("is_active", css_class="col-12"), css_class="g-3"),
            ),
        )

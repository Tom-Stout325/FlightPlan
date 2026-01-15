# money/forms/company_profiles.py
from __future__ import annotations

from django import forms
from django.db import transaction
from django.utils.text import slugify

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, Layout, Submit
from crispy_forms.bootstrap import FormActions

from ...models import CompanyProfile


class CompanyProfileForm(forms.ModelForm):
    """
    Crispy + safe activation behavior:
    If this profile is saved as active, deactivate any other active profiles.
    """

    class Meta:
        model = CompanyProfile
        fields = [
            "slug",
            "legal_name",
            "display_name",
            "logo",
            "logo_light",
            "logo_dark",
            "logo_alt_text",
            "brand_color_primary",
            "brand_color_secondary",
            "website",
            "address_line1",
            "address_line2",
            "city",
            "state_province",
            "postal_code",
            "country",
            "main_phone",
            "support_email",
            "invoice_reply_to_email",
            "billing_contact_name",
            "billing_contact_email",
            "tax_id_ein",
            "vehicle_expense_method",
            "pay_to_name",
            "remittance_address",
            "default_terms",
            "default_net_days",
            "default_late_fee_policy",
            "default_footer_text",
            "pdf_header_layout",
            "header_logo_max_width_px",
            "default_currency",
            "default_locale",
            "timezone",
            "is_active",
        ]
        widgets = {
            "remittance_address": forms.Textarea(attrs={"rows": 3}),
            "default_footer_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = True
        self.helper.attrs = {"enctype": "multipart/form-data"}

        # Mobile-first: stacked, then becomes 2-column at md+
        self.helper.layout = Layout(
            Div(
                Div(Field("slug"), css_class="col-12 col-md-6"),
                Div(Field("is_active"), css_class="col-12 col-md-6"),
                css_class="row g-3",
            ),
            Div(
                Div(Field("legal_name"), css_class="col-12 col-md-6"),
                Div(Field("display_name"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("logo"), css_class="col-12 col-md-4"),
                Div(Field("logo_light"), css_class="col-12 col-md-4"),
                Div(Field("logo_dark"), css_class="col-12 col-md-4"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("logo_alt_text"), css_class="col-12 col-md-6"),
                Div(Field("website"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("brand_color_primary"), css_class="col-12 col-md-6"),
                Div(Field("brand_color_secondary"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(css_class="my-2"),

            Div(
                Div(Field("address_line1"), css_class="col-12 col-md-6"),
                Div(Field("address_line2"), css_class="col-12 col-md-6"),
                css_class="row g-3",
            ),
            Div(
                Div(Field("city"), css_class="col-12 col-md-4"),
                Div(Field("state_province"), css_class="col-12 col-md-4"),
                Div(Field("postal_code"), css_class="col-12 col-md-4"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("country"), css_class="col-12 col-md-6"),
                Div(Field("main_phone"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("support_email"), css_class="col-12 col-md-6"),
                Div(Field("invoice_reply_to_email"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("billing_contact_name"), css_class="col-12 col-md-6"),
                Div(Field("billing_contact_email"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("tax_id_ein"), css_class="col-12 col-md-6"),
                Div(Field("vehicle_expense_method"), css_class="col-12 col-md-6"),
                css_class="row g-3 mt-0",
            ),
            Div(css_class="my-2"),

            Div(
                Div(Field("pay_to_name"), css_class="col-12 col-md-6"),
                Div(Field("default_terms"), css_class="col-12 col-md-3"),
                Div(Field("default_net_days"), css_class="col-12 col-md-3"),
                css_class="row g-3",
            ),
            Div(
                Div(Field("remittance_address"), css_class="col-12"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("default_late_fee_policy"), css_class="col-12"),
                css_class="row g-3 mt-0",
            ),
            Div(
                Div(Field("default_footer_text"), css_class="col-12"),
                css_class="row g-3 mt-0",
            ),
            Div(css_class="my-2"),

            Div(
                Div(Field("pdf_header_layout"), css_class="col-12 col-md-6"),
                Div(Field("header_logo_max_width_px"), css_class="col-12 col-md-6"),
                css_class="row g-3",
            ),
            Div(
                Div(Field("default_currency"), css_class="col-12 col-md-4"),
                Div(Field("default_locale"), css_class="col-12 col-md-4"),
                Div(Field("timezone"), css_class="col-12 col-md-4"),
                css_class="row g-3 mt-0",
            ),

            FormActions(
                Submit("save", "Save", css_class="btn btn-primary"),
                css_class="mt-3",
            ),
        )

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        if not slug:
            raise forms.ValidationError("Slug is required.")
        return slugify(slug)

    def save(self, commit: bool = True):
        instance: CompanyProfile = super().save(commit=False)

        if commit:
            with transaction.atomic():
                if instance.is_active:
                    (
                        CompanyProfile.objects
                        .filter(is_active=True)
                        .exclude(pk=instance.pk)
                        .update(is_active=False)
                    )
                # model.clean() enforces required fields when active
                instance.full_clean()
                instance.save()
                self.save_m2m()
        return instance

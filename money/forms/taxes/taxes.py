from django import forms

from ...models import *


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['category'] 
        widgets = {
            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name'
            }),
        }


class SubCategoryForm(forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = ['sub_cat', 'category'] 
        widgets = {
            'sub_cat': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter sub-category name'
            }),
            'category': forms.Select(attrs={
                'class': 'form-control'
            }),
        }






class MileageForm(forms.ModelForm):
    class Meta:
        model = Miles
        # user + total are still managed in view/model, not edited directly
        fields = [
            "date",
            "begin",
            "end",
            "client",
            "event",
            "invoice_v2",     # NEW: FK to InvoiceV2
            "invoice_number", # legacy string, usually mirrors invoice_v2.invoice_number
            "vehicle",
            "mileage_type",
        ]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "begin": forms.NumberInput(
                attrs={"step": "0.1", "class": "form-control"}
            ),
            "end": forms.NumberInput(
                attrs={"step": "0.1", "class": "form-control"}
            ),
            "client": forms.Select(
                attrs={"class": "form-control"}
            ),
            "event": forms.Select(
                attrs={"class": "form-control"}
            ),
            "invoice_v2": forms.Select(
                attrs={"class": "form-control"}
            ),
            "invoice_number": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "vehicle": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "mileage_type": forms.Select(
                attrs={"class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Order invoices nicely in the dropdown; you can later filter by client/year if you want
        if "invoice_v2" in self.fields:
            self.fields["invoice_v2"].queryset = (
                InvoiceV2.objects.order_by("-date", "-invoice_number")
            )

    def save(self, commit=True):
        """
        - Auto-calc total if begin/end are provided and total is empty.
        - If linked to an InvoiceV2 and invoice_number is blank, mirror the invoice's number.
        """
        obj: Miles = super().save(commit=False)

        # Mirror invoice_number from InvoiceV2 if not manually set
        if obj.invoice_v2 and not obj.invoice_number:
            obj.invoice_number = obj.invoice_v2.invoice_number

        # Auto-calc total miles if begin/end present and total is empty
        if obj.begin is not None and obj.end is not None and obj.total is None:
            obj.total = obj.end - obj.begin

        if commit:
            obj.save()
            self.save_m2m()
        return obj


class MileageRateForm(forms.ModelForm):
    class Meta:
        model = MileageRate
        fields = ["rate"]
        widgets = {
            "rate": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
        }

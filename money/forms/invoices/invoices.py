from django import forms
from django.forms import inlineformset_factory

from ...models import *



class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        exclude = [
            "amount",  
            "from_name",
            "from_address",
            "from_phone",
            "from_email",
            "from_website",
            "from_tax_id",
            "from_logo_url",
            "from_header_logo_max_width_px",
            "from_terms",
            "from_net_days",
            "from_footer_text",
            "from_currency",
            "from_locale",
            "from_timezone",
            "issued_at",
            "version",
            "pdf_url",
            "pdf_sha256",
        ]
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-select'}),
            'event': forms.Select(attrs={'class': 'form-select'}),
            'service': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'paid_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }




class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['description', 'qty', 'price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_qty(self):
        qty = self.cleaned_data.get('qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be greater than 0.")
        return qty

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price



InvoiceItemFormSet = inlineformset_factory(
    parent_model=Invoice,
    model=InvoiceItem,
    form=InvoiceItemForm,
    extra=2,  # Show 2 blank forms by default
    can_delete=True
)














class InvoiceV2Form(forms.ModelForm):
    class Meta:
        model = InvoiceV2
        # amount/invoice_number are handled by model logic
        fields = [
            "client",
            "event",
            "event_name",
            "location",
            "service",
            "date",
            "due",
            "status",
            "paid_date",
        ]
        widgets = {
            "client": forms.Select(attrs={"class": "form-select"}),
            "event": forms.Select(attrs={"class": "form-select"}),
            "service": forms.Select(attrs={"class": "form-select"}),
            "event_name": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "due": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "paid_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }



class InvoiceItemV2Form(forms.ModelForm):
    class Meta:
        model = InvoiceItemV2
        fields = ["description", "qty", "price", "sub_cat"]
        widgets = {
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Description"}),
            "qty": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "sub_cat": forms.Select(attrs={"class": "form-select"}),
        }


InvoiceItemV2FormSet = inlineformset_factory(
    InvoiceV2,
    InvoiceItemV2,
    form=InvoiceItemV2Form,
    extra=1,
    can_delete=True,
)

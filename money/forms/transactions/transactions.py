from django import forms
from django.core.exceptions import ValidationError

from ...models import *


class TransForm(forms.ModelForm):
    invoice_number = forms.CharField(
        label="Invoice Number (Optional)",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    event = forms.ModelChoiceField(
        queryset=Event.objects.order_by('title'),
        label='Event',
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )

    sub_cat = forms.ModelChoiceField(
        queryset=SubCategory.objects.all().order_by('category__category', 'sub_cat'),
        label='Sub-Category',
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = Transaction
        fields = (
            'invoice_number', 'date', 'trans_type', 'sub_cat', 'amount',
            'team', 'transaction', 'receipt', 'transport_type', 'event'
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'transport_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_receipt(self):
        receipt = self.cleaned_data.get('receipt')
        if receipt and hasattr(receipt, 'content_type'):
            if receipt.content_type not in ['application/pdf', 'image/jpeg', 'image/png']:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return receipt

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('sub_cat'):
            cleaned_data['category'] = cleaned_data['sub_cat'].category
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.sub_cat:
            instance.category = instance.sub_cat.category
        if commit:
            instance.save()
        return instance






class RecurringTransactionForm(forms.ModelForm):
    class Meta:
        model = RecurringTransaction
        fields = [
            'trans_type', 'sub_cat', 'amount', 'transaction', 'day',
            'team', 'event', 'receipt', 'active'
        ]

    def clean(self):
        cleaned = super().clean()
        sub_cat = cleaned.get('sub_cat')
        category = cleaned.get('category')
        if sub_cat:
            cleaned['category'] = sub_cat.category
        elif not category:
            raise forms.ValidationError("Select either a Sub-Category or a Category.")
        return cleaned



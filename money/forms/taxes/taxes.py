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
        exclude = ['user', 'total']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'begin': forms.NumberInput(attrs={'step': '0.1', 'class': 'form-control'}),
            'end': forms.NumberInput(attrs={'step': '0.1', 'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}), 
            'event': forms.Select(attrs={'class': 'form-control'}), 
            'vehicle': forms.TextInput(attrs={'class': 'form-control'}),
            'mileage_type': forms.Select(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['invoice_number'].queryset = Invoice.objects.order_by('-date')



class MileageRateForm(forms.ModelForm):
    class Meta:
        model = MileageRate
        fields = ['rate']
        widgets = {
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


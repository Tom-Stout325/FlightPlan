from django import forms


from ...models import (
        Category, 
        SubCategory, 
        Miles, 
        MileageRate, 
        Vehicle, 
        InvoiceV2,
)





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
        fields = [
            "date",
            "begin",
            "end",
            "client",
            "event",
            "invoice_v2",
            "invoice_number",
            "vehicle",
            "mileage_type",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "begin": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
            "end": forms.NumberInput(attrs={"step": "0.1", "class": "form-control"}),
            "client": forms.Select(attrs={"class": "form-control"}),
            "event": forms.Select(attrs={"class": "form-control"}),
            "invoice_v2": forms.Select(attrs={"class": "form-control"}),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "vehicle": forms.Select(attrs={"class": "form-control"}),
            "mileage_type": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user and "vehicle" in self.fields:
            self.fields["vehicle"].queryset = Vehicle.objects.filter(user=user, is_active=True).order_by("-is_active", "name")

        if "invoice_v2" in self.fields:
            self.fields["invoice_v2"].queryset = InvoiceV2.objects.order_by("-date", "-invoice_number")

    def save(self, commit=True):
        obj: Miles = super().save(commit=False)

        if obj.invoice_v2 and not obj.invoice_number:
            obj.invoice_number = obj.invoice_v2.invoice_number

        if obj.begin is not None and obj.end is not None:
            obj.total = obj.end - obj.begin
        else:
            obj.total = None

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

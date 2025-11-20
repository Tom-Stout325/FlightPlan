from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row, Submit
from django import forms

from ...models import *



class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            'title',
            'event_type',
            'location_city',
            'location_address',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.label_class = 'fw-semibold'
        self.helper.layout = Layout(
            Row(
                Column('title', css_class='col-md-6'),
                Column('event_type', css_class='col-md-6'),
            ),
            Row(
                Column('location_city', css_class='col-md-6'),
                Column('location_address', css_class='col-md-6'),
            ),
            Row(
            'notes',
            ),
            Submit('submit', 'Save Event', css_class='btn btn-primary float-end')
        )
from django import forms

from ...models import *




class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['business', 'first', 'last', 'street', 'address2', 'email', 'phone']


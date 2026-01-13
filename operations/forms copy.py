from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import OpsPlan




class OpsPlanForm(forms.ModelForm):
    class Meta:
        model = OpsPlan
        fields = [
            "event_name", "plan_year", "start_date", "end_date",
            "client", "address", "pilot_in_command", "visual_observers",
            "airspace_class", "waivers_required", "airport", "airport_phone",
            "notes", "emergency_procedures",
            "waiver", "location_map",
            "client_approval", "client_approval_notes",
        ]

        widgets = {
            "event_name": forms.TextInput(),
            "plan_year": forms.NumberInput(attrs={"min": 2000, "max": 2100, "step": 1}),
            "start_date": forms.DateInput(attrs={"type": "date"}),  # browser posts YYYY-MM-DD
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "client": forms.Select(),
            "address": forms.TextInput(),
            "pilot_in_command": forms.TextInput(),
            "visual_observers": forms.TextInput(),
            "airspace_class": forms.TextInput(),
            "waivers_required": forms.CheckboxInput(),
            "airport": forms.TextInput(),
            "airport_phone": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "emergency_procedures": forms.Textarea(attrs={"rows": 3}),
            "client_approval_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self._bound_event = kwargs.pop("event", None)
        self._bound_user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["start_date"].input_formats = ["%Y-%m-%d", "%m/%d/%Y"] 
        self.fields["end_date"].input_formats   = ["%Y-%m-%d", "%m/%d/%Y"]

        if self._bound_event is not None:
            self.instance.event = self._bound_event
            if not self.initial.get("event_name") and not getattr(self.instance, "event_name", None):
                event_title = getattr(self._bound_event, "title", None) or getattr(self._bound_event, "name", None)
                self.initial["event_name"] = event_title or str(self._bound_event)
            if not self.initial.get("client") and not getattr(self.instance, "client_id", None):
                if getattr(self._bound_event, "client_id", None):
                    self.initial["client"] = self._bound_event.client_id

        if not self.instance.pk and not self.initial.get("plan_year"):
            event_year = getattr(self._bound_event, "event_year", None)
            self.initial["plan_year"] = event_year or timezone.now().year

    def clean_plan_year(self):
        year = self.cleaned_data.get("plan_year")
        if not year:
            raise ValidationError("Plan year is required.")
        if year < 2000 or year > 2100:
            raise ValidationError("Please enter a valid year between 2000 and 2100.")
        return year

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be after the start date.")
            
        event_obj = self._bound_event or getattr(self.instance, "event", None)
        plan_year = cleaned.get("plan_year")
        if event_obj and plan_year:
            qs = OpsPlan.objects.filter(event=event_obj, plan_year=plan_year)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("plan_year", f"An Ops Plan for '{event_obj}' already exists for {plan_year}.")
        return cleaned



class OpsPlanApprovalForm(forms.Form):
    approve = forms.BooleanField(
        label="I have reviewed and approve this Operations Plan.",
        required=True
    )
    full_name = forms.CharField(
        label="Full Name (Digital Signature)",
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )


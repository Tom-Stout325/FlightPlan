# money/views/events.py

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.utils import timezone

from money.forms.events.events import EventCreateForm, EventUpdateForm
from money.models import Event

logger = logging.getLogger(__name__)



class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = "money/events/event_list.html"
    context_object_name = "events"
    paginate_by = 25

    def _selected_year(self) -> int:
        current_year = timezone.localdate().year
        try:
            return int(self.request.GET.get("year") or current_year)
        except (TypeError, ValueError):
            return current_year

    def _query(self) -> str:
        return (self.request.GET.get("q") or "").strip()

    def get_queryset(self):
        selected_year = self._selected_year()
        query = self._query()

        qs = Event.objects.filter(user=self.request.user, event_year=selected_year)

        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(location_city__icontains=query)
                | Q(location_address__icontains=query)
                | Q(job_number__icontains=query)  # helpful when people paste the number
            )

        # New ordering: year-specific + job_number first
        # job_number can be NULL for historical rows initially; title is the tie-breaker.
        return qs.order_by("job_number", "title")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        current_year = timezone.localdate().year
        selected_year = self._selected_year()
        query = self._query()

        years_qs = (
            Event.objects.filter(user=self.request.user)
            .values_list("event_year", flat=True)
            .distinct()
            .order_by("-event_year")
        )
        years = list(years_qs)

        # Ensure current year is always present in the dropdown
        if current_year not in years:
            years.insert(0, current_year)

        context.update(
            {
                "current_page": "events",
                "query": query,
                "years": years,
                "selected_year": selected_year,
            }
        )
        return context


class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventCreateForm
    template_name = "money/events/event_form.html"
    success_url = reverse_lazy("money:event_list")

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Ownership must be set before save/full_clean
        form.instance.user = self.request.user
        messages.success(self.request, "Job added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "events"
        context["is_create"] = True
        return context


class EventUpdateView(LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventUpdateForm
    template_name = "money/events/event_form.html"
    success_url = reverse_lazy("money:event_list")

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Keep ownership consistent
        form.instance.user = self.request.user
        messages.success(self.request, "Job updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "events"
        context["is_create"] = False
        return context



class EventDetailView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = "money/events/event_detail.html"
    context_object_name = "event"

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "events"
        return context


class EventDeleteView(LoginRequiredMixin, DeleteView):
    model = Event
    template_name = "money/events/event_confirm_delete.html"
    success_url = reverse_lazy("money:event_list")

    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Event deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "events"
        return context

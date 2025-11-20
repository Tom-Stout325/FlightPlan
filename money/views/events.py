import logging

logger = logging.getLogger(__name__)
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)
from ..forms.events.events import (
    EventForm,
)
from ..models import *




# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->            E V E N T S 


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = 'money/events/event_list.html'
    context_object_name = 'events'
    paginate_by = 25

    def get_queryset(self):
        queryset = Event.objects.all().order_by('title')
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(location_city__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        context['query'] = self.request.GET.get('q', '')
        return context



class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = 'money/events/event_form.html'
    success_url = reverse_lazy('event_list')

    def form_valid(self, form):
        messages.success(self.request, "event added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context


class EventUpdateView(LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'money/events/event_form.html'
    success_url = reverse_lazy('money:event_list')

    def form_valid(self, form):
        messages.success(self.request, "Event updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context
    

class EventDetailView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'money/events/event_detail.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context



class EventDeleteView(LoginRequiredMixin, DeleteView):
    model = Event
    template_name = 'money/events/event_confirm_delete.html'
    success_url = reverse_lazy('money:event_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Event deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context




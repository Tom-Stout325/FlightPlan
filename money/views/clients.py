import logging

logger = logging.getLogger(__name__)

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from money.forms.clients.clients import ClientForm

from ..models import Client





class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = "money/clients/client_list.html"
    context_object_name = "clients"
    ordering = ['business']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context



class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "money/clients/client_form.html"
    success_url = reverse_lazy('money:client_list')

    def form_valid(self, form):
        messages.success(self.request, "Client added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context



class ClientUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "money/clients/client_form.html"
    success_url = reverse_lazy('money:client_list')

    def form_valid(self, form):
        messages.success(self.request, "Client updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context



class ClientDeleteView(LoginRequiredMixin, DeleteView):
    model = Client
    template_name = "money/clients/client_confirm_delete.html"
    success_url = reverse_lazy('money:client_list')

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Client deleted successfully!")
            return response
        except ProtectedError:
            messages.error(self.request, "Cannot delete client due to related invoices.")
            return redirect('money:client_list')

        except Exception as e:
            logger.error(f"Error deleting client for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting client.")
            return redirect('money:client_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context


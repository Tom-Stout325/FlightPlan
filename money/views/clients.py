# money/views/clients.py

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from money.forms.clients.clients import ClientForm
from money.models import Client

logger = logging.getLogger(__name__)


class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = "money/clients/client_list.html"
    context_object_name = "clients"
    ordering = ["business", "last", "first"]

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user).order_by(*self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "clients"
        return context


class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "money/clients/client_form.html"
    success_url = reverse_lazy("money:client_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.user = self.request.user
        obj.save()
        messages.success(self.request, "Client added successfully!")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "clients"
        return context


class ClientUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "money/clients/client_form.html"
    success_url = reverse_lazy("money:client_list")

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Client updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "clients"
        return context


class ClientDeleteView(LoginRequiredMixin, DeleteView):
    model = Client
    template_name = "money/clients/client_confirm_delete.html"
    success_url = reverse_lazy("money:client_list")

    def get_queryset(self):
        return Client.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Client deleted successfully!")
            return response
        except ProtectedError:
            messages.error(self.request, "Cannot delete client due to related invoices.")
            return redirect("money:client_list")
        except Exception as e:
            logger.exception("Error deleting client for user %s: %s", request.user.id, e)
            messages.error(self.request, "Error deleting client.")
            return redirect("money:client_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "clients"
        return context

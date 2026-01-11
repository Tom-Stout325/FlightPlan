# _FLIGHTPLAN/money/views/dashboard.py

from __future__ import annotations

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


class Dashboard(LoginRequiredMixin, TemplateView):
    template_name = "money/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "dashboard"
        return context

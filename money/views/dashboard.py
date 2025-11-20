import logging

logger = logging.getLogger(__name__)

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from ..forms import *
from ..models import *




class Dashboard(LoginRequiredMixin, TemplateView):
    template_name = "money/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'dashboard'
        return context
    
    
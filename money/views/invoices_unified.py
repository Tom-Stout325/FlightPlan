# money/views/invoices_unified.py

from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views import View

from ..models import InvoiceV2, Client
from ..unified_invoices import (
    load_v2_invoices,
    load_legacy_model_invoices,
    load_legacy_files,
)


class InvoiceUnifiedListView(LoginRequiredMixin, View):
    """
    Unified invoice list:

    - InvoiceV2 records (new system)
    - Legacy Invoice DB records
    - Legacy PDF-only files
    """

    template_name = "money/invoices/invoice_v2_list.html"
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        # ------------------------------------------------------------------
        # 1) Load ALL sources (V2 + legacy DB + legacy file PDFs)
        # ------------------------------------------------------------------
        rows = []
        rows.extend(load_v2_invoices(request))
        rows.extend(load_legacy_model_invoices(request))
        rows.extend(load_legacy_files(request))

        # ------------------------------------------------------------------
        # 2) Filters from query params
        # ------------------------------------------------------------------
        status = request.GET.get("status") or ""
        year_str = request.GET.get("year") or ""
        client_str = request.GET.get("client") or ""

        # Status filter (only if provided)
        if status:
            rows = [
                r for r in rows
                if (r.status == status)
            ]

        # Year filter (by issue_date.year)
        if year_str:
            try:
                year_val = int(year_str)
            except ValueError:
                year_val = None

            if year_val:
                rows = [
                    r for r in rows
                    if r.issue_date and r.issue_date.year == year_val
                ]

        # Client filter – using client_name as normalised display
        if client_str:
            try:
                client_id = int(client_str)
            except ValueError:
                client_id = None

            if client_id:
                try:
                    client_obj = Client.objects.get(pk=client_id)
                    target_name = client_obj.business or str(client_obj)
                except Client.DoesNotExist:
                    target_name = None

                if target_name:
                    rows = [
                        r for r in rows
                        if r.client_name == target_name
                    ]

        # ------------------------------------------------------------------
        # 3) Sort rows: newest issue_date first, then by id
        # ------------------------------------------------------------------
        rows.sort(
            key=lambda r: (
                r.issue_date or date.min,
                r.id,
            ),
            reverse=True,
        )

        # ------------------------------------------------------------------
        # 4) Pagination
        # ------------------------------------------------------------------
        paginator = Paginator(rows, self.paginate_by)
        page_number = request.GET.get("page") or 1
        page_obj = paginator.get_page(page_number)

        # ------------------------------------------------------------------
        # 5) Build filter options for the UI
        # ------------------------------------------------------------------
        # Years from InvoiceV2 dates (to keep things simple)
        v2_years = (
            InvoiceV2.objects
            .order_by()
            .values_list("date__year", flat=True)
            .distinct()
        )
        years = sorted(set(y for y in v2_years if y))

        # Clients from the Client model
        clients = Client.objects.all().order_by("business")

        context = {
            # data
            "invoices": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": page_obj.has_other_pages(),

            # filters
            "status_choices": InvoiceV2.STATUS_CHOICES,
            "selected_status": status,
            "selected_year": year_str,
            "selected_client": client_str,
            "years": years,
            "clients": clients,
        }

        return render(request, self.template_name, context)

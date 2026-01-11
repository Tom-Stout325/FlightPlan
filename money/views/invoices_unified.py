# money/views/invoices_unified.py

from __future__ import annotations

from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views import View

from ..models import Client, InvoiceV2
from ..unified_invoices import (
    load_legacy_files,
    load_legacy_model_invoices,
    load_v2_invoices,
)


class InvoiceUnifiedListView(LoginRequiredMixin, View):
    """
    Unified invoice list (per-user):
      - InvoiceV2 records (new system)
      - Legacy Invoice DB records
      - Legacy PDF-only files
    """

    template_name = "money/invoices/invoice_v2_list.html"
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        # ------------------------------------------------------------------
        # 1) Load ALL sources (ensure loaders are user-scoped)
        # ------------------------------------------------------------------
        rows = []
        rows.extend(load_v2_invoices(user=request.user))
        rows.extend(load_legacy_model_invoices(request))  # must scope internally
        rows.extend(load_legacy_files(request))           # must scope internally

        # ------------------------------------------------------------------
        # 2) Filters from query params
        # ------------------------------------------------------------------
        status = (request.GET.get("status") or "").strip()
        year_str = (request.GET.get("year") or "").strip()
        client_str = (request.GET.get("client") or "").strip()

        # Status filter (exact match)
        if status:
            rows = [r for r in rows if (getattr(r, "status", "") == status)]

        # Year filter (by issue_date.year)
        year_val = None
        if year_str.isdigit():
            year_val = int(year_str)

        if year_val:
            rows = [
                r for r in rows
                if getattr(r, "issue_date", None) and r.issue_date.year == year_val
            ]

        # Client filter
        # IMPORTANT: client lookup must be user-scoped
        target_name = None
        if client_str.isdigit():
            client_id = int(client_str)
            client_obj = Client.objects.filter(user=request.user, pk=client_id).first()
            if client_obj:
                # Use the same display name your unified rows use for client_name
                target_name = (client_obj.business or str(client_obj) or "").strip()

        if target_name:
            rows = [r for r in rows if (getattr(r, "client_name", "").strip() == target_name)]

        # ------------------------------------------------------------------
        # 3) Sort rows: newest issue_date first, then by id
        # ------------------------------------------------------------------
        rows.sort(
            key=lambda r: (
                getattr(r, "issue_date", None) or date.min,
                getattr(r, "id", 0) or 0,
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
        # 5) Build filter options for the UI (SCOPED)
        # ------------------------------------------------------------------
        v2_years = (
            InvoiceV2.objects
            .filter(user=request.user)
            .order_by()
            .values_list("date__year", flat=True)
            .distinct()
        )
        years = sorted({y for y in v2_years if y})

        clients = Client.objects.filter(user=request.user).order_by("business")

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

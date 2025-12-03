# money/views/invoices_legacy.py

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views import View

from money.models import Invoice  # legacy Invoice model


class LegacyInvoiceDetailView(LoginRequiredMixin, View):
    """
    Read-only detail page for legacy invoices stored in the old Invoice model.

    URL name:  money:legacy_invoice_detail
    Template:  money/invoices/legacy_invoice_detail.html
    """
    template_name = "money/invoices/legacy_invoice_detail.html"

    def get(self, request, pk, *args, **kwargs):
        legacy = get_object_or_404(
            Invoice.objects.select_related("client", "event"),
            pk=pk,
        )

        # Prefer issue_date if it exists, fall back to date
        issue_date = getattr(legacy, "issue_date", None) or getattr(legacy, "date", None)

        # Prefer total_amount if present, fall back to amount
        total_amount = getattr(legacy, "total_amount", None) or getattr(legacy, "amount", None)

        # If you later add a PDF field to the legacy model, plug it in here
        pdf_url = None

        context = {
            "invoice": legacy,
            "legacy_issue_date": issue_date,
            "legacy_total_amount": total_amount,
            "legacy_pdf_url": pdf_url,
        }
        return render(request, self.template_name, context)


class LegacyFileInvoiceDetailView(LoginRequiredMixin, View):
    """
    Read-only detail page for legacy *PDF-only* invoices that do not
    have a DB record.

    URL name:  money:legacy_file_invoice_detail
    Template:  money/invoices/legacy_file_invoice_detail.html
    """
    template_name = "money/invoices/legacy_file_invoice_detail.html"

    def get(self, request, filename, *args, **kwargs):
        legacy_dir = getattr(settings, "LEGACY_INVOICE_DIR", "legacy_invoices/")

        # Safety: only allow paths within the configured legacy directory
        if not filename.startswith(legacy_dir):
            raise Http404("Invalid legacy invoice path")

        if not default_storage.exists(filename):
            raise Http404("Legacy invoice not found")

        pdf_url = default_storage.url(filename)
        base_name = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        context = {
            "invoice_number": base_name,
            "pdf_url": pdf_url,
        }
        return render(request, self.template_name, context)

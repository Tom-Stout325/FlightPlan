from __future__ import annotations
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector
from django.db.models import Value

from django.db import transaction
from money.models import InvoiceItemV2, InvoiceV2
from money.services.invoice_pdf import generate_invoice_pdf


def _regen_pdf_on_commit(invoice_id: int):
    def _cb():
        invoice = InvoiceV2.objects.filter(pk=invoice_id).first()
        if not invoice:
            return
        # Force regen to keep PDF consistent with the latest state
        generate_invoice_pdf(invoice, force=True)
    transaction.on_commit(_cb)


@receiver(post_save, sender=InvoiceItemV2)
def invoice_item_v2_saved(sender, instance: InvoiceItemV2, **kwargs):
    # Item save already updates invoice amount in your model,
    # so regenerate PDF once the transaction commits.
    if getattr(instance, "_skip_pdf_regen", False):
        return
    if instance.invoice_id:
        _regen_pdf_on_commit(instance.invoice_id)


@receiver(post_delete, sender=InvoiceItemV2)
def invoice_item_v2_deleted(sender, instance: InvoiceItemV2, **kwargs):
    if getattr(instance, "_skip_pdf_regen", False):
        return
    if instance.invoice_id:
        _regen_pdf_on_commit(instance.invoice_id)


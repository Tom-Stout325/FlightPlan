# # money/migrations/00xx_backfill_miles_invoice_v2.py
# from django.db import migrations

# def link_miles_to_invoice_v2(apps, schema_editor):
#     Miles = apps.get_model("money", "Miles")
#     InvoiceV2 = apps.get_model("money", "InvoiceV2")

#     # Only rows that don't already have invoice_v2 but DO have an invoice_number
#     qs = Miles.objects.exclude(invoice_number__isnull=True).exclude(invoice_number="").filter(invoice_v2__isnull=True)

#     for miles in qs.iterator():
#         inv = InvoiceV2.objects.filter(invoice_number=miles.invoice_number).first()
#         if inv:
#             miles.invoice_v2 = inv
#             miles.save(update_fields=["invoice_v2"])

# class Migration(migrations.Migration):
#     dependencies = [
#         ("money", "00xx_add_invoice_v2_fk_to_miles"),  # your schema migration
#     ]

#     operations = [
#         migrations.RunPython(link_miles_to_invoice_v2, migrations.RunPython.noop),
#     ]

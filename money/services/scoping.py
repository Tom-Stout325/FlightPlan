# money/services/scoping.py
from money.models import InvoiceV2, Client

def user_clients(user):
    return Client.objects.filter(user=user)

def user_invoices_v2(user):
    return InvoiceV2.objects.filter(client__user=user)

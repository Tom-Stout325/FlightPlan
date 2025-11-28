import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from money.models import (
    Transaction,
    Invoice,
    SubCategory,
    Client,
    Service,
    Category,
    Team,
    Event,
)


class Command(BaseCommand):
    help = "Seed local dev database with demo invoices and transactions."

    # SubCategory IDs from your screenshot
    SUBCAT_IDS = list(range(3, 31))  # 3–30 inclusive

    def handle(self, *args, **options):
        User = get_user_model()

        # --- Use your existing user 'tomstout' ---
        try:
            user = User.objects.get(username="tomstout")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("User 'tomstout' not found."))
            return

        # --- Required base objects for Invoice / Transaction ---
        client = Client.objects.first()
        service = Service.objects.first()
        event = Event.objects.first()
        category = Category.objects.first()
        team = Team.objects.first()  # optional

        if not client:
            self.stdout.write(self.style.ERROR("No Client found. Create at least one Client first."))
            return
        if not service:
            self.stdout.write(self.style.ERROR("No Service found. Create at least one Service first."))
            return
        if not event:
            self.stdout.write(self.style.ERROR("No Event found. Create at least one Event first."))
            return
        if not category:
            self.stdout.write(self.style.ERROR("No Category found. Create at least one Category first."))
            return

        subcats = list(SubCategory.objects.filter(id__in=self.SUBCAT_IDS))
        if not subcats:
            self.stdout.write(self.style.ERROR("No SubCategory records found for IDs 3–30."))
            return

        today = timezone.now().date()

        # ------------------------------------------------------------------
        # 1) Create 10 invoices
        # ------------------------------------------------------------------
        invoices = []
        for i in range(1, 11):
            inv_number = f"DEV-{today.year}-{i:03d}"

            invoice_date = today - timedelta(days=random.randint(0, 60))
            due_date = invoice_date + timedelta(days=30)

            invoice, created = Invoice.objects.get_or_create(
                invoice_number=inv_number,
                defaults={
                    "client": client,
                    "event": event,
                    "service": service,
                    "date": invoice_date,
                    "due": due_date,
                    "status": "Unpaid",
                    "event_name": f"Dev Event {i}",
                    "location": "Dev Location",
                    # from_* snapshot fields can stay blank; defaults are fine for dev seed
                },
            )
            invoices.append(invoice)

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created invoice {inv_number}"))
            else:
                self.stdout.write(self.style.WARNING(f"Using existing invoice {inv_number}"))

        # ------------------------------------------------------------------
        # 2) Create 50 transactions
        # ------------------------------------------------------------------
        self.stdout.write("Creating 50 dev transactions...")

        for i in range(1, 51):
            subcat = random.choice(subcats)

            tx_date = today - timedelta(days=random.randint(0, 180))
            amount = (
                Decimal(random.randint(20, 750))
                + (Decimal(random.randint(0, 99)) / Decimal("100"))
            )

            # ~75% of transactions will NOT be tied to an invoice
            invoice = random.choice(invoices + [None, None, None])

            tx = Transaction.objects.create(
                user=user,
                trans_type=Transaction.EXPENSE,  # all expenses for this seed
                category=category,
                sub_cat=subcat,
                amount=amount,
                transaction=f"DEV seed transaction #{i} - {subcat.sub_cat}",
                team=team if team else None,
                event=invoice.event if invoice else event,
                date=tx_date,
                invoice_number=invoice.invoice_number if invoice else None,
            )

            self.stdout.write(
                f"Transaction {tx.id}: {tx.date} | {subcat.sub_cat} | "
                f"${amount} {'-> ' + invoice.invoice_number if invoice else ''}"
            )

        self.stdout.write(self.style.SUCCESS("\n✔ Seed complete: 10 invoices + 50 transactions.\n"))

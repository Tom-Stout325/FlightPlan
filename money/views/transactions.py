# money/views/transactions.py

from __future__ import annotations

import csv
import logging
from calendar import month_name, monthrange
from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction as db_tx
from django.db.models import Q, Sum
from django.db.models.functions import ExtractYear
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.timezone import now
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ..forms.transactions.transactions import (
    RecurringTransactionForm,
    RunRecurringForMonthForm,
    TransForm,
)
from ..models import Category, Event, RecurringTransaction, SubCategory, Transaction

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Transactions
# ------------------------------------------------------------------------------


class Transactions(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "money/transactions/transactions.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user

        qs = (
            Transaction.objects.select_related(
                "category",
                "sub_cat__category",
                "sub_cat",
                "team",
                "event",
            )
            .filter(user=user)
        )

        # Filter inputs (always scoped to the current user)
        event_id = (self.request.GET.get("event") or "").strip()
        if event_id.isdigit() and Event.objects.filter(pk=int(event_id), user=user).exists():
            qs = qs.filter(event_id=int(event_id))

        category_id = (self.request.GET.get("category") or "").strip()
        if category_id.isdigit() and Category.objects.filter(pk=int(category_id), user=user).exists():
            qs = qs.filter(category_id=int(category_id))

        sub_cat_id = (self.request.GET.get("sub_cat") or "").strip()
        if sub_cat_id.isdigit() and SubCategory.objects.filter(pk=int(sub_cat_id), user=user).exists():
            qs = qs.filter(sub_cat_id=int(sub_cat_id))

        year = (self.request.GET.get("year") or "").strip()
        if year.isdigit():
            y = int(year)
            if 1900 <= y <= 9999:
                qs = qs.filter(date__year=y)

        sort = self.request.GET.get("sort", "-date")
        valid_sort_fields = {
            "date",
            "-date",
            "trans_type",
            "-trans_type",
            "transaction",
            "-transaction",
            "event__slug",
            "-event__slug",
            "amount",
            "-amount",
            "invoice_number",
            "-invoice_number",
        }
        if sort not in valid_sort_fields:
            sort = "-date"
        self.current_sort = sort

        return qs.order_by(sort, "-pk")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        ctx["col_headers"] = [
            {"field": "date", "label": "Date"},
            {"field": "trans_type", "label": "Type"},
            {"field": "transaction", "label": "Description"},
            {"field": "event__slug", "label": "Event"},
            {"field": "amount", "label": "Amount"},
            {"field": "invoice_number", "label": "Invoice #"},
        ]

        ctx["current_sort"] = getattr(self, "current_sort", "-date")

        ctx["events"] = (
            Event.objects.filter(user=user, transactions__user=user)
            .distinct()
            .order_by("slug")
        )

        ctx["categories"] = (
            Category.objects.filter(user=user, transaction__user=user)
            .distinct()
            .order_by("category")
        )

        ctx["subcategories"] = (
            SubCategory.objects.filter(user=user, transaction__user=user)
            .distinct()
            .order_by("sub_cat")
        )

        ctx["years"] = [
            str(y)
            for y in (
                Transaction.objects.filter(user=user)
                .annotate(year=ExtractYear("date"))
                .values_list("year", flat=True)
                .distinct()
                .order_by("-year")
            )
            if y
        ]

        ctx.update(
            {
                "selected_event": self.request.GET.get("event", ""),
                "selected_category": self.request.GET.get("category", ""),
                "selected_sub_cat": self.request.GET.get("sub_cat", ""),
                "selected_year": self.request.GET.get("year", ""),
                "current_page": "transactions",
            }
        )
        return ctx


class TransactionDetailView(LoginRequiredMixin, DetailView):
    model = Transaction
    template_name = "money/transactions/transactions_detail_view.html"
    context_object_name = "transaction"

    def get_queryset(self):
        return (
            Transaction.objects.select_related(
                "category",
                "sub_cat__category",
                "sub_cat",
                "team",
                "event",
            )
            .filter(user=self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "transactions"
        return context


class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransForm
    template_name = "money/transactions/transaction_add.html"
    success_url = reverse_lazy("money:add_transaction_success")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            with db_tx.atomic():
                obj = form.save(commit=False)
                obj.user = self.request.user

                # Ensure category is always aligned with sub_cat when provided
                if obj.sub_cat_id:
                    obj.category = obj.sub_cat.category

                obj.save()
                form.save_m2m()

            messages.success(self.request, "Transaction added successfully!")
            return redirect(self.get_success_url())

        except Exception as e:
            logger.exception("Error adding transaction for user %s: %s", self.request.user.id, e)
            messages.error(self.request, "Error adding transaction. Please check the form.")
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "transactions"
        return context


class TransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransForm
    template_name = "money/transactions/transaction_edit.html"
    success_url = reverse_lazy("money:transactions")

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            with db_tx.atomic():
                obj = form.save(commit=False)
                obj.user = self.request.user  # defensive (should already be true)

                # Keep category aligned if sub_cat is selected/changed
                if obj.sub_cat_id:
                    obj.category = obj.sub_cat.category

                obj.save()
                form.save_m2m()

            messages.success(self.request, "Transaction updated successfully!")
            return redirect(self.get_success_url())

        except Exception as e:
            logger.exception(
                "Error updating transaction %s for user %s: %s",
                getattr(self.object, "id", "unknown"),
                getattr(self.request.user, "id", "anon"),
                e,
            )
            messages.error(self.request, "Error updating transaction. Please check the form.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        logger.warning(
            "TransactionUpdateView.form_invalid for user %s. Errors: %s",
            getattr(self.request.user, "id", "anon"),
            form.errors,
        )
        messages.error(self.request, "There were errors in the transaction form.")
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "transactions"

        sub_cat = getattr(self.object, "sub_cat", None)
        if sub_cat:
            context["selected_category"] = sub_cat.category

        return context


class TransactionDeleteView(LoginRequiredMixin, DeleteView):
    model = Transaction
    template_name = "money/transactions/transaction_confirm_delete.html"
    success_url = reverse_lazy("money:transactions")

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        try:
            with db_tx.atomic():
                response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Transaction deleted successfully!")
            return response
        except Exception as e:
            logger.exception("Error deleting transaction for user %s: %s", request.user.id, e)
            messages.error(self.request, "Error deleting transaction.")
            return redirect("money:transactions")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "transactions"
        return context


@login_required
def add_transaction_success(request):
    return render(
        request,
        "money/transactions/transaction_add_success.html",
        {"current_page": "transactions"},
    )


@login_required
def export_transactions_csv(request):
    """
    Export the user's transactions as CSV.

    Note: Transaction has NO FK named 'invoice' (invoice_number is a CharField),
    so we only select_related valid FKs.
    """
    transactions = (
        Transaction.objects.filter(user=request.user)
        .select_related("category", "sub_cat", "team", "event")
        .order_by("-date", "-pk")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="transactions.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Date",
            "Type",
            "Description",
            "Category",
            "SubCategory",
            "Amount",
            "Team",
            "Event",
            "Invoice Number",
        ]
    )

    for t in transactions:
        writer.writerow(
            [
                getattr(t, "date", "") or "",
                getattr(t, "trans_type", "") or "",
                getattr(t, "transaction", "") or "",
                getattr(getattr(t, "category", None), "category", "") or "",
                getattr(getattr(t, "sub_cat", None), "sub_cat", "") or "",
                getattr(t, "amount", "") or "",
                getattr(getattr(t, "team", None), "name", "") or "",
                getattr(getattr(t, "event", None), "title", "") or "",
                getattr(t, "invoice_number", "") or "",
            ]
        )

    return response


# ------------------------------------------------------------------------------
# Recurring Transactions
# ------------------------------------------------------------------------------


class RecurringTransactionListView(LoginRequiredMixin, ListView):
    model = RecurringTransaction
    template_name = "money/transactions/recurring_list.html"
    context_object_name = "recurring_transactions"

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = timezone.localdate()
        context["current_page"] = "recurring_transactions"
        return context


class RecurringTransactionCreateView(LoginRequiredMixin, CreateView):
    model = RecurringTransaction
    form_class = RecurringTransactionForm
    template_name = "money/transactions/recurring_form.html"
    success_url = reverse_lazy("money:recurring_transaction_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.user = self.request.user

        # Keep category aligned with sub_cat if present
        if obj.sub_cat_id:
            obj.category = obj.sub_cat.category

        obj.save()
        form.save_m2m()

        messages.success(self.request, "Recurring transaction added successfully!")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "recurring_transactions"
        return context


class RecurringTransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = RecurringTransaction
    form_class = RecurringTransactionForm
    template_name = "money/transactions/recurring_form.html"
    success_url = reverse_lazy("money:recurring_transaction_list")

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.user = self.request.user  # defensive

        if obj.sub_cat_id:
            obj.category = obj.sub_cat.category

        obj.save()
        form.save_m2m()

        messages.success(self.request, "Recurring transaction updated successfully!")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "recurring_transactions"
        return context


class RecurringTransactionDeleteView(LoginRequiredMixin, DeleteView):
    model = RecurringTransaction
    template_name = "money/transactions/recurring_confirm_delete.html"
    success_url = reverse_lazy("money:recurring_transaction_list")

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Recurring transaction deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_page"] = "recurring_transactions"
        return context


@staff_member_required
def recurring_report_view(request):
    """
    Staff-only report page, but data is still scoped to request.user.
    """
    year = int(request.GET.get("year", now().year))
    month_numbers = list(range(1, 13))

    templates = RecurringTransaction.objects.filter(user=request.user).order_by("transaction")

    tx = (
        Transaction.objects.filter(
            user=request.user,
            recurring_template__in=templates,
            date__year=year,
        )
        .values("recurring_template_id", "date__month")
        .annotate(total_amount=Sum("amount"))
    )

    amount_map = {(t["recurring_template_id"], t["date__month"]): t["total_amount"] for t in tx}

    data = [
        {"template": tmpl, "monthly_amounts": [amount_map.get((tmpl.id, m)) for m in month_numbers]}
        for tmpl in templates
    ]

    context = {
        "data": data,
        "months": [month_name[m] for m in month_numbers],
        "year": year,
        "current_page": "recurring_transactions",
    }
    return render(request, "money/transactions/recurring_report.html", context)


def _valid_run_date(year: int, month: int, day_value):
    last_day = monthrange(year, month)[1]
    run_day = day_value or 1
    run_day = max(1, min(int(run_day), last_day))
    return date(year, month, run_day)


@staff_member_required
def run_monthly_recurring_view(request):
    user = request.user
    today = timezone.localdate()

    form = RunRecurringForMonthForm(request.POST if request.method == "POST" else request.GET)
    if form.is_valid():
        target_month = form.cleaned_data["month"]
        target_year = form.cleaned_data["year"]
    else:
        target_month = today.month
        target_year = today.year

    recurrences = RecurringTransaction.objects.filter(user=user, active=True).order_by("day", "transaction")

    created_count = 0
    skipped_count = 0

    for r in recurrences:
        try:
            trans_date = _valid_run_date(target_year, target_month, r.day)

            already_exists = Transaction.objects.filter(
                user=user,
                recurring_template=r,
                date__year=target_year,
                date__month=target_month,
            ).exists()

            if already_exists:
                skipped_count += 1
                continue

            data = {
                "user": user,
                "trans_type": r.trans_type,
                "date": trans_date,
                "amount": r.amount,
                "transaction": r.transaction,
                "category": (r.sub_cat.category if r.sub_cat_id else r.category),
                "sub_cat": r.sub_cat,
                "invoice_number": "",
                "recurring_template": r,
            }

            if r.team_id:
                data["team"] = r.team
            if r.event_id:
                data["event"] = r.event
            if r.receipt:
                data["receipt"] = r.receipt

            with db_tx.atomic():
                Transaction.objects.create(**data)
                r.last_created = today
                r.save(update_fields=["last_created"])

            created_count += 1

        except Exception as e:
            logger.exception(
                "Error creating recurring (id=%s) for user %s in %s-%s: %s",
                r.id,
                user.id,
                target_year,
                target_month,
                e,
            )

    label = timezone.datetime(target_year, target_month, 1).strftime("%B %Y")
    messages.success(
        request,
        f"Created {created_count} recurring transaction(s) for {label}. "
        f"Skipped {skipped_count} already-created.",
    )
    return redirect("money:recurring_transaction_list")



import csv
import logging

logger = logging.getLogger(__name__)
from calendar import month_name, monthrange
from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
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
    TransForm,
    RecurringTransactionForm,
)
from ..models import *


class Transactions(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "money/transactions/transactions.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        qs = (
            Transaction.objects
            .select_related('sub_cat__category', 'sub_cat', 'team', 'event')
            .filter(user=self.request.user)
        )

        event_id = self.request.GET.get('event')
        if event_id and Event.objects.filter(id=event_id).exists():
            qs = qs.filter(event_id=event_id)

        category_id = self.request.GET.get('category')
        if category_id and Category.objects.filter(id=category_id).exists():
            qs = qs.filter(sub_cat__category_id=category_id)

        sub_cat_id = self.request.GET.get('sub_cat')
        if sub_cat_id and SubCategory.objects.filter(id=sub_cat_id).exists():
            qs = qs.filter(sub_cat_id=sub_cat_id)

        year = self.request.GET.get('year')
        if year and year.isdigit() and 1900 <= int(year) <= 9999:
            qs = qs.filter(date__year=int(year))

        sort = self.request.GET.get('sort', '-date')
        valid_sort_fields = [
            'date', '-date',
            'trans_type', '-trans_type',
            'transaction', '-transaction',
            'event__slug', '-event__slug',
            'amount', '-amount',
            'invoice_number', '-invoice_number',
        ]
        if sort not in valid_sort_fields:
            sort = '-date'
        self.current_sort = sort

        return qs.order_by(sort)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['col_headers'] = [
            {'field': 'date', 'label': 'Date'},
            {'field': 'trans_type', 'label': 'Type'},
            {'field': 'transaction', 'label': 'Description'},
            {'field': 'event__slug', 'label': 'Event'},
            {'field': 'amount', 'label': 'Amount'},
            {'field': 'invoice_number', 'label': 'Invoice #'},
        ]

        ctx['current_sort'] = self.current_sort
        ctx['events'] = (
            Event.objects.filter(transactions__user=self.request.user)
            .distinct().order_by('slug')
        )

        ctx['categories'] = (
            Category.objects.filter(subcategories__transaction__user=self.request.user)
            .distinct().order_by('category')
        )

        ctx['subcategories'] = (
            SubCategory.objects.filter(transaction__user=self.request.user)
            .distinct().order_by('sub_cat')
        )

        ctx['years'] = [
            str(y) for y in (
                Transaction.objects.filter(user=self.request.user)
                .annotate(year=ExtractYear('date'))
                .values_list('year', flat=True)
                .distinct()
                .order_by('-year')
            )
        ]

        ctx.update({
            'selected_event': self.request.GET.get('event', ''),
            'selected_category': self.request.GET.get('category', ''),
            'selected_sub_cat': self.request.GET.get('sub_cat', ''),
            'selected_year': self.request.GET.get('year', ''),
            'current_page': 'transactions',
        })
        return ctx


class TransactionDetailView(LoginRequiredMixin, DetailView):
    model = Transaction
    template_name = 'money/transactions/transactions_detail_view.html'
    context_object_name = 'transaction'

    def get_queryset(self):
        return Transaction.objects.select_related(
            'sub_cat__category', 'sub_cat', 'team', 'event'
        ).filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'transactions'
        return context




class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransForm
    template_name = 'money/transactions/transaction_add.html'
    success_url = reverse_lazy('money:add_transaction_success')

    def form_valid(self, form):
        form.instance.user = self.request.user

        sub_cat = form.cleaned_data.get('sub_cat')
        if sub_cat:
            form.instance.category = sub_cat.category

        try:
            with transaction.atomic():
                response = super().form_valid(form)
                messages.success(self.request, 'Transaction added successfully!')
                return response
        except Exception as e:
            logger.error(f"Error adding transaction for user {self.request.user.id}: {e}")
            messages.error(self.request, 'Error adding transaction. Please check the form.')
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'transactions'
        return context



class TransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransForm
    template_name = "money/transactions/transaction_edit.html"
    success_url = reverse_lazy("money:transactions")

    def get_queryset(self):
        """
        Limit updates to the logged-in user's transactions.
        """
        return Transaction.objects.filter(user=self.request.user)

    def form_valid(self, form):
        """
        Save a valid transaction inside an atomic block.
        Django handles POST + FILES binding for us.
        """
        try:
            with transaction.atomic():
                self.object = form.save()
            messages.success(self.request, "Transaction updated successfully!")
            return redirect(self.get_success_url())
        except Exception as e:
            logger.error(
                "Error updating transaction %s for user %s: %s",
                getattr(self.object, "id", "unknown"),
                getattr(self.request.user, "id", "anon"),
                e,
            )
            messages.error(self.request, "Error updating transaction. Please check the form.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        """
        DEBUG: log exactly why the first POST is failing, which is
        what forces you to pick the file a second time.
        """
        logger.warning(
            "TransactionUpdateView.form_invalid for user %s. Errors: %s",
            getattr(self.request.user, "id", "anon"),
            form.errors,
        )
        print("==== TransactionUpdateView.form_invalid ====")
        print("FORM VALID:", form.is_valid())
        print("FORM ERRORS:", form.errors)

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
    success_url = reverse_lazy('money:transactions')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                response = super().delete(request, *args, **kwargs)
                messages.success(self.request, "Transaction deleted successfully!")
                return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete transaction due to related records.")
            return redirect('money:transactions')
        except Exception as e:
            logger.error(f"Error deleting transaction for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting transaction.")
            return redirect('money:transactions')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'money:transactions'
        return context



@login_required
def add_transaction_success(request):
    context = {'current_page': 'transactions'}
    return render(request, 'money/transactions/transaction_add_success.html', context)




export_transactions_csv



# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->          R E C U R R I N G   T R A N S 


class RecurringTransactionListView(LoginRequiredMixin, ListView):
    model = RecurringTransaction
    template_name = 'money/transactions/recurring_list.html'
    context_object_name = 'recurring_transactions'

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring transactions'
        return context


class RecurringTransactionCreateView(LoginRequiredMixin, CreateView):
    model = RecurringTransaction
    form_class = RecurringTransactionForm
    template_name = 'money/transactions/recurring_form.html'
    success_url = reverse_lazy('money:recurring_transaction_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        sub_cat = form.cleaned_data.get('sub_cat')
        if sub_cat:
            form.instance.category = sub_cat.category
        messages.success(self.request, "Recurring transaction added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring_transactions'
        return context



class RecurringTransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = RecurringTransaction
    form_class = RecurringTransactionForm
    template_name = 'money/transactions/recurring_form.html'
    success_url = reverse_lazy('money:recurring_transaction_list')
    context = { 'current_page': 'recurring transactions', }

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Recurring transaction updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring_transactions'
        return context


class RecurringTransactionDeleteView(LoginRequiredMixin, DeleteView):
    model = RecurringTransaction
    template_name = 'money/transactions/recurring_confirm_delete.html'
    success_url = reverse_lazy('money:recurring_transaction_list')
    context = { 'current_page': 'recurring transactions', }

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Recurring transaction deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring_transactions'
        return context


@staff_member_required
def recurring_report_view(request):
    year = int(request.GET.get('year', now().year))
    month_numbers = list(range(1, 13))

    templates = (RecurringTransaction.objects
                 .filter(user=request.user)
                 .order_by('transaction'))

    tx = (Transaction.objects
          .filter(recurring_template__in=templates, date__year=year)
          .values('recurring_template_id', 'date__month')
          .annotate(total_amount=Sum('amount')))

    amount_map = {(t['recurring_template_id'], t['date__month']): t['total_amount'] for t in tx}

    data = [{
        'template': tmpl,
        'monthly_amounts': [amount_map.get((tmpl.id, m)) for m in month_numbers],
    } for tmpl in templates]

    context = {
        'data': data,
        'months': [month_name[m] for m in month_numbers],  
        'year': year,
        'current_page': 'recurring_transactions',
    }
    return render(request, 'money/transactions/recurring_report.html', context)



def _valid_run_date(today, day_value):
    """
    Resolve a safe date for this month:
    - default to 1 if day is None or falsy
    - clamp to [1, last_day_of_month]
    """
    last_day = monthrange(today.year, today.month)[1]
    run_day = day_value or 1
    run_day = max(1, min(run_day, last_day))
    return date(today.year, today.month, run_day)


@staff_member_required
def run_monthly_recurring_view(request):
    """
    Generate this month's Transactions from active RecurringTransaction templates
    for the current user, skipping any that were already created this month.
    """
    today = timezone.localdate()
    user = request.user

    recurrences = (
        RecurringTransaction.objects
        .filter(user=user, active=True)
        .exclude(last_created__year=today.year, last_created__month=today.month)
        .order_by('day', 'transaction')
    )

    created_count = 0

    for r in recurrences:
        try:
            trans_date = _valid_run_date(today, r.day)

            data = {
                "user": user,
                "trans_type": r.trans_type,
                "date": trans_date,
                "amount": r.amount,
                "transaction": r.transaction,
                "category": (r.sub_cat.category if r.sub_cat else r.category),
                "sub_cat": r.sub_cat,
                "invoice_number": "",        
                "recurring_template": r,       
            }

            # Optional FKs
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
                "Error creating recurring (id=%s) for user %s: %s",
                r.id, user.id, e
            )

    messages.success(
        request,
        f"Created {created_count} recurring transaction(s) for {today.strftime('%B %Y')}."
    )
    return redirect('money:recurring_transaction_list')




# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->            R E C E I P T S


@login_required
def receipts_list(request):
    query = request.GET.get('search', '')
    receipts = Transaction.objects.filter(user=request.user, receipt__isnull=False)

    if query:
        receipts = receipts.filter(
            Q(invoice_number__icontains=query) |
            Q(transaction__icontains=query)
        )

    receipts = receipts.order_by('-date')
    paginator = Paginator(receipts, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'receipts': page_obj.object_list,
        'page_obj': page_obj,
        'request': request,
    }
    return render(request, 'money/transactions/receipts_list.html', context)


@login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(Transaction, pk=pk, user=request.user, receipt__isnull=False)
    return render(request, 'money/transactions/receipt_detail.html', {'receipt': receipt})




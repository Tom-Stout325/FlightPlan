import logging

logger = logging.getLogger(__name__)
import csv
import tempfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.conf.urls.static import static
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import (
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from equipment.models import Equipment
from weasyprint import HTML

from ..forms.taxes.taxes import (
    CategoryForm,
    SubCategoryForm,
    MileageForm,
    MileageRateForm,
)
from ..models import *





class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'money/taxes/category_page.html'
    context_object_name = 'category'

    def get_queryset(self):
        return Category.objects.prefetch_related('subcategories').order_by('category')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context



class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/taxes/category_form.html"
    success_url = reverse_lazy('money:money/category_page')

    def form_valid(self, form):
        messages.success(self.request, "Category added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/taxes/category_form.html"
    success_url = reverse_lazy('money:category_page')

    def form_valid(self, form):
        messages.success(self.request, "Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = "money/taxes/category_confirm_delete.html"
    success_url = reverse_lazy('money:category_page')

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Category deleted successfully!")
            return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete category due to related transactions.")
            return redirect('money/category_page')
        except Exception as e:
            logger.error(f"Error deleting category for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting category.")
            return redirect('money/category_page')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




@login_required
def category_summary(request):
    year = request.GET.get('year')
    context = get_summary_data(request, year)
    context['available_years'] = [d.year for d in Transaction.objects.filter(
        user=request.user).dates('date', 'year', order='DESC').distinct()]
    context['current_page'] = 'reports'
    return render(request, 'money/taxes/category_summary.html', context)




@login_required
def category_summary_pdf(request):
    year = request.GET.get('year')
    context = get_summary_data(request, year)
    context['now'] = timezone.now()
    context['selected_year'] = year or timezone.now().year
    context['logo_url'] = request.build_absolute_uri('/static/img/logo.png')

    try:
        template = get_template('money/taxes/category_summary_pdf.html')
        html_string = template.render(context)
        html_string = "<style>@page { size: 8.5in 11in; margin: 1in; }</style>" + html_string

        if request.GET.get("preview") == "1":
            return HttpResponse(html_string)

        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(tmp.name)
            tmp.seek(0)
            response = HttpResponse(tmp.read(), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename=\"category_summary.pdf\"'
            return response
    except Exception as e:
        logger.error(f"Error generating category summary PDF: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect('money:category_summary')


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->         S U B    C A T E G O R I E S 




class SubCategoryCreateView(LoginRequiredMixin, CreateView):
    model = SubCategory
    form_class = SubCategoryForm
    template_name = "money/taxes/sub_category_form.html"
    success_url = reverse_lazy('money/taxes/category_page')

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context



class SubCategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = SubCategory
    form_class = SubCategoryForm
    template_name = "money/taxes/sub_category_form.html"
    success_url = reverse_lazy('money/taxes/category_page')
    context_object_name = "sub_cat"

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




class SubCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = SubCategory
    template_name = "money/taxes/sub_category_confirm_delete.html"
    success_url = reverse_lazy('money/taxes/category_page')

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Sub-Category deleted successfully!")
            return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete sub-category due to related transactions.")
            return redirect('money/taxes/category_page')
        except Exception as e:
            logger.error(f"Error deleting sub-category for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting sub-category.")
            return redirect('money/taxes/category_page')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context



# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->            R E P O R T S




def get_summary_data(request, year):
    EXCLUDED_INCOME_CATEGORIES = ['Equipment Sale']

    try:
        current_year = timezone.now().year
        selected_year = int(year) if year and str(year).isdigit() else current_year
    except ValueError:
        messages.error(request, "Invalid year selected.")
        selected_year = current_year

    transactions = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year
    ).select_related('sub_cat__category')

    income_data = defaultdict(lambda: {
        'total': Decimal('0.00'),
        'subcategories': defaultdict(lambda: [Decimal('0.00'), None])
    })

    expense_data = defaultdict(lambda: {
        'total': Decimal('0.00'),
        'subcategories': defaultdict(lambda: [Decimal('0.00'), None])
    })

    for t in transactions:
        category = t.sub_cat.category if t.sub_cat and t.sub_cat.category else None
        sub_cat_name = t.sub_cat.sub_cat if t.sub_cat else "Uncategorized"
        cat_name = category.category if category else "Uncategorized"
        sched_line = category.schedule_c_line if category and category.schedule_c_line else None

        is_meals = t.sub_cat and t.sub_cat.slug == 'meals'
        is_fuel = t.sub_cat and t.sub_cat.slug == 'fuel'
        is_personal_vehicle = t.transport_type == "personal_vehicle"

        if is_meals:
            amount = round(t.amount * Decimal('0.5'), 2)
        elif is_fuel and is_personal_vehicle:
            amount = Decimal('0.00')
        else:
            amount = t.amount

        if t.trans_type == 'Income':
            if cat_name in EXCLUDED_INCOME_CATEGORIES:
                continue
            target_data = income_data
        else:
            target_data = expense_data

        target_data[cat_name]['total'] += amount
        target_data[cat_name]['subcategories'][sub_cat_name][0] += amount
        target_data[cat_name]['subcategories'][sub_cat_name][1] = sched_line

    def format_data(data_dict):
        return [
            {
                'category': cat,
                'total': values['total'],
                'subcategories': [(sub, amt_sched[0], amt_sched[1]) for sub, amt_sched in values['subcategories'].items()]
            }
            for cat, values in sorted(data_dict.items())
        ]

    income_category_totals = format_data(income_data)
    expense_category_totals = format_data(expense_data)
    income_total = sum(item['total'] for item in income_category_totals)
    expense_total = sum(item['total'] for item in expense_category_totals)
    net_profit = income_total - expense_total

    available_years = Transaction.objects.filter(user=request.user).dates('date', 'year', order='DESC')

    return {
        'selected_year': selected_year,
        'income_category_totals': income_category_totals,
        'expense_category_totals': expense_category_totals,
        'income_category_total': income_total,
        'expense_category_total': expense_total,
        'net_profit': net_profit,
        'available_years': [d.year for d in available_years],
    }



@login_required
def financial_statement(request):
    year = request.GET.get('year', str(timezone.now().year))
    context = get_summary_data(request, year)
    context['current_page'] = 'reports'
    return render(request, 'money/taxes/financial_statement.html', context)


@login_required
def financial_statement_pdf(request, year):
    try:
        selected_year = int(year)
    except ValueError:
        selected_year = timezone.now().year

    context = get_summary_data(request, selected_year)
    context['now'] = timezone.now()
    html_string = render_to_string('money/taxes/financial_statement_pdf.html', context)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Financial_Statement_{selected_year}.pdf"'

    return response


def get_schedule_c_summary(transactions):
    line_summary = defaultdict(lambda: {'total': Decimal('0.00'), 'items': set()})

    for t in transactions:
        if not t.sub_cat or not t.sub_cat.category or not t.sub_cat.category.schedule_c_line:
            continue
        line = t.sub_cat.category.schedule_c_line
        amount = t.amount
        if t.trans_type == 'Expense':
            if t.sub_cat_id == 26: 
                amount *= Decimal('0.5')
            elif t.sub_cat_id == 27 and t.transport_type == 'personal_vehicle':
                continue  
            amount = -abs(amount)
        line_summary[line]['total'] += amount
        line_summary[line]['items'].add(t.sub_cat.category.category)

    return [
        {'line': line, 'total': data['total'], 'categories': sorted(data['items'])}
        for line, data in sorted(line_summary.items())
    ]

    
    
@login_required
def schedule_c_summary(request):
    year = request.GET.get('year', timezone.now().year)
    transactions = Transaction.objects.filter(user=request.user, date__year=year).select_related('sub_cat__category')
    summary = get_schedule_c_summary(transactions)

    income_total = sum(t.amount for t in transactions if t.trans_type == 'Income')
    total_expenses = sum(row['total'] for row in summary if row['total'] < 0)
    net_profit = income_total + total_expenses

    return render(request, 'money/taxes/schedule_c_summary.html', {
        'summary': summary,
        'income_total': income_total,
        'net_profit': net_profit,
        'selected_year': year,
        'current_page': 'reports',
    })



@login_required
def schedule_c_summary_pdf(request, year):
    transactions = Transaction.objects.filter(user=request.user, date__year=year).select_related('sub_cat__category')
    summary = get_schedule_c_summary(transactions)
    income_total = sum(t.amount for t in transactions if t.trans_type == 'Income')
    total_expenses = sum(row['total'] for row in summary if row['total'] < 0)
    net_profit = income_total + total_expenses

    logo_url = request.build_absolute_uri(static('images/logo2.png'))

    html = render_to_string('money/taxes/schedule_c_summary_pdf.html', {
        'summary': summary,
        'income_total': income_total,
        'net_profit': net_profit,
        'selected_year': year,
        'logo_url': logo_url,
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=schedule_c_summary_{year}.pdf'
    HTML(string=html).write_pdf(response)
    return response



@login_required
def form_4797_view(request):
    sold_equipment = Equipment.objects.filter(date_sold__isnull=False, sale_price__isnull=False)
    report_data = []

    for item in sold_equipment:
        purchase_cost = Decimal('0.00') if item.deducted_full_cost else (item.purchase_price or Decimal('0.00'))
        gain = item.sale_price - item.purchase_cost

        report_data.append({
            'name': item.name,
            'date_sold': item.date_sold,
            'sale_price': item.sale_price,
            'purchase_cost': item.purchase_cost,
            'gain': gain,
        })

    context = {
        'report_data': report_data,
        'current_page': 'form_4797'
    }
    return render(request, 'money/taxes/form_4797.html', context)



@login_required
def form_4797_pdf(request):
    sold_equipment = Equipment.objects.filter(date_sold__isnull=False, sale_price__isnull=False)
    report_data = []

    for item in sold_equipment:
        basis = Decimal('0.00') if item.deducted_full_cost else (item.purchase_price or Decimal('0.00'))
        gain = item.sale_price - basis

        report_data.append({
            'name': item.name,
            'date_sold': item.date_sold,
            'sale_price': item.sale_price,
            'basis': basis,
            'gain': gain,
        })

    context = {
        'report_data': report_data,
        'company_name': "Airborne Images",
 
    }

    template = get_template('money/taxes/form_4797_pdf.html')
    html_string = template.render(context)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as output:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(output.name)
        output.seek(0)
        pdf = output.read()

    preview = request.GET.get('preview') == '1'
    disposition = 'inline' if preview else 'attachment'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'{disposition}; filename="form_4797.pdf"'
    return response




# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->           M I L E A G E



def get_mileage_context(request):
    try:
        r = MileageRate.objects.first()
        rate = Decimal(str(r.rate)) if r and r.rate is not None else Decimal('0.70')
    except Exception:
        rate = Decimal('0.70')
        messages.error(request, "Error fetching mileage rate. Using default rate.")

    year = datetime.now().year

    base_qs = (
        Miles.objects
        .filter(user=request.user, date__year=year)
        .select_related('client', 'event')
    )

    miles_expr = ExpressionWrapper(
        Coalesce(F('total'), F('end') - F('begin'), Value(0)),
        output_field=DecimalField(max_digits=12, decimal_places=1),
    )
    qs = base_qs.annotate(miles=miles_expr)
    qs = qs.annotate(
        amount=Case(
            When(
                mileage_type='Taxable',
                then=ExpressionWrapper(
                    F('miles') * Value(rate),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            ),
            default=Value(0),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by('-date')
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    totals = qs.filter(mileage_type='Taxable').aggregate(
        total_miles=Sum('miles'),
        total_amount=Sum('amount'),
    )
    total_miles = totals['total_miles'] or Decimal('0')
    taxable_dollars = totals['total_amount'] or (total_miles * rate)

    return {
        'mileage_list': page_obj,
        'page_obj': page_obj,
        'total_miles': total_miles,
        'taxable_dollars': taxable_dollars,
        'current_year': year,
        'mileage_rate': rate,
        'current_page': 'mileage',
    }



@login_required
def mileage_log(request):
    context = get_mileage_context(request)
    return render(request, 'money/taxes/mileage_log.html', context)



class MileageCreateView(LoginRequiredMixin, CreateView):
    model = Miles
    form_class = MileageForm
    template_name = 'money/taxes/mileage_form.html'
    success_url = reverse_lazy('money:mileage_log')

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Mileage entry added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'mileage'
        return context


class MileageUpdateView(LoginRequiredMixin, UpdateView):
    model = Miles
    form_class = MileageForm
    template_name = 'money/taxes/mileage_form.html'
    success_url = reverse_lazy('mileage_log')

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Mileage entry updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'mileage'
        return context


class MileageDeleteView(LoginRequiredMixin, DeleteView):
    model = Miles
    template_name = 'money/taxes/mileage_confirm_delete.html'
    success_url = reverse_lazy('money:mileage_log')

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Mileage entry deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'mileage'
        return context



@login_required
def update_mileage_rate(request):
    mileage_rate = MileageRate.objects.first() or MileageRate(rate=0.70)
    if request.method == 'POST':
        form = MileageRateForm(request.POST, instance=mileage_rate)
        if form.is_valid():
            form.save()
            messages.success(request, "Mileage rate updated successfully!")
            return redirect('mileage_log')
        else:
            messages.error(request, "Error updating mileage rate. Please check the form.")
    else:
        form = MileageRateForm(instance=mileage_rate)
    context = {'form': form, 'current_page': 'mileage'}
    return render(request, 'money/taxes/update_mileage_rate.html', context)


@login_required
def export_mileage_csv(request):
    miles_entries = Miles.objects.filter(user=request.user).select_related('client', 'invoice')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="mileage.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date',
        'Start Odometer',
        'End Odometer',
        'Total Miles',
        'Client',
        'Invoice #',
        'Tax Deductible',
        'Job',
        'Vehicle',
        'Mileage Type',
    ])

    for entry in miles_entries:
        writer.writerow([
            entry.date,
            entry.begin,
            entry.end,
            entry.total,
            str(entry.client) if entry.client else '',
            entry.invoice.invoice if entry.invoice else '',
            entry.job or '',
            entry.vehicle or '',
            entry.mileage_type,
        ])

    return response


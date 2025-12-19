import logging

logger = logging.getLogger(__name__)
import tempfile
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import get_template, render_to_string
from django.utils import timezone
from django.utils.timezone import now
from django.conf import settings
from django.urls import reverse
from django.db.models.functions import Coalesce

from weasyprint import HTML, CSS

from ..forms import *
from ..models import *

from money.models import (
            Invoice, 
            Transaction, 
            MileageRate, 
            Miles,
)




REPORT_CARDS = [
    {
        "key": "financial_statement",
        "title": "Financial Statement",
        "subtitle": "View income, expenses, and net profit by sub-category.",
        "url_name": "money:financial_statement",
        "icon": "fa-solid fa-chart-line",
        "bg_color": "#f0f8ff",
        "text_class": "text-primary",
    },
    {
        "key": "category_summary",
        "title": "Category Summary",
        "subtitle": "Summary of income and expenses by category and sub-category.",
        "url_name": "money:category_summary",
        "icon": "fa-solid fa-folder-tree",
        "bg_color": "#eaf6ea",
        "text_class": "text-success",
    },
    {
        "key": "travel_summary",
        "title": "Travel Summary",
        "subtitle": "Filter by year; see invoice totals, travel expenses, and net income.",
        "url_name": "money:travel_summary",
        "icon": "fa-solid fa-file-invoice-dollar",
        "bg_color": "#fff8e6",
        "text_class": "text-warning",
    },
    {
        "key": "form_4797",
        "title": "Form 4797",
        "subtitle": "Report gains from the sale of business property and equipment.",
        "url_name": "money:form_4797",
        "icon": "fa-solid fa-boxes-packing",
        "bg_color": "#ffffff",
        "text_class": "text-danger",
    },
    {
        "key": "recurring_transactions",
        "title": "Recurring Transactions",
        "subtitle": "Review Monthly Recurring Transactions",
        "url_name": "money:recurring_transaction_list",
        "icon": "fa-solid fa-tags",
        "bg_color": "#fff5f5",
        "text_class": "text-info",
    },
    {
        "key": "nhra_summary",
        "title": "NHRA Summary",
        "subtitle": "Compare NHRA income and expenses across years.",
        "url_name": "money:nhra_summary_report",
        "icon": "fa-solid fa-tags",
        "bg_color": "#fff5f5",
        "text_class": "text-danger",
    },
    {
        "key": "events",
        "title": "Events",
        "subtitle": "Analyze events saved on the system.",
        "url_name": "money:event_list",
        "icon": "fa-solid fa-plane-departure",
        "bg_color": "#eaf3fb",
        "text_class": "text-primary",
    },
    {
        "key": "receipts",
        "title": "Receipts",
        "subtitle": "Analyze receipts saved on the system.",
        "url_name": "money:receipts_list",
        "icon": "fa-solid fa-plane-departure",
        "bg_color": "#eaf3fb",
        "text_class": "text-primary",
    },
        {
        "key": "travel_expenses",
        "title": "Travel Expenses",
        "subtitle": "Analyze receipts travel expenses for events.",
        "url_name": "money:travel_expense_analysis",
        "icon": "fa-solid fa-plane-departure",
        "bg_color": "#eaf3fb",
        "text_class": "text-primary",
    },
]



@login_required
def reports_page(request):
    enabled_keys = getattr(settings, "ENABLED_REPORTS", None)

    cards = []
    for card in REPORT_CARDS:
        # If ENABLED_REPORTS is defined, only include those keys
        if enabled_keys is not None and card["key"] not in enabled_keys:
            continue

        c = card.copy()
        c["url"] = reverse(card["url_name"])
        cards.append(c)

    context = {
        "current_page": "reports",
        "report_cards": cards,
    }
    return render(request, "money/reports/reports.html", context)



@login_required
def nhra_summary(request):
    current_year = timezone.now().year
    years = [current_year, current_year - 1, current_year - 2]
    excluded_ids = [35, 133, 34, 67, 100]

    summary_data = Transaction.objects.filter(
        user=request.user
    ).exclude(event__id__in=excluded_ids).filter(
        date__year__in=years, trans_type__isnull=False
    ).values('event__name', 'date__year', 'trans_type').annotate(
        total=Sum('amount')
    ).order_by('event__name', 'date__year')

    result = defaultdict(lambda: {y: {"income": 0, "expense": 0, "net": 0} for y in years})
    
    for item in summary_data:
        event = item['event__name']
        year = item['date__year']
        trans_type = item['trans_type'].lower()
        if event:
            result[event][year][trans_type] = item['total']
            result[event][year]['net'] = result[event][year]['income'] - result[event][year]['expense']

    result_dict = dict(result)

    logger.debug(f"NHRA summary data for user {request.user.id}: {result_dict}")

    context = {
        "years": years,
        "summary_data": result_dict,
        "urls": {
            "reports": "/money/"
        },
        'current_page': 'reports'
    }
    return render(request, "money/reports/nhra_summary.html", context)





@login_required
def nhra_summary_report(request):
    current_year = now().year
    years = [current_year, current_year - 1, current_year - 2]

    include_meals = True
    
    travel_subcategories = [
        'Airfare',
        'Car Rental',
        'Fuel',
        'Hotels',
        'Other Travel',
    ]

    if include_meals:
        travel_subcategories.append('Meals')

    selected_event = request.GET.get('event', '').strip()

    base_qs = Transaction.objects.filter(
        user=request.user,
        trans_type='Expense',
        sub_cat__sub_cat__in=travel_subcategories,
        date__year__in=years
    ).select_related('event', 'sub_cat')

    all_events = (
        base_qs
        .filter(event__isnull=False)
        .values_list('event__title', flat=True)
        .distinct()
        .order_by('event__title')
    )

    if selected_event:
        base_qs = base_qs.filter(event__title=selected_event)

    summary_data = base_qs.values(
        'event__title', 'sub_cat__sub_cat', 'date__year'
    ).annotate(total=Sum('amount')).order_by('sub_cat__sub_cat', 'date__year')

    result = defaultdict(lambda: defaultdict(lambda: {y: Decimal('0.00') for y in years}))
    event_totals = defaultdict(lambda: {y: Decimal('0.00') for y in years})
    yearly_totals = {y: Decimal('0.00') for y in years}

    for item in summary_data:
        event = item['event__title'] or 'Unspecified'
        subcategory = item['sub_cat__sub_cat']
        year = item['date__year']
        amount = item['total'] or Decimal('0.00')
        result[event][subcategory][year] = amount
        event_totals[event][year] += amount
        yearly_totals[year] += amount

    context = {
        'years': years,
        'events': all_events,
        'selected_event': selected_event,
        'summary_data': dict(result),
        'event_totals': dict(event_totals),
        'yearly_totals': yearly_totals,
        'travel_subcategories': travel_subcategories,
        'current_page': 'reports',
    }

    return render(request, 'money/reports/nhra_summary_report.html', context)




@login_required
def travel_expense_analysis(request):
    current_year = now().year
    available_years = list(range(2023, current_year + 1))
    selected_year = int(request.GET.get('year', current_year))
    income_subcat_id = 19  # Services: Drone
    expense_subcat_ids = [100, 23, 24, 27, 25, 26, 28]
    income_total = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Income',
        sub_cat_id=income_subcat_id
    ).aggregate(total=Sum('amount'))['total'] or 0

    expenses_qs = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Expense',
        sub_cat_id__in=expense_subcat_ids
    ).values('sub_cat__sub_cat', 'sub_cat_id') \
     .annotate(total=Sum('amount')).order_by('sub_cat__sub_cat')

    expense_data = []
    total_expense = sum(row['total'] for row in expenses_qs)

    for row in expenses_qs:
        amount = row['total']
        percentage = (amount / total_expense) * 100 if total_expense else 0
        expense_data.append({
            'name': row['sub_cat__sub_cat'],
            'amount': amount,
            'percentage': round(percentage, 2)
        })

    context = {
        'selected_year': selected_year,
        'available_years': available_years,
        'income_total': income_total,
        'expense_data': expense_data,
        'total_expense': total_expense,
        'current_page': 'reports',
    }

    return render(request, 'money/reports/travel_expense_analysis.html', context)



@login_required
def travel_expense_analysis_pdf(request):
    selected_year = int(request.GET.get('year', now().year))

    income_subcat_id = 19
    expense_subcat_ids = [100, 23, 24, 27, 25, 26, 28]

    income_total = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Income',
        sub_cat_id=income_subcat_id
    ).aggregate(total=Sum('amount'))['total'] or 0

    expenses_qs = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Expense',
        sub_cat_id__in=expense_subcat_ids
    ).values('sub_cat__sub_cat', 'sub_cat_id') \
     .annotate(total=Sum('amount')).order_by('sub_cat__sub_cat')

    expense_data = []
    total_expense = sum(row['total'] for row in expenses_qs)

    for row in expenses_qs:
        amount = row['total']
        percentage = (amount / total_expense) * 100 if total_expense else 0
        expense_data.append({
            'name': row['sub_cat__sub_cat'],
            'amount': amount,
            'percentage': round(percentage, 2)
        })

    html_string = render_to_string('money/reports/travel_expense_analysis_pdf.html', {
        'selected_year': selected_year,
        'income_total': income_total,
        'expense_data': expense_data,
        'total_expense': total_expense,
    })

    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf_file = html.write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename="Travel_Expense_Report_{selected_year}.pdf"'
    return response





@login_required
def nhra_summary_report_pdf(request):
    current_year = now().year
    years = [current_year, current_year - 1, current_year - 2]
    travel_subcategories = [
        'Travel: Car Rental', 'Travel: Flights', 'Travel: Fuel',
        'Travel: Hotel', 'Travel: Meals', 'Travel: Miscellaneous'
    ]
    transactions = Transaction.objects.filter(
        user=request.user,
        trans_type='Expense',
        sub_cat__sub_cat__in=travel_subcategories,
        date__year__in=years
    ).select_related('event', 'sub_cat')
    summary_data = transactions.values(
        'event__name', 'sub_cat__sub_cat', 'date__year'
    ).annotate(total=Sum('amount')).order_by('event__name', 'sub_cat__sub_cat', 'date__year')
    result = defaultdict(lambda: defaultdict(lambda: {y: 0 for y in years}))
    for item in summary_data:
        event = item['event__name'] or 'Unspecified'
        subcategory = item['sub_cat__sub_cat']
        year = item['date__year']
        result[event][subcategory][year] = item['total']
    event_totals = defaultdict(lambda: {y: 0 for y in years})
    yearly_totals = {y: 0 for y in years}
    for event, subcats in result.items():
        for subcat, year_data in subcats.items():
            for year, amount in year_data.items():
                event_totals[event][year] += amount
                yearly_totals[year] += amount
    context = {
        'years': years,
        'summary_data': dict(result),
        'event_totals': dict(event_totals),
        'yearly_totals': yearly_totals,
        'travel_subcategories': travel_subcategories,
        'current_page': 'reports'
    }
    try:
        template = get_template('money/reports/nhra_summary_report.html')
        html_string = template.render(context)
        html_string = "<style>@page { size: 8.5in 11in; margin: 1in; }</style>" + html_string
        with tempfile.NamedTemporaryFile(delete=True) as output:
            HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(output.name)
            output.seek(0)
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="nhra_summary_report.pdf"'
            response.write(output.read())
        return response
    except Exception as e:
        logger.error(f"Error generating PDF for user {request.user.id}: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect('money:nhra_summary_report')






def _matches_subcat(t: Transaction, slug_candidates=None, name_candidates=None) -> bool:
    """
    Best-effort matcher so the report works even if your slug naming differs.
    - slug_candidates: list of acceptable slug values
    - name_candidates: list of acceptable substrings to match against sub_cat.sub_cat (name)
    """
    if not t.sub_cat:
        return False

    slug = (getattr(t.sub_cat, "slug", "") or "").strip().lower()
    name = (getattr(t.sub_cat, "sub_cat", "") or "").strip().lower()

    if slug_candidates:
        if slug in {s.lower() for s in slug_candidates}:
            return True

    if name_candidates:
        for n in name_candidates:
            if n.lower() in name:
                return True

    return False







@login_required
def travel_summary(request: HttpRequest) -> HttpResponse:
    # --- Year selection -------------------------------------------------
    all_years_qs = (
        Invoice.objects
        .exclude(date__isnull=True)
        .values_list("date__year", flat=True)
        .distinct()
        .order_by("-date__year")
    )
    years = list(all_years_qs) or [now().year]

    selected_year = request.GET.get("year")
    try:
        selected_year = int(selected_year) if selected_year else years[0]
    except (TypeError, ValueError):
        selected_year = years[0]

    invoices = (
        Invoice.objects
        .select_related("event", "client", "service")
        .filter(date__year=selected_year)
        .order_by("date", "invoice_number")
    )

    year_txns = (
        Transaction.objects
        .filter(date__year=selected_year)
        .select_related("sub_cat__category", "event")
    )
    miles_expr = ExpressionWrapper(
        Coalesce(F("total"), F("end") - F("begin"), Value(0)),
        output_field=DecimalField(max_digits=12, decimal_places=1),
    )
    amount_expr = ExpressionWrapper(
        F("miles") * Value(mileage_rate),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    # --- Exact slugs ----------------------------------------------------
    SLUG_AIRFARE = "airfare"
    SLUG_HOTELS = "hotels"
    SLUG_CAR_RENTAL = "car-rental"
    SLUG_FUEL = "fuel"

    rows = []

    totals = {
        "invoice_amount": Decimal("0.00"),
        "airfare": Decimal("0.00"),
        "hotels": Decimal("0.00"),
        "car_rental": Decimal("0.00"),
        "fuel": Decimal("0.00"),
        "net_amount": Decimal("0.00"),
    }

    # Per-column “included” counters (denominator for each average)
    counts = {
        "invoice_amount": 0,  # typically all invoices (if amount > 0)
        "airfare": 0,
        "hotels": 0,
        "car_rental": 0,
        "fuel": 0,
        "net_amount": 0,  # if you want “net average” only where net != 0
    }

    def q2(x: Decimal) -> Decimal:
        return (x or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    for inv in invoices:
        inv_txns = year_txns.filter(event=inv.event, invoice_number=inv.invoice_number)

        airfare = Decimal("0.00")
        hotels = Decimal("0.00")
        car_rental = Decimal("0.00")
        fuel = Decimal("0.00")

        for t in inv_txns:
            if t.trans_type != Transaction.EXPENSE or not t.sub_cat:
                continue

            slug = (t.sub_cat.slug or "").strip().lower()
            amt = t.amount or Decimal("0.00")

            if slug == SLUG_AIRFARE:
                airfare += amt
            elif slug == SLUG_HOTELS:
                hotels += amt
            elif slug == SLUG_CAR_RENTAL:
                car_rental += amt
            elif slug == SLUG_FUEL:
                fuel += amt


        invoice_amount = inv.amount or Decimal("0.00")
        travel_total = airfare + hotels + car_rental + fuel + mileage_dollars
        net_amount = invoice_amount - travel_total

        rows.append(
            {
                "invoice": inv,
                "invoice_amount": invoice_amount,
                "airfare": airfare,
                "hotels": hotels,
                "car_rental": car_rental,
                "fuel": fuel,
                "net_amount": net_amount,
            }
        )

        # Totals
        totals["invoice_amount"] += invoice_amount
        totals["airfare"] += airfare
        totals["hotels"] += hotels
        totals["car_rental"] += car_rental
        totals["fuel"] += fuel
        totals["net_amount"] += net_amount

        # Counts (only if included)
        if invoice_amount != 0:
            counts["invoice_amount"] += 1
        if airfare > 0:
            counts["airfare"] += 1
        if hotels > 0:
            counts["hotels"] += 1
        if car_rental > 0:
            counts["car_rental"] += 1
        if fuel > 0:
            counts["fuel"] += 1
        if net_amount != 0:
            counts["net_amount"] += 1

    def avg(total: Decimal, denom: int) -> Decimal:
        if not denom:
            return Decimal("0.00")
        return q2(total / Decimal(denom))

    averages = {
        "invoice_amount": avg(totals["invoice_amount"], counts["invoice_amount"]),
        "airfare": avg(totals["airfare"], counts["airfare"]),
        "hotels": avg(totals["hotels"], counts["hotels"]),
        "car_rental": avg(totals["car_rental"], counts["car_rental"]),
        "fuel": avg(totals["fuel"], counts["fuel"]),
        "net_amount": avg(totals["net_amount"], counts["net_amount"]),
    }

    context = {
        "years": years,
        "selected_year": selected_year,
        "rows": rows,
        "totals": totals,
        "averages": averages,
        "counts": counts,  # optional (handy if you want to show “n=” in template)
        "invoice_count": invoices.count(),
        "current_page": "reports",
    }
    return render(request, "money/reports/travel_summary.html", context)





def _q2(x: Decimal) -> Decimal:
    return (x or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)





def build_travel_summary_context(request: HttpRequest, selected_year: int) -> dict:
    invoices = (
        Invoice.objects
        .select_related("event", "client", "service")
        .filter(date__year=selected_year)
        .order_by("date", "invoice_number")
    )

    year_txns = (
        Transaction.objects
        .filter(date__year=selected_year)
        .select_related("sub_cat__category", "event")
    )

    # Exact slugs (per your note)
    SLUG_AIRFARE = "airfare"
    SLUG_HOTELS = "hotels"
    SLUG_CAR_RENTAL = "car-rental"
    SLUG_FUEL = "fuel"

    rows = []
    totals = {
        "invoice_amount": Decimal("0.00"),
        "airfare": Decimal("0.00"),
        "hotels": Decimal("0.00"),
        "car_rental": Decimal("0.00"),
        "fuel": Decimal("0.00"),
        "net_amount": Decimal("0.00"),
    }

    # “included” counters (avg only where column > 0)
    counts = {k: 0 for k in totals.keys()}

    for inv in invoices:
        inv_txns = year_txns.filter(event=inv.event, invoice_number=inv.invoice_number)

        airfare = Decimal("0.00")
        hotels = Decimal("0.00")
        car_rental = Decimal("0.00")
        fuel = Decimal("0.00")

        for t in inv_txns:
            if t.trans_type != Transaction.EXPENSE or not t.sub_cat:
                continue

            slug = (t.sub_cat.slug or "").strip().lower()
            amt = t.amount or Decimal("0.00")

            if slug == SLUG_AIRFARE:
                airfare += amt
            elif slug == SLUG_HOTELS:
                hotels += amt
            elif slug == SLUG_CAR_RENTAL:
                car_rental += amt
            elif slug == SLUG_FUEL:
                fuel += amt

        invoice_amount = inv.amount or Decimal("0.00")
        travel_total = airfare + hotels + car_rental + fuel
        net_amount = invoice_amount - travel_total

        rows.append(
            {
                "invoice": inv,
                "invoice_amount": invoice_amount,
                "airfare": airfare,
                "hotels": hotels,
                "car_rental": car_rental,
                "fuel": fuel,
                "net_amount": net_amount,
            }
        )

        totals["invoice_amount"] += invoice_amount
        totals["airfare"] += airfare
        totals["hotels"] += hotels
        totals["car_rental"] += car_rental
        totals["fuel"] += fuel
        totals["net_amount"] += net_amount

        if invoice_amount != 0:
            counts["invoice_amount"] += 1
        if airfare > 0:
            counts["airfare"] += 1
        if hotels > 0:
            counts["hotels"] += 1
        if car_rental > 0:
            counts["car_rental"] += 1
        if fuel > 0:
            counts["fuel"] += 1
        if net_amount != 0:
            counts["net_amount"] += 1

    def avg(total: Decimal, denom: int) -> Decimal:
        return _q2(total / Decimal(denom)) if denom else Decimal("0.00")

    averages = {
        "invoice_amount": avg(totals["invoice_amount"], counts["invoice_amount"]),
        "airfare": avg(totals["airfare"], counts["airfare"]),
        "hotels": avg(totals["hotels"], counts["hotels"]),
        "car_rental": avg(totals["car_rental"], counts["car_rental"]),
        "fuel": avg(totals["fuel"], counts["fuel"]),
        "net_amount": avg(totals["net_amount"], counts["net_amount"]),
    }

    # Branding (logo URL must be absolute for WeasyPrint)
    brand_name = getattr(request, "brand_name", None) or "Airborne Images"

    return {
        "rows": rows,
        "totals": totals,
        "averages": averages,
        "counts": counts,
        "invoice_count": invoices.count(),
        "brand_name": brand_name,
        "selected_year": selected_year,
    }





@login_required
def travel_summary(request: HttpRequest) -> HttpResponse:
    all_years_qs = (
        Invoice.objects
        .exclude(date__isnull=True)
        .values_list("date__year", flat=True)
        .distinct()
        .order_by("-date__year")
    )
    years = list(all_years_qs) or [now().year]

    selected_year = request.GET.get("year")
    try:
        selected_year = int(selected_year) if selected_year else years[0]
    except (TypeError, ValueError):
        selected_year = years[0]

    report_ctx = build_travel_summary_context(request, selected_year)

    context = {
        "years": years,
        "selected_year": selected_year,
        "current_page": "reports",
        **report_ctx,
    }
    return render(request, "money/reports/travel_summary.html", context)







@login_required
def travel_summary_pdf_preview(request: HttpRequest) -> HttpResponse:
    # year handling matches the HTML
    selected_year = request.GET.get("year")
    try:
        selected_year = int(selected_year) if selected_year else now().year
    except (TypeError, ValueError):
        selected_year = now().year

    report_ctx = build_travel_summary_context(request, selected_year)

    html_string = render_to_string(
        "money/reports/travel_summary_pdf.html",
        report_ctx,
        request=request,
    )

    pdf_bytes = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    return HttpResponse(pdf_bytes, content_type="application/pdf")


@login_required
def travel_summary_pdf_download(request: HttpRequest) -> HttpResponse:
    selected_year = request.GET.get("year")
    try:
        selected_year = int(selected_year) if selected_year else now().year
    except (TypeError, ValueError):
        selected_year = now().year

    report_ctx = build_travel_summary_context(request, selected_year)

    html_string = render_to_string(
        "money/reports/travel_summary_pdf.html",
        report_ctx,
        request=request,
    )

    pdf_bytes = HTML(
        string=html_string,
        base_url=request.build_absolute_uri("/"),
    ).write_pdf()

    filename = f"travel-summary-{selected_year}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

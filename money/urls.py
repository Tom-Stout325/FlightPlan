from django.urls import path

# Dashboard
from .views.dashboard import Dashboard

# Transactions & Recurring
from .views.transactions import (
    Transactions,
    TransactionCreateView,
    TransactionDetailView,
    TransactionUpdateView,
    TransactionDeleteView,
    RecurringTransactionListView,
    RecurringTransactionCreateView,
    RecurringTransactionUpdateView,
    RecurringTransactionDeleteView,
    add_transaction_success,
    export_transactions_csv,
    recurring_report_view,
    run_monthly_recurring_view,
    receipts_list,
    receipt_detail,
)

# Invoices
from .views.invoices import (
    InvoiceListView,
    InvoiceDeleteView,
    InvoiceDetailView,
    InvoiceCreateView,
    InvoiceUpdateView,
    invoice_review,
    invoice_review_pdf,
    send_invoice_email,
    unpaid_invoices,
    export_invoices_csv,
    export_invoices_pdf,
    invoice_summary,
)

# Categories, Subcategories, Clients
from .views.clients import (
    ClientListView,
    ClientCreateView,
    ClientUpdateView,
    ClientDeleteView,
)

# Reports (non-tax)
from .views.reports import (
    reports_page,
    nhra_summary,
    race_expense_report,
    race_expense_report_pdf,
    travel_expense_analysis,
    travel_expense_analysis_pdf,
    

)

# Taxes (Schedule C, 4797, etc.)
from .views.taxes import (
    schedule_c_summary,
    schedule_c_summary_pdf,
    form_4797_view,
    form_4797_pdf,
    financial_statement,
    financial_statement_pdf,
    category_summary,
    category_summary_pdf,
    CategoryListView,
    CategoryCreateView,
    CategoryUpdateView,
    CategoryDeleteView,
    SubCategoryCreateView,
    SubCategoryUpdateView,
    SubCategoryDeleteView,
)

# Mileage
from .views.taxes import (
    MileageCreateView,
    MileageUpdateView,
    MileageDeleteView,
    mileage_log,
    update_mileage_rate,
    export_mileage_csv,
)

# Events
from .views.events import (
    EventListView,
    EventCreateView,
    EventUpdateView,
    EventDetailView,
    EventDeleteView,
)

app_name = "money"


urlpatterns = [
    # Dashboard
    path("dashboard", Dashboard.as_view(), name="dashboard"),

    # Transactions
    path("transactions/", Transactions.as_view(), name="transactions"),
    path("transaction/add/", TransactionCreateView.as_view(), name="add_transaction"),
    path("transaction/success/", add_transaction_success, name="add_transaction_success"),
    path("transaction/<int:pk>/", TransactionDetailView.as_view(), name="transaction_detail"),
    path("transaction/edit/<int:pk>/", TransactionUpdateView.as_view(), name="edit_transaction"),
    path("transaction/delete/<int:pk>/", TransactionDeleteView.as_view(), name="delete_transaction"),
    path("transactions/export/", export_transactions_csv, name="export_transactions_csv"),

    # Invoices
    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/<int:pk>/delete/", InvoiceDeleteView.as_view(), name="invoice_delete"),
    path("invoice/<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoice/<int:pk>/review/", invoice_review, name="invoice_review"),
    path("invoice/<int:pk>/review/pdf/", invoice_review_pdf, name="invoice_review_pdf"),
    path("invoice/new", InvoiceCreateView.as_view(), name="create_invoice"),
    path("invoice/edit/<int:pk>/", InvoiceUpdateView.as_view(), name="update_invoice"),
    path("invoice/<int:invoice_id>/email/", send_invoice_email, name="send_invoice_email"),
    path("unpaid-invoices/", unpaid_invoices, name="unpaid_invoices"),
    path("invoices/export/csv/", export_invoices_csv, name="export_invoices_csv"),
    path("invoices/export/pdf/", export_invoices_pdf, name="export_invoices_pdf"),

    # Categories & Subcategories
    path("category-report/", CategoryListView.as_view(), name="category_page"),
    path("category/add/", CategoryCreateView.as_view(), name="add_category"),
    path("category/edit/<int:pk>/", CategoryUpdateView.as_view(), name="edit_category"),
    path("category/delete/<int:pk>/", CategoryDeleteView.as_view(), name="delete_category"),
    path("sub_category/add/", SubCategoryCreateView.as_view(), name="add_sub_category"),
    path("sub_category/edit/<int:pk>/", SubCategoryUpdateView.as_view(), name="edit_sub_category"),
    path("sub_category/delete/<int:pk>/", SubCategoryDeleteView.as_view(), name="delete_sub_category"),

    # Clients
    path("clients/", ClientListView.as_view(), name="client_list"),
    path("clients/add/", ClientCreateView.as_view(), name="add_client"),
    path("clients/edit/<int:pk>/", ClientUpdateView.as_view(), name="edit_client"),
    path("client/delete/<int:pk>/", ClientDeleteView.as_view(), name="delete_client"),

    # Reports
    path("reports/", reports_page, name="reports"),
    path("financial-statement/", financial_statement, name="financial_statement"),
    path("money/financial-statement/pdf/<int:year>/", financial_statement_pdf, name="financial_statement_pdf",),
    path("category-summary/", category_summary, name="category_summary"),
    path("money/category-summary/pdf/", category_summary_pdf, name="category_summary_pdf"),
    path("nhra-summary/", nhra_summary, name="nhra_summary"),
    path("race-expense-report/", race_expense_report, name="race_expense_report"),
    path("race-expense-report/pdf/", race_expense_report_pdf, name="race_expense_report_pdf"),
    path("reports/travel-analysis/", travel_expense_analysis, name="travel_expense_analysis"),
    path("reports/travel-analysis/pdf/", travel_expense_analysis_pdf, name="travel_expense_analysis_pdf"),
    path("schedule-c/", schedule_c_summary, name="schedule_c_summary"),
    path("schedule-c/<int:year>/pdf/", schedule_c_summary_pdf, name="schedule_c_summary_pdf"),
    path("form-4797/", form_4797_view, name="form_4797"),
    path("form-4797/pdf/", form_4797_pdf, name="form_4797_pdf"),
    path("receipts/", receipts_list, name="receipts_list"),
    path("receipts/<int:pk>/", receipt_detail, name="receipt_detail"),
    path("reports/invoices/", invoice_summary, name="invoice_summary"),

    # Mileage
    path("mileage-log/", mileage_log, name="mileage_log"),
    path("mileage/add/", MileageCreateView.as_view(), name="mileage_create"),
    path("mileage/<int:pk>/edit/", MileageUpdateView.as_view(), name="mileage_update"),
    path("mileage/<int:pk>/delete/", MileageDeleteView.as_view(), name="mileage_delete"),
    path("mileage/update-rate/", update_mileage_rate, name="update_mileage_rate"),
    path("mileage/export/csv/", export_mileage_csv, name="export_mileage_csv"),

    # Events
    path("events/", EventListView.as_view(), name="event_list"),
    path("events/add/", EventCreateView.as_view(), name="create_event"),
    path("events/<int:pk>/edit/", EventUpdateView.as_view(), name="event_update"),
    path("events/<int:pk>/", EventDetailView.as_view(), name="event_detail"),
    path("events/<int:pk>/delete/", EventDeleteView.as_view(), name="event_delete"),

    # Recurring Transactions
    path("recurring/", RecurringTransactionListView.as_view(), name="recurring_transaction_list"),
    path("recurring/add/", RecurringTransactionCreateView.as_view(), name="recurring_add"),
    path("recurring/<int:pk>/edit/", RecurringTransactionUpdateView.as_view(), name="recurring_edit"),
    path("recurring/<int:pk>/delete/", RecurringTransactionDeleteView.as_view(), name="recurring_delete"),
    path("recurring/report/", recurring_report_view, name="recurring_report"),
    path("run-monthly-recurring/", run_monthly_recurring_view, name="run_monthly_recurring"),
]

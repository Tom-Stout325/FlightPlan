# money/urls.py
from django.urls import path

from .views.dashboard import Dashboard

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
)

from .views.invoices_v2 import (
    InvoiceV2IssueView,
    InvoiceV2MarkPaidView,
    InvoiceV2DeleteView,
    InvoiceV2DetailView,
    invoice_v2_create,
    invoice_v2_update,
    invoice_v2_pdf_view,
    invoice_v2_send_email,
    invoice_v2_review,
    InvoiceV2ListView,
    invoice_v2_suggest_number,
)

from .views.clients import (
    ClientListView,
    ClientCreateView,
    ClientUpdateView,
    ClientDeleteView,
)

from .views.reports import (
    reports_page,
    profit_loss,
    profit_loss_pdf,
    profit_loss_yoy,
    profit_loss_yoy_pdf,
    category_summary,
    category_summary_pdf,
    nhra_summary,
    nhra_summary_report,
    nhra_summary_report_pdf,
    travel_expense_analysis,
    travel_expense_analysis_pdf,
    travel_summary,
    travel_summary_pdf_preview,
    travel_summary_pdf_download,
    JobReviewView,
)

from .views.tax_tools import (
    CategoryListView,
    CategoryCreateView,
    CategoryUpdateView,
    CategoryDeleteView,
    SubCategoryCreateView,
    SubCategoryUpdateView,
    SubCategoryDeleteView,
    mileage_log,
    mileage_report_pdf,
    export_mileage_csv,
    MileageCreateView,
    MileageUpdateView,
    MileageDeleteView,
    update_mileage_rate,
)

from .views.tax_reports import (
    schedule_c_summary,
    tax_profit_loss,
    tax_category_summary,
    form_4797_view,
    form_4797_pdf,
    tax_profit_loss_pdf,
    tax_profit_loss_yoy_pdf,
    tax_profit_loss_yoy,
    tax_profit_loss_yoy_pdf,
    
)

from .views.vehicles import (
    VehicleListView,
    VehicleCreateView,
    VehicleUpdateView,
    VehicleDeleteView,
    VehicleDetailView,
)

from .views.events import (
    EventListView,
    EventCreateView,
    EventUpdateView,
    EventDetailView,
    EventDeleteView,
)

from .views.company_profiles import (
    CompanyProfileCreateView,
    CompanyProfileDeleteView,
    CompanyProfileDetailView,
    CompanyProfileListView,
    CompanyProfileUpdateView,
    companyprofile_activate,
)

from .views.contractors import (
    ContractorListView,
    ContractorCreateView,
    ContractorDetailView,
    ContractorUpdateView,
    ContractorDeleteView,
    contractor_w9,
    contractor_w9_admin,
)

app_name = "money"

urlpatterns = [
    # ---------------------------------------------------------------------
    # Dashboard
    # ---------------------------------------------------------------------
    path("dashboard/", Dashboard.as_view(), name="dashboard"),

    # ---------------------------------------------------------------------
    # Transactions
    # ---------------------------------------------------------------------
    path("transactions/", Transactions.as_view(), name="transactions"),
    path("transaction/add/", TransactionCreateView.as_view(), name="add_transaction"),
    path("transaction/success/", add_transaction_success, name="add_transaction_success"),
    path("transaction/<int:pk>/", TransactionDetailView.as_view(), name="transaction_detail"),
    path("transaction/edit/<int:pk>/", TransactionUpdateView.as_view(), name="edit_transaction"),
    path("transaction/delete/<int:pk>/", TransactionDeleteView.as_view(), name="delete_transaction"),
    path("transactions/export/", export_transactions_csv, name="export_transactions_csv"),

    # ---------------------------------------------------------------------
    # Recurring Transactions
    # ---------------------------------------------------------------------
    path("recurring/", RecurringTransactionListView.as_view(), name="recurring_transaction_list"),
    path("recurring/add/", RecurringTransactionCreateView.as_view(), name="recurring_add"),
    path("recurring/<int:pk>/edit/", RecurringTransactionUpdateView.as_view(), name="recurring_edit"),
    path("recurring/<int:pk>/delete/", RecurringTransactionDeleteView.as_view(), name="recurring_delete"),
    path("recurring/report/", recurring_report_view, name="recurring_report"),
    path("run-monthly-recurring/", run_monthly_recurring_view, name="run_monthly_recurring"),

    # ---------------------------------------------------------------------
    # Invoices (V2 invoice CRUD)
    # ---------------------------------------------------------------------
    path("invoices/v2/new/", invoice_v2_create, name="invoice_v2_create"),
    path("invoices/v2/<int:pk>/", InvoiceV2DetailView.as_view(), name="invoice_v2_detail"),
    path("invoices/v2/<int:pk>/edit/", invoice_v2_update, name="invoice_v2_edit"),
    path("invoices/v2/<int:pk>/delete/", InvoiceV2DeleteView.as_view(), name="invoice_v2_delete"),
    path("invoices/v2/<int:pk>/mark-paid/", InvoiceV2MarkPaidView.as_view(), name="invoice_v2_mark_paid"),
    path("invoices/v2/<int:pk>/issue/", InvoiceV2IssueView.as_view(), name="invoice_v2_issue"),
    path("invoices/v2/<int:pk>/pdf/", invoice_v2_pdf_view, name="invoice_v2_pdf"),
    path("invoices/v2/<int:pk>/send-email/", invoice_v2_send_email, name="invoice_v2_send_email"),
    path("invoices/v2/<int:pk>/review/", invoice_v2_review, name="invoice_v2_review"),
    path("invoices/", InvoiceV2ListView.as_view(), name="invoice_list"),

    path("invoices-v2/suggest-number/", invoice_v2_suggest_number, name="invoice_v2_suggest_number"),

    # ---------------------------------------------------------------------
    # Clients
    # ---------------------------------------------------------------------
    path("clients/", ClientListView.as_view(), name="client_list"),
    path("clients/add/", ClientCreateView.as_view(), name="add_client"),
    path("clients/edit/<int:pk>/", ClientUpdateView.as_view(), name="edit_client"),
    path("client/delete/<int:pk>/", ClientDeleteView.as_view(), name="delete_client"),

    # ---------------------------------------------------------------------
    # Reports (landing + business reports)
    # Canonical routes live under /reports/...
    # ---------------------------------------------------------------------
    path("reports/", reports_page, name="reports"),

    # Profit & Loss
    path("reports/profit-loss/", profit_loss, name="profit_loss"),
    path("reports/profit-loss/pdf/<int:year>/", profit_loss_pdf, name="profit_loss_pdf"),
    path("reports/profit-loss/yoy/", profit_loss_yoy, name="profit_loss_yoy"),
    path("reports/profit-loss/yoy/pdf/", profit_loss_yoy_pdf, name="profit_loss_yoy_pdf"),

    # Category Summary
    path("reports/category-summary/", category_summary, name="category_summary"),
    path("reports/category-summary/pdf/", category_summary_pdf, name="category_summary_pdf"),

    # NHRA / Race Expense
    path("reports/nhra-summary/", nhra_summary, name="nhra_summary"),
    path("reports/race-expense-report/", nhra_summary_report, name="nhra_summary_report"),
    path("reports/race-expense-report/pdf/", nhra_summary_report_pdf, name="nhra_summary_report_pdf"),

    # Travel
    path("reports/travel-analysis/", travel_expense_analysis, name="travel_expense_analysis"),
    path("reports/travel-analysis/pdf/", travel_expense_analysis_pdf, name="travel_expense_analysis_pdf"),
    path("reports/travel-summary/", travel_summary, name="travel_summary"),
    path("reports/travel-summary/pdf/", travel_summary_pdf_preview, name="travel_summary_pdf_preview"),
    path("reports/travel-summary/pdf/download/", travel_summary_pdf_download, name="travel_summary_pdf_download"),
   path("jobs/<int:pk>/review/", JobReviewView.as_view(), name="job_review"),
    # ---------------------------------------------------------------------
    # Legacy report aliases (safe to keep while migrating templates / bookmarks)
    # IMPORTANT: Do not use these in templates going forward.
    # ---------------------------------------------------------------------
    path("category-summary/", category_summary, name="legacy_category_summary"),
    path("category-summary/pdf/", category_summary_pdf, name="legacy_category_summary_pdf"),
    path("nhra-summary/", nhra_summary, name="legacy_nhra_summary"),
    path("race-expense-report/", nhra_summary_report, name="legacy_race_expense_report"),
    path("race-expense-report/pdf/", nhra_summary_report_pdf, name="legacy_race_expense_report_pdf"),

    # If you previously used these naming conventions for PDFs:
    path("financial-statement/pdf/<int:year>/", profit_loss_pdf, name="legacy_financial_statement_pdf"),

    # ---------------------------------------------------------------------
    # Tax reports (tax-adjusted)
    # ---------------------------------------------------------------------
    path("tax/profit-loss/", tax_profit_loss, name="tax_profit_loss"),
    path("tax/category-summary/", tax_category_summary, name="tax_category_summary"),
    path("taxes/schedule-c/", schedule_c_summary, name="schedule_c_summary"),
    path("tax/reports/profit-loss/", tax_profit_loss, name="tax_profit_loss",),
    path("tax/reports/profit-loss/pdf/<int:year>/", tax_profit_loss_pdf, name="tax_profit_loss_pdf",),
    path("tax/reports/profit-loss/yoy/", tax_profit_loss_yoy, name="tax_profit_loss_yoy",),
    path("tax/reports/profit-loss/yoy/pdf/", tax_profit_loss_yoy_pdf, name="tax_profit_loss_yoy_pdf",),
    path("form-4797/", form_4797_view, name="form_4797"),
    path("form-4797/pdf/", form_4797_pdf, name="form_4797_pdf"),

    # ---------------------------------------------------------------------
    # Category & SubCategory CRUD
    # ---------------------------------------------------------------------
    path("category-report/", CategoryListView.as_view(), name="category_page"),
    path("category/add/", CategoryCreateView.as_view(), name="add_category"),
    path("category/edit/<int:pk>/", CategoryUpdateView.as_view(), name="edit_category"),
    path("category/delete/<int:pk>/", CategoryDeleteView.as_view(), name="delete_category"),
    path("sub_category/add/", SubCategoryCreateView.as_view(), name="add_sub_category"),
    path("sub_category/edit/<int:pk>/", SubCategoryUpdateView.as_view(), name="edit_sub_category"),
    path("sub_category/delete/<int:pk>/", SubCategoryDeleteView.as_view(), name="delete_sub_category"),

    # ---------------------------------------------------------------------
    # Mileage
    # ---------------------------------------------------------------------
    path("mileage/add/", MileageCreateView.as_view(), name="mileage_create"),
    path("mileage/<int:pk>/edit/", MileageUpdateView.as_view(), name="mileage_update"),
    path("mileage/<int:pk>/delete/", MileageDeleteView.as_view(), name="mileage_delete"),
    path("mileage/update-rate/", update_mileage_rate, name="update_mileage_rate"),
    path("mileage/export/csv/", export_mileage_csv, name="export_mileage_csv"),
    path("mileage-log/", mileage_log, name="mileage_log"),
    path("taxes/mileage/report/pdf/", mileage_report_pdf, name="mileage_report_pdf"),

    # ---------------------------------------------------------------------
    # Vehicles
    # ---------------------------------------------------------------------
    path("vehicles/<int:pk>/", VehicleDetailView.as_view(), name="vehicle_detail"),
    path("vehicles/", VehicleListView.as_view(), name="vehicle_list"),
    path("vehicles/add/", VehicleCreateView.as_view(), name="vehicle_add"),
    path("vehicles/<int:pk>/edit/", VehicleUpdateView.as_view(), name="vehicle_edit"),
    path("vehicles/<int:pk>/delete/", VehicleDeleteView.as_view(), name="vehicle_delete"),

    # ---------------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------------
    path("events/", EventListView.as_view(), name="event_list"),
    path("events/add/", EventCreateView.as_view(), name="create_event"),
    path("events/<int:pk>/edit/", EventUpdateView.as_view(), name="event_update"),
    path("events/<int:pk>/", EventDetailView.as_view(), name="event_detail"),
    path("events/<int:pk>/review/", JobReviewView.as_view(), name="job_review"),
    path("events/<int:pk>/delete/", EventDeleteView.as_view(), name="event_delete"),



    # ---------------------------------------------------------------------
    # Company Profiles
    # ---------------------------------------------------------------------
    path("company-profiles/", CompanyProfileListView.as_view(), name="companyprofile_list"),
    path("company-profiles/new/", CompanyProfileCreateView.as_view(), name="companyprofile_create"),
    path("company-profiles/<int:pk>/", CompanyProfileDetailView.as_view(), name="companyprofile_detail"),
    path("company-profiles/<int:pk>/edit/", CompanyProfileUpdateView.as_view(), name="companyprofile_update"),
    path("company-profiles/<int:pk>/delete/", CompanyProfileDeleteView.as_view(), name="companyprofile_delete"),
    path("company-profiles/<int:pk>/activate/", companyprofile_activate, name="companyprofile_activate"),
    
    # ---------------------------------------------------------------------
    # Contractors (W-9 / 1099)
    # ---------------------------------------------------------------------
    path("contractors/", ContractorListView.as_view(), name="contractor_list"),
    path("contractors/add/", ContractorCreateView.as_view(), name="contractor_add"),
    path("contractors/<int:pk>/", ContractorDetailView.as_view(), name="contractor_detail"),
    path("contractors/<int:pk>/edit/", ContractorUpdateView.as_view(), name="contractor_edit"),
    path("contractors/<int:pk>/delete/", ContractorDeleteView.as_view(), name="contractor_delete"),
    
    path("contractors/w9/<str:token>/", contractor_w9, name="contractor_w9"),
    path("contractors/<int:pk>/w9/", contractor_w9_admin, name="contractor_w9_admin"),

]

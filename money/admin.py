from django.contrib import admin, messages
from django.utils.safestring import mark_safe

from .models import (
    Client,
    ClientProfile,
    Invoice,
    InvoiceItem,
    InvoiceV2,
    InvoiceItemV2,
    MileageRate,
    Miles,
    RecurringTransaction,
    Service,
    Team,
    Category,
    SubCategory,
    Transaction,
    Event,
)

# -----------------------------
# Core money app admin classes
# -----------------------------


class TransactionAdmin(admin.ModelAdmin):
    list_display = ["date", "category", "sub_cat", "transaction", "event", "invoice_number"]
    list_filter = ("category", "sub_cat", "event", "date")
    search_fields = ("transaction", "invoice_number")


class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "id"]
    search_fields = ("name",)


class InvoiceAdmin(admin.ModelAdmin):
    """
    Legacy Invoice admin (keep as-is for historical access).
    """
    list_display = ("invoice_number", "client", "amount", "status", "paid_date", "days_to_pay")
    list_filter = ("status", "client", "date")
    search_fields = ("invoice_number", "client__business", "event_name")

    def days_to_pay(self, obj):
        return obj.days_to_pay if getattr(obj, "days_to_pay", None) is not None else "-"

    days_to_pay.short_description = "Days to Pay"


class CategoryAdmin(admin.ModelAdmin):
    list_display = ["category", "id", "schedule_c_line"]
    search_fields = ("category",)


class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ["sub_cat", "id", "category"]
    list_filter = ("category",)
    search_fields = ("sub_cat",)


class RecurringTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction",
        "id",
        "amount",
        "day",
        "category",
        "sub_cat",
        "user",
        "active",
        "last_created",
    )
    list_filter = ("active", "day", "category", "sub_cat")
    search_fields = ("transaction", "user__username")


class ClientAdmin(admin.ModelAdmin):
    list_display = ("id", "business", "email", "first", "last")
    search_fields = ("business", "email", "first", "last")


class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title")
    search_fields = ("title",)


# -----------------------------
# ClientProfile admin (branding)
# -----------------------------


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = (
        "display_name_or_legal",
        "slug",
        "city",
        "state_province",
        "postal_code",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "state_province", "city")
    search_fields = (
        "legal_name",
        "display_name",
        "slug",
        "city",
        "postal_code",
        "support_email",
    )
    ordering = ("-is_active", "slug")
    actions = ("make_active",)

    readonly_fields = ("created_at", "updated_at", "logo_preview")
    # Make slug read-only after first save (see get_readonly_fields)
    fieldsets = (
        ("Identity & Branding", {
            "fields": (
                ("slug",),
                ("legal_name", "display_name"),
                ("logo", "logo_light", "logo_dark"),
                ("logo_alt_text",),
                ("brand_color_primary", "brand_color_secondary"),
                ("website",),
                ("logo_preview",),
            )
        }),
        ("Address & Contact", {
            "fields": (
                ("address_line1", "address_line2"),
                ("city", "state_province", "postal_code"),
                ("country",),
                ("main_phone", "support_email", "invoice_reply_to_email"),
                ("billing_contact_name", "billing_contact_email"),
            )
        }),
        ("Tax & Remittance", {
            "fields": (
                ("tax_id_ein",),
                ("pay_to_name",),
                ("remittance_address",),
            )
        }),
        ("Invoice Defaults", {
            "fields": (
                ("default_terms", "default_net_days"),
                ("default_late_fee_policy",),
                ("default_footer_text",),
                ("default_currency", "default_locale", "timezone"),
                ("pdf_header_layout", "header_logo_max_width_px"),
   
            )
        }),
        ("Status", {
            "fields": (("is_active",), ("created_at", "updated_at")),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj:  # editing existing instance
            ro.append("slug")  # enforce immutability in the admin too
        return ro

    @admin.display(description="Client")
    def display_name_or_legal(self, obj: ClientProfile):
        return obj.display_name or obj.legal_name

    @admin.display(description="Logo preview")
    def logo_preview(self, obj: ClientProfile):
        if not obj or not obj.logo:
            return "—"
        # Keep it small to avoid bloating the change form
        return mark_safe(
            f'<img src="{obj.logo.url}" '
            f'style="max-width: 240px; height:auto; border:1px solid #ddd; '
            f'padding:4px; border-radius:6px;" />'
        )

    @admin.action(description="Mark selected as Active (enforce single active profile)")
    def make_active(self, request, queryset):
        # Allow only one selection for clarity
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one profile to activate.",
                level=messages.WARNING,
            )
            return
        active_obj = queryset.first()
        # Deactivate others
        ClientProfile.objects.exclude(pk=active_obj.pk).update(is_active=False)
        # Activate target
        active_obj.is_active = True
        active_obj.full_clean()  # will run model.clean validations
        active_obj.save(update_fields=["is_active", "updated_at"])
        self.message_user(
            request,
            f"Activated: {active_obj}",
            level=messages.SUCCESS,
        )

    def save_model(self, request, obj, form, change):
        # If this is being saved active=True, ensure all others become inactive
        super().save_model(request, obj, form, change)
        if obj.is_active:
            ClientProfile.objects.exclude(pk=obj.pk).update(is_active=False)


# -----------------------------
# InvoiceV2 + InvoiceItemV2 admin
# -----------------------------


class InvoiceItemV2Inline(admin.TabularInline):
    """
    Inline items for InvoiceV2.
    User selects sub_cat; category is auto-derived in the model.
    """
    model = InvoiceItemV2
    extra = 1
    fields = ("description", "qty", "price", "sub_cat", "line_total_display")
    readonly_fields = ("line_total_display",)

    def line_total_display(self, obj):
        if not obj.pk:
            return ""
        return obj.line_total

    line_total_display.short_description = "Line total"


@admin.register(InvoiceV2)
class InvoiceV2Admin(admin.ModelAdmin):
    inlines = [InvoiceItemV2Inline]

    list_display = (
        "invoice_number",
        "client",
        "event",
        "date",
        "due",
        "status",
        "amount",
        "is_paid",
        "net_income_display",
    )
    list_filter = (
        "status",
        "client",
        "event",
        "date",
    )
    search_fields = (
        "invoice_number",
        "client__business",
        "client__first",
        "client__last",
        "event_name",
        "location",
    )
    date_hierarchy = "date"
    ordering = ("-date", "invoice_number")

    readonly_fields = (
        "amount",
        "issued_at",
        "version",
        "pdf_url",
        "pdf_sha256",
        "net_income_display",
    )

    actions = ("mark_as_paid_from_items",)

    fieldsets = (
        ("Identity", {
            "fields": (
                "invoice_number",
                "client",
                "event",
                "event_name",
                "location",
                "service",
            )
        }),
        ("Dates & Status", {
            "fields": (
                "date",
                "due",
                "paid_date",
                "status",
            )
        }),
        ("Money", {
            "fields": (
                "amount",
                "net_income_display",
            )
        }),
        ("From Snapshot", {
            "classes": ("collapse",),
            "fields": (
                "from_name",
                "from_address",
                "from_phone",
                "from_email",
                "from_website",
                "from_tax_id",
                "from_logo_url",
                "from_header_logo_max_width_px",
                "from_terms",
                "from_net_days",
                "from_footer_text",
                "from_currency",
                "from_locale",
                "from_timezone",
            ),
        }),
        ("Issuance / Archiving", {
            "classes": ("collapse",),
            "fields": (
                "issued_at",
                "version",
                "pdf_url",
                "pdf_sha256",
            ),
        }),
    )

    def net_income_display(self, obj):
        return obj.net_income

    net_income_display.short_description = "Net income"

    @admin.action(description="Mark selected as Paid (use SubCategory from items)")
    def mark_as_paid_from_items(self, request, queryset):
        """
        Mark selected invoices as Paid and create matching income Transactions.

        Uses the SubCategory from the first invoice item to determine the
        income category/subcategory for each invoice.
        """
        success_count = 0
        skipped_count = 0
        error_count = 0

        for invoice in queryset:
            if invoice.is_paid:
                skipped_count += 1
                continue
            try:
                invoice.mark_as_paid(user=request.user)
                success_count += 1
            except Exception as exc:
                error_count += 1
                self.message_user(
                    request,
                    f"Error processing Invoice {invoice.invoice_number or invoice.pk}: {exc}",
                    level=messages.ERROR,
                )

        if success_count:
            self.message_user(
                request,
                f"{success_count} invoice(s) marked as Paid and income transaction created.",
                level=messages.SUCCESS,
            )
        if skipped_count:
            self.message_user(
                request,
                f"{skipped_count} invoice(s) were already marked as Paid and were skipped.",
                level=messages.INFO,
            )


@admin.register(InvoiceItemV2)
class InvoiceItemV2Admin(admin.ModelAdmin):
    list_display = (
        "invoice",
        "description",
        "qty",
        "price",
        "line_total_display",
        "sub_cat",
        "category",
    )
    list_filter = ("invoice__client", "sub_cat", "category")
    search_fields = ("description", "invoice__invoice_number")

    def line_total_display(self, obj):
        return obj.line_total

    line_total_display.short_description = "Line total"


# -----------------------------
# Register remaining models
# -----------------------------

admin.site.register(Client, ClientAdmin)
admin.site.register(InvoiceItem)
admin.site.register(MileageRate)
admin.site.register(Service)
admin.site.register(Team, TeamAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(SubCategory, SubCategoryAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(Miles)
admin.site.register(RecurringTransaction, RecurringTransactionAdmin)
admin.site.register(Invoice, InvoiceAdmin)  # legacy
admin.site.register(Event, EventAdmin)

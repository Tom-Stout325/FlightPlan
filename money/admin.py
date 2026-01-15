# money/admin.py

from __future__ import annotations

from django.contrib import admin, messages
from django.core.exceptions import FieldDoesNotExist
from django.utils.safestring import mark_safe

from .models import (
    Category,
    Client,
    CompanyProfile,
    Event,
    InvoiceItemV2,
    InvoiceV2,
    MileageRate,
    Miles,
    RecurringTransaction,
    Service,
    SubCategory,
    Team,
    Transaction,
    Vehicle,
    VehicleExpense,
    VehicleYear,
)


# ------------------------------------------------------------------------------
# Shared helpers / mixins
# ------------------------------------------------------------------------------

class UserScopedAdminMixin:
    """
    Ensures:
    - list_display includes a "User" column (via user_display)
    - non-superusers only see their own rows (when we can infer ownership)
    """

    # If a model does NOT have `user`, you can set a relation path here (e.g. "invoice__user")
    owner_rel: str | None = None

    def _model_has_field(self, field_name: str) -> bool:
        try:
            self.model._meta.get_field(field_name)
            return True
        except FieldDoesNotExist:
            return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        # Direct user FK
        if self._model_has_field("user"):
            return qs.filter(user=request.user)

        # Related-owner path
        if self.owner_rel:
            return qs.filter(**{self.owner_rel: request.user})

        # No scoping possible (e.g. truly global config)
        return qs

    @admin.display(description="User")
    def user_display(self, obj):
        """
        Best-effort display of ownership:
        - obj.user if present
        - common related patterns (invoice.user, vehicle.user, client.user, event.user)
        - if no user exists, show em dash
        """
        # direct
        u = getattr(obj, "user", None)
        if u:
            return u

        # common relations
        for attr in ("invoice", "vehicle", "client", "event"):
            rel = getattr(obj, attr, None)
            if rel is not None:
                rel_user = getattr(rel, "user", None)
                if rel_user:
                    return rel_user

        return "—"


class UserScopedFKMixin(UserScopedAdminMixin):
    """
    Additionally scopes common FK dropdowns by request.user for non-superusers.
    Override `fk_user_map` to add/adjust field->queryset mapping.
    """

    fk_user_map: dict[str, tuple[object, dict]] = {}

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name in self.fk_user_map:
            model_cls, extra_filters = self.fk_user_map[db_field.name]
            base = {"user": request.user}
            base.update(extra_filters or {})
            kwargs["queryset"] = model_cls.objects.filter(**base)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ------------------------------------------------------------------------------
# Transactions
# ------------------------------------------------------------------------------

@admin.register(Transaction)
class TransactionAdmin(UserScopedFKMixin, admin.ModelAdmin):
    fk_user_map = {
        "category": (Category, {}),
        "sub_cat": (SubCategory, {}),
        "event": (Event, {}),
        "team": (Team, {}),
    }

    list_display = (
        "user_display",
        "date",
        "trans_type",
        "category",
        "sub_cat",
        "transaction",
        "event",
        "invoice_number",
        "amount",
        "deductible_amount_display",
    )
    list_filter = ("trans_type", "category", "sub_cat", "event", "date")
    search_fields = ("transaction", "invoice_number", "user__username", "user__email")
    date_hierarchy = "date"
    ordering = ("-date",)

    @admin.display(description="Deductible")
    def deductible_amount_display(self, obj):
        return obj.deductible_amount

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Admin UX polish:
        - If a category is selected (on add/edit), only show subcategories in that category.
        - Still user-scoped for non-superusers.
        """
        if db_field.name == "sub_cat":
            category_id = request.POST.get("category") or request.GET.get("category")

            qs = SubCategory.objects.all()
            if not request.user.is_superuser and hasattr(SubCategory, "user"):
                qs = qs.filter(user=request.user)

            if category_id and str(category_id).isdigit():
                qs = qs.filter(category_id=int(category_id)).order_by("sub_cat")
            else:
                qs = qs.order_by("category__category", "sub_cat")

            kwargs["queryset"] = qs

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ------------------------------------------------------------------------------
# Lookup models
# ------------------------------------------------------------------------------

@admin.register(Team)
class TeamAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "name", "id")
    search_fields = ("name", "user__username", "user__email")
    ordering = ("name",)


@admin.register(Service)
class ServiceAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "service", "id")
    search_fields = ("service", "user__username", "user__email")
    ordering = ("service",)


@admin.register(Event)
class EventAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "id", "title", "event_year", "event_type")
    search_fields = ("title", "user__username", "user__email")
    list_filter = ("event_year", "event_type")
    ordering = ("-event_year", "title")


@admin.register(Category)
class CategoryAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "category", "category_type", "schedule_c_line", "id")
    list_filter = ("category_type", "schedule_c_line")
    search_fields = ("category", "user__username", "user__email")
    ordering = ("category_type", "category")


@admin.register(SubCategory)
class SubCategoryAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "sub_cat", "category", "include_in_tax_reports", "schedule_c_line")
    list_filter = ("include_in_tax_reports", "category", "schedule_c_line")
    search_fields = ("sub_cat", "slug", "user__username", "user__email")
    ordering = ("category__category", "sub_cat")


@admin.register(Client)
class ClientAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "id", "business", "email", "first", "last")
    search_fields = ("business", "email", "first", "last", "user__username", "user__email")
    ordering = ("business", "last", "first")


# ------------------------------------------------------------------------------
# CompanyProfile (branding)
# NOTE: If CompanyProfile is deployment-level and has no user FK, user_display will show "—".
# ------------------------------------------------------------------------------

@admin.register(CompanyProfile)
class CompanyProfileAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "user_display",
        "display_name_or_legal",
        "slug",
        "is_active",
        "vehicle_expense_method",
        "updated_at",
    )
    list_filter = ("is_active", "state_province", "city")
    search_fields = (
        "legal_name",
        "display_name",
        "slug",
        "vehicle_expense_method",
    )
    ordering = ("-is_active", "slug")
    actions = ("make_active",)

    readonly_fields = ("created_at", "updated_at", "logo_preview")

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
                ("vehicle_expense_method",),
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
        if obj:
            ro.append("slug")
        return ro

    @admin.display(description="Company")
    def display_name_or_legal(self, obj: CompanyProfile):
        return obj.display_name or obj.legal_name

    @admin.display(description="Logo preview")
    def logo_preview(self, obj: CompanyProfile):
        if not obj or not getattr(obj, "logo", None):
            return "—"
        return mark_safe(
            f'<img src="{obj.logo.url}" '
            f'style="max-width: 240px; height:auto; border:1px solid #ddd; '
            f'padding:4px; border-radius:6px;" />'
        )

    @admin.action(description="Mark selected as Active (enforce single active profile)")
    def make_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one profile to activate.", level=messages.WARNING)
            return

        active_obj = queryset.first()
        CompanyProfile.objects.exclude(pk=active_obj.pk).update(is_active=False)

        active_obj.is_active = True
        active_obj.full_clean()
        active_obj.save(update_fields=["is_active", "updated_at"])

        self.message_user(request, f"Activated: {active_obj}", level=messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.is_active:
            CompanyProfile.objects.exclude(pk=obj.pk).update(is_active=False)


# ------------------------------------------------------------------------------
# InvoiceV2 + InvoiceItemV2
# ------------------------------------------------------------------------------

class InvoiceItemV2Inline(admin.TabularInline):
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
class InvoiceV2Admin(UserScopedFKMixin, admin.ModelAdmin):
    fk_user_map = {
        "client": (Client, {}),
        "event": (Event, {}),
        "service": (Service, {}),
    }

    inlines = [InvoiceItemV2Inline]

    list_display = (
        "user_display",
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
    list_filter = ("status", "client", "event", "date")
    search_fields = (
        "invoice_number",
        "client__business",
        "client__first",
        "client__last",
        "user__username",
        "user__email",
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
        if error_count and not success_count:
            self.message_user(request, "No invoices were updated due to errors.", level=messages.ERROR)


@admin.register(InvoiceItemV2)
class InvoiceItemV2Admin(UserScopedAdminMixin, admin.ModelAdmin):
    # InvoiceItemV2 is owned via invoice.user
    owner_rel = "invoice__user"

    list_display = ("user_display", "invoice", "description", "qty", "price", "line_total_display", "sub_cat", "category")
    list_filter = ("invoice__client", "sub_cat", "category")
    search_fields = ("description", "invoice__invoice_number", "invoice__user__username", "invoice__user__email")
    ordering = ("invoice", "id")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("invoice", "invoice__user", "sub_cat", "category")
        if request.user.is_superuser:
            return qs
        return qs.filter(invoice__user=request.user)

    def line_total_display(self, obj):
        return obj.line_total

    line_total_display.short_description = "Line total"


# ------------------------------------------------------------------------------
# Mileage models
# ------------------------------------------------------------------------------

@admin.register(MileageRate)
class MileageRateAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = ("user_display", "year", "rate", "id")
    list_filter = ("year",)
    search_fields = ("year", "user__username", "user__email")
    ordering = ("-year",)


class VehicleYearInline(admin.TabularInline):
    model = VehicleYear
    extra = 0
    fields = ("tax_year", "begin_mileage", "end_mileage")
    ordering = ("-tax_year",)


class VehicleExpenseInline(admin.TabularInline):
    model = VehicleExpense
    extra = 0
    fields = ("date", "expense_type", "description", "vendor", "amount", "odometer", "is_tax_related")
    ordering = ("-date",)
    show_change_link = True


@admin.register(Vehicle)
class VehicleAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "user_display",
        "name",
        "year",
        "make",
        "model",
        "plate",
        "is_active",
        "placed_in_service_date",
        "placed_in_service_mileage",
    )
    list_filter = ("is_active", "year", "make")
    search_fields = ("name", "plate", "vin", "make", "model", "user__username", "user__email")
    inlines = [VehicleYearInline, VehicleExpenseInline]
    ordering = ("-is_active", "name")


@admin.register(VehicleYear)
class VehicleYearAdmin(UserScopedFKMixin, admin.ModelAdmin):
    owner_rel = "vehicle__user"
    fk_user_map = {"vehicle": (Vehicle, {})}

    list_display = ("user_display", "vehicle", "tax_year", "begin_mileage", "end_mileage")
    list_filter = ("tax_year",)
    search_fields = ("vehicle__name", "vehicle__plate", "vehicle__vin", "vehicle__user__username", "vehicle__user__email")
    ordering = ("-tax_year", "vehicle")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("vehicle", "vehicle__user")
        if request.user.is_superuser:
            return qs
        return qs.filter(vehicle__user=request.user)


@admin.register(VehicleExpense)
class VehicleExpenseAdmin(UserScopedFKMixin, admin.ModelAdmin):
    fk_user_map = {"vehicle": (Vehicle, {})}

    list_display = ("user_display", "date", "vehicle", "expense_type", "description", "vendor", "amount", "odometer", "is_tax_related")
    list_filter = ("expense_type", "is_tax_related")
    search_fields = ("vehicle__name", "description", "vendor", "vehicle__plate", "vehicle__vin", "user__username", "user__email")
    date_hierarchy = "date"
    ordering = ("-date",)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("vehicle", "user", "vehicle__user")
        if request.user.is_superuser:
            return qs
        # VehicleExpense appears to have a direct user FK in your existing admin;
        # keep that behavior.
        return qs.filter(user=request.user)


@admin.register(Miles)
class MilesAdmin(UserScopedFKMixin, admin.ModelAdmin):
    fk_user_map = {
        "vehicle": (Vehicle, {"is_active": True}),
        "client": (Client, {}),
        "event": (Event, {}),
    }

    list_display = ("user_display", "date", "vehicle", "client", "event", "invoice_display", "begin", "end", "total", "mileage_type")
    list_filter = ("mileage_type", "vehicle", "client")
    search_fields = ("invoice_number", "event__title", "vehicle__name", "vehicle__plate", "user__username", "user__email")
    date_hierarchy = "date"
    ordering = ("-date",)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("vehicle", "client", "event", "invoice_v2", "user", "vehicle__user")
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    @admin.display(description="Invoice")
    def invoice_display(self, obj):
        if obj.invoice_v2:
            return obj.invoice_v2.invoice_number
        return obj.invoice_number or ""


# ------------------------------------------------------------------------------
# Recurring transactions
# ------------------------------------------------------------------------------

@admin.register(RecurringTransaction)
class RecurringTransactionAdmin(UserScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "user_display",
        "transaction",
        "id",
        "amount",
        "day",
        "category",
        "sub_cat",
        "active",
        "last_created",
    )
    list_filter = ("active", "day", "category", "sub_cat")
    search_fields = ("transaction", "user__username", "user__email")
    ordering = ("-active", "day", "id")



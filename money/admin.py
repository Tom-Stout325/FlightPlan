from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.utils.html import format_html
from .models import *
from money.models import ClientProfile 




    
class TransactionAdmin(admin.ModelAdmin):
    list_display    = ['date', 'category', 'sub_cat', 'transaction', 'event', 'invoice_number']
    

class TeamAdmin(admin.ModelAdmin):
    list_display    = ['name', 'id']
    
    
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client', 'amount', 'status', 'paid_date', 'days_to_pay')

    def days_to_pay(self, obj):
        return obj.days_to_pay if obj.days_to_pay is not None else "-"
    days_to_pay.short_description = "Days to Pay"


class CategoryAdmin(admin.ModelAdmin):
    list_display = ['category', 'id', 'schedule_c_line']
    search_fields = ('category',)


class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ['sub_cat', 'id', 'category']
    

class RecurringTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'id', 'amount', 'day', 'category', 'sub_cat', 'user', 'active', 'last_created')
    list_filter = ('active', 'day', 'category', 'sub_cat')
    search_fields = ('transaction', 'user__username')


class ClientAdmin(admin.ModelAdmin):
    list_display = ('id','business', 'email', 'first', 'last')
    
    
class EventAdmin(admin.ModelAdmin):
    list_display = ('id', 'title')
    





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
    search_fields = ("legal_name", "display_name", "slug", "city", "postal_code", "support_email")
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
                ("invoice_prefix",),
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
        return mark_safe(f'<img src="{obj.logo.url}" style="max-width: 240px; height:auto; border:1px solid #ddd; padding:4px; border-radius:6px;" />')

    @admin.action(description="Mark selected as Active (enforce single active profile)")
    def make_active(self, request, queryset):
        # Allow only one selection for clarity
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one profile to activate.", level=messages.WARNING)
            return
        active_obj = queryset.first()
        # Deactivate others
        ClientProfile.objects.exclude(pk=active_obj.pk).update(is_active=False)
        # Activate target
        active_obj.is_active = True
        active_obj.full_clean()  # will run model.clean validations
        active_obj.save(update_fields=["is_active", "updated_at"])
        self.message_user(request, f"Activated: {active_obj}", level=messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        # If this is being saved active=True, ensure all others become inactive
        super().save_model(request, obj, form, change)
        if obj.is_active:
            ClientProfile.objects.exclude(pk=obj.pk).update(is_active=False)




    
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
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(Event, EventAdmin)
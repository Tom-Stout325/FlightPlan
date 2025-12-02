from django.db import models

# Create your models here.
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from datetime import timedelta, date
from decimal import Decimal
from django.conf import settings
from decimal import Decimal
from django.utils.text import slugify
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone
from django.apps import apps
from django.db.models.functions import Cast
from django.db.models import IntegerField

from django.db.models import (
    F,
    Sum,
    DecimalField,
    ExpressionWrapper,
    Q
)

try:
    from django.contrib.postgres.indexes import GinIndex
    from django.contrib.postgres.search import SearchVectorField
except ImportError:
    GinIndex = None
    SearchVectorField = None



    

class Category(models.Model):
    category = models.CharField(max_length=500, blank=True, null=True)
    schedule_c_line = models.CharField(max_length=10, blank=True, null=True, help_text="Enter Schedule C line number (e.g., '8', '9', '27a')")
    
    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.category or "Unnamed Category"


class SubCategory(models.Model):
    sub_cat = models.CharField(max_length=500, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    schedule_c_line = models.CharField(max_length=10, blank=True, null=True, help_text="Enter Schedule C line number.")

    class Meta:
        verbose_name_plural = "Sub Categories"
        ordering = ['sub_cat']

    def __str__(self):
        return f"{self.category} - {self.sub_cat or 'Unnamed SubCategory'}"

    def save(self, *args, **kwargs):
        if not self.slug and self.sub_cat:
            self.slug = slugify(self.sub_cat)
        super().save(*args, **kwargs)




class Team(models.Model):
    name = models.CharField(max_length=50, blank=True, null=True)
   
    def __str__(self):
        return self.name
    
    
    

class Client(models.Model):
    business  = models.CharField(max_length=500, blank=True, null=True)
    first     = models.CharField(max_length=500, blank=True, null=True)
    last      = models.CharField(max_length=500, blank=True, null=True)
    street    = models.CharField(max_length=500, blank=True, null=True)
    address2  = models.CharField(max_length=500, blank=True, null=True)
    email     = models.EmailField(max_length=254)
    phone     = models.CharField(max_length=500, blank=True, null=True)
    
    def __str__(self):
        return self.business
    

class Event(models.Model):
    EVENT_TYPE_CHOICES = [
        ('race', 'Race'),
        ('event', 'Event'),
        ('other', 'Other'),
    ]

    title            = models.CharField(max_length=200)
    event_type       = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES, default='race')
    location_city    = models.CharField(max_length=200, blank=True, null=True)
    location_address = models.CharField(max_length=500, blank=True, null=True)
    notes            = models.TextField(blank=True, null=True)
    slug             = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        ordering = ['title']

    def save(self, *args, **kwargs):
        if not self.slug or self.slug.strip() == "":
            self.slug = slugify(f"{self.title}")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Service(models.Model):
    service = models.CharField(max_length=500, blank=True, null=True) 
    
    def __str__(self):
        return self.service






class InvoiceItem(models.Model):
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500) 
    qty = models.IntegerField(default=0, blank=True, null=True)
    price = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, blank=True, null=True)

    def __str__(self):
        return f"{self.description} - {self.qty} x {self.price}"

    @property
    def total(self):
        return (self.qty or 0) * (self.price or 0)
    
    
    
    
    
    
    
class Invoice(models.Model):
    # ------- existing core fields -------
    invoice_number = models.CharField(max_length=25, blank=True, null=True)
    client         = models.ForeignKey('Client', on_delete=models.PROTECT, related_name='invoices')
    event_name     = models.CharField(max_length=500, blank=True, null=True)
    location       = models.CharField(max_length=500, blank=True, null=True)
    event          = models.ForeignKey('Event', on_delete=models.PROTECT, default=1, related_name='invoices')
    service        = models.ForeignKey('Service', on_delete=models.PROTECT, related_name='invoices')
    amount         = models.DecimalField(default=0.00, max_digits=12, decimal_places=2, editable=False)
    date           = models.DateField()
    due            = models.DateField()
    paid_date      = models.DateField(null=True, blank=True)

    STATUS_CHOICES = [
        ('Unpaid', 'Unpaid'),
        ('Paid', 'Paid'),
        ('Partial', 'Partial'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unpaid')

    # Optional Postgres search vector (kept from your original)
    if SearchVectorField:
        search_vector = SearchVectorField(null=True, blank=True)

    # ------- NEW: immutable "From" snapshot (captured at create/issue time) -------
    from_name   = models.CharField(max_length=255, blank=True)
    from_address = models.TextField(blank=True)                 # multiline postal block
    from_phone  = models.CharField(max_length=50, blank=True)
    from_email  = models.EmailField(blank=True)
    from_website = models.URLField(blank=True)
    from_tax_id = models.CharField(max_length=64, blank=True)

    # Render/branding hints captured with the snapshot
    from_logo_url                    = models.URLField(blank=True)
    from_header_logo_max_width_px    = models.PositiveIntegerField(default=320)

    # Policy defaults captured at issue time
    from_terms       = models.CharField(max_length=100, blank=True)   # e.g., "Net 30"
    from_net_days    = models.PositiveIntegerField(default=30)
    from_footer_text = models.TextField(blank=True)

    # Formatting hints captured (useful for PDFs, currency symbols, etc.)
    from_currency = models.CharField(max_length=3, default="USD")
    from_locale   = models.CharField(max_length=10, default="en_US")
    from_timezone = models.CharField(max_length=64, default="America/Indiana/Indianapolis")

    # ------- NEW: issuance / archiving hooks (minimal) -------
    issued_at  = models.DateTimeField(null=True, blank=True)     # set when you officially "issue"
    version    = models.PositiveIntegerField(default=1)           # bump if you create a revision
    pdf_url    = models.URLField(
        blank=True,
        max_length=1000,
    )                      
    pdf_sha256 = models.CharField(max_length=64, blank=True)    
    class Meta:
        ordering = ['invoice_number']

    def __str__(self):
        return self.invoice_number or f"Invoice {self.pk}"

    # ------- totals -------
    def update_amount(self):
        """
        Recalculate the total invoice amount based on related items (qty * price).
        Relies on InvoiceItem with related_name='items'.
        """
        total = self.items.annotate(
            line_total=ExpressionWrapper(F('qty') * F('price'), output_field=DecimalField())
        ).aggregate(sum=Sum('line_total'))['sum'] or 0
        self.amount = total
        self.save()

    # ------- flags / convenience -------
    @property
    def is_paid(self):
        return self.paid_date is not None or self.status == 'Paid'

    @property
    def is_locked(self):
        """
        Consider the invoice 'locked' once issued (you can key your UI off this).
        """
        return bool(self.issued_at)

    @property
    def days_to_pay(self):
        if self.paid_date:
            return (self.paid_date - self.date).days
        return None

    @property
    def net_income(self):
        income = self.transactions.filter(trans_type='Income').aggregate(total=Sum('amount'))['total'] or 0
        expenses = self.transactions.filter(trans_type='Expense').aggregate(total=Sum('amount'))['total'] or 0
        return income - expenses

    # ------- NEW: snapshot helpers -------
    def has_from_snapshot(self) -> bool:
        """
        Returns True if the invoice already has a usable snapshot.
        """
        return bool(self.from_name or self.from_logo_url or self.from_address)

    def snapshot_from_profile(self, profile, absolute_logo_url: str | None = None, overwrite: bool = False):
        """
        Copy active ClientProfile details into this invoice's snapshot fields.
        Set overwrite=True ONLY if you explicitly want to replace an existing snapshot.
        """
        if not profile:
            return
        if self.has_from_snapshot() and not overwrite:
            return

        # Identity
        self.from_name = profile.name_for_display
        self.from_address = "\n".join(profile.full_address_lines())
        self.from_phone = profile.main_phone or ""
        self.from_email = profile.invoice_reply_to_email or profile.support_email or ""
        self.from_website = profile.website or ""
        self.from_tax_id = profile.tax_id_ein or ""

        # Branding / render hints
        if absolute_logo_url:
            self.from_logo_url = absolute_logo_url
        else:
            try:
                self.from_logo_url = profile.logo.url or ""
            except Exception:
                self.from_logo_url = ""
        self.from_header_logo_max_width_px = profile.header_logo_max_width_px

        # Policy defaults
        self.from_terms = profile.default_terms or ""
        self.from_net_days = int(getattr(profile, "default_net_days", 30) or 30)
        self.from_footer_text = profile.default_footer_text or ""

        # Formatting hints
        self.from_currency = profile.default_currency or "USD"
        self.from_locale = profile.default_locale or "en_US"
        self.from_timezone = profile.timezone or "America/Indiana/Indianapolis"



    
    
    
class Transaction(models.Model):
    TRANSPORT_CHOICES = [
        ('personal_vehicle', 'Personal Vehicle'),
        ('rental_car', 'Rental Car'),
    ]
    INCOME = 'Income'
    EXPENSE = 'Expense'

    TRANS_TYPE_CHOICES = [
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
        
    ]
    user               = models.ForeignKey(User, on_delete=models.CASCADE)
    trans_type         = models.CharField(max_length=10, choices=TRANS_TYPE_CHOICES, default=EXPENSE)
    category           = models.ForeignKey('Category', on_delete=models.PROTECT)
    sub_cat            = models.ForeignKey('SubCategory', on_delete=models.PROTECT, null=True, blank=True)
    amount             = models.DecimalField(max_digits=20, decimal_places=2)
    transaction        = models.CharField(max_length=255)
    team               = models.ForeignKey('Team', null=True, blank=True, on_delete=models.PROTECT)
    event              = models.ForeignKey('Event', null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    receipt            = models.FileField(upload_to='receipts/', blank=True, null=True)
    date               = models.DateField()
    invoice_number     = models.CharField(max_length=25, blank=True, null=True, help_text="Optional")
    recurring_template = models.ForeignKey('RecurringTransaction', null=True, blank=True, on_delete=models.SET_NULL, related_name='generated_transactions')
    transport_type     = models.CharField(max_length=30, choices=TRANSPORT_CHOICES, null=True, blank=True, help_text="Used to identify if actual expenses apply")
    
    class Meta:
        indexes = [
            models.Index(fields=['date', 'trans_type']),
            models.Index(fields=['user', 'date']),
            models.Index(fields=['event']),
            models.Index(fields=['category']),
            models.Index(fields=['sub_cat']),
            models.Index(fields=['invoice_number']),
        ]
        ordering = ['date']

    @property
    def deductible_amount(self):
        if self.sub_cat and self.sub_cat.slug == 'meals':
            return round(self.amount * Decimal('0.5'), 2)
        return self.amount

    def __str__(self):
        return f"{self.transaction} - {self.amount}"




class MileageRate(models.Model):
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.70)
    
    def __str__(self):
        return f"Current Mileage Rate: ${self.rate}"

    class Meta:
        verbose_name = "Mileage Rate"
        verbose_name_plural = "Mileage Rates"



# money/models.py (where Miles lives)

class Miles(models.Model):
    MILEAGE_TYPE_CHOICES = [
        ("Taxable", "Taxable"),
        ("Reimbursed", "Reimbursed"),
    ]

    user   = models.ForeignKey(User, on_delete=models.CASCADE)
    date   = models.DateField()

    begin  = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        validators=[MinValueValidator(0)],
    )
    end    = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        validators=[MinValueValidator(0)],
    )
    total  = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        editable=False,
    )

    client = models.ForeignKey("Client", on_delete=models.PROTECT)
    event  = models.ForeignKey(
        "Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Event this mileage was associated with (for event-level cost analysis).",
    )

    # 🔹 NEW: formal link to Invoice V2
    invoice_v2 = models.ForeignKey(
        "InvoiceV2",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mileage_entries",
        help_text="If set, this mileage entry is tied to an Invoice V2.",
    )

    # Legacy / denormalized string for older reports
    invoice_number = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Legacy invoice number string. For new entries, usually mirrors InvoiceV2.invoice_number.",
    )

    vehicle = models.CharField(
        max_length=255,
        blank=False,
        null=True,
        default="Lead Foot",
    )

    mileage_type = models.CharField(
        max_length=20,
        choices=MILEAGE_TYPE_CHOICES,
        default="Taxable",
    )

    class Meta:
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["mileage_type"]),
        ]
        verbose_name_plural = "Miles"
        ordering = ["-date"]

    def __str__(self):
        label = self.invoice_number or (self.invoice_v2.invoice_number if self.invoice_v2 else "No invoice")
        return f"{label} – {self.client} ({self.date})"





class RecurringTransaction(models.Model):
    INCOME = 'Income'
    EXPENSE = 'Expense'
    TRANS_TYPE_CHOICES = [(INCOME, 'Income'), (EXPENSE, 'Expense')]

    user            = models.ForeignKey(User, on_delete=models.CASCADE)
    trans_type      = models.CharField(max_length=10, choices=TRANS_TYPE_CHOICES, default=EXPENSE)
    category        = models.ForeignKey('Category', on_delete=models.PROTECT, null=True, blank=True, help_text="Auto-filled from Sub-Category.")
    sub_cat         = models.ForeignKey('SubCategory', on_delete=models.PROTECT, null=True, blank=True)
    amount          = models.DecimalField(max_digits=20, decimal_places=2)
    transaction     = models.CharField(max_length=255)
    day             = models.IntegerField(help_text="Day of the month to apply")
    team            = models.ForeignKey(Team, null=True, blank=True, on_delete=models.PROTECT)
    event           = models.ForeignKey('Event', null=True, blank=True, on_delete=models.PROTECT)
    receipt         = models.FileField(upload_to='receipts/', blank=True, null=True)
    active          = models.BooleanField(default=True)
    last_created    = models.DateField(null=True, blank=True)

    def clean(self):
        if self.sub_cat:
            self.category = self.sub_cat.category
        if not self.sub_cat and not self.category:
            raise ValidationError("Select either a Sub-Category or a Category.")

    def save(self, *args, **kwargs):
        if self.sub_cat:
            self.category = self.sub_cat.category
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction} - {self.amount} on day {self.day}"

    class Meta:
        indexes = [models.Index(fields=['user', 'day', 'active'])]




class Receipt(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='receipts')
    date = models.DateField(blank=True, null=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    event = models.ForeignKey('Event', null=True, blank=True, on_delete=models.SET_NULL)
    invoice_number = models.CharField(max_length=255, blank=True, null=True)
    receipt_file = models.FileField(upload_to='receipts/', blank=True, null=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Receipt: {self.transaction.transaction} - {self.amount or 'No Amount'}"



def logo_upload_path(instance, filename):
    # e.g., branding/airborne-images/logo.png
    slug = instance.slug or "default"
    return f"branding/{slug}/{filename}"

HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}){1,2}$",
    message="Enter a valid hex color like #000000 or #fff.",
)

def validate_image_extension_no_svg(value):
    """
    Prevent SVG uploads for logos; allow common raster formats.
    """
    name = getattr(value, "name", "") or ""
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    allowed = {"png", "jpg", "jpeg", "webp"}
    if ext not in allowed:
        raise ValidationError(f"Unsupported logo file type '.{ext}'. Allowed: {', '.join(sorted(allowed))}.")


PDF_HEADER_LAYOUT_CHOICES = [
    ("stacked", "Stacked (logo above address)"),
    ("inline-left", "Inline (logo left, address right)"),
    ("inline-right", "Inline (address left, logo right)"),
]

class ClientProfile(models.Model):
    """
    Per-deployment brand & 'From' identity. Exactly one may be active.
    """
    # Identity & branding
    slug = models.SlugField(
        unique=True,
        help_text="Short identifier for this client (e.g., 'airborne-images', 'skyguy')."
    )
    legal_name = models.CharField(
        max_length=255,
        help_text="Registered legal name used on invoices."
    )
    display_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Public/trade name; falls back to legal name if blank."
    )

    logo = models.ImageField(
        upload_to=logo_upload_path,
        validators=[validate_image_extension_no_svg],
        help_text="Primary logo used in invoice header."
    )
    logo_light = models.ImageField(
        upload_to=logo_upload_path, blank=True, null=True,
        validators=[validate_image_extension_no_svg],
        help_text="Optional light-mode logo variation."
    )
    logo_dark = models.ImageField(
        upload_to=logo_upload_path, blank=True, null=True,
        validators=[validate_image_extension_no_svg],
        help_text="Optional dark-mode logo variation."
    )
    logo_alt_text = models.CharField(
        max_length=255, blank=True,
        help_text="Accessible alt text for the logo image."
    )

    brand_color_primary = models.CharField(
        max_length=7, blank=True, validators=[HEX_COLOR_VALIDATOR],
        help_text="Primary brand color (hex), e.g., #0055FF."
    )
    brand_color_secondary = models.CharField(
        max_length=7, blank=True, validators=[HEX_COLOR_VALIDATOR],
        help_text="Secondary brand color (hex), optional."
    )
    website = models.URLField(blank=True)

    # Address & contact (postal identity)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state_province = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="United States")

    main_phone = models.CharField(max_length=50, blank=True)
    support_email = models.EmailField(blank=True)
    invoice_reply_to_email = models.EmailField(blank=True)

    # Billing contact (for AR / invoice reply-to)
    billing_contact_name = models.CharField(max_length=255, blank=True)
    billing_contact_email = models.EmailField(blank=True)

    # Tax
    tax_id_ein = models.CharField(
        max_length=64, blank=True,
        help_text="EIN / Tax ID as displayed on invoices (do not include sensitive PII)."
    )

    # Payments & remittance
    pay_to_name = models.CharField(
        max_length=255, blank=True,
        help_text="Name checks should be made payable to (defaults to legal_name if blank)."
    )
    remittance_address = models.TextField(
        blank=True,
        help_text="If different from primary address. Multiline allowed."
    )

    # Defaults for invoice creation
    default_terms = models.CharField(
        max_length=100, blank=True, help_text='e.g., "Net 30".'
    )
    default_net_days = models.PositiveIntegerField(default=30)
    default_late_fee_policy = models.CharField(
        max_length=255, blank=True,
        help_text='Short line like "1.5% per month after 30 days".'
    )
    default_footer_text = models.TextField(
        blank=True,
        help_text="Footer / legal disclaimers displayed on invoices."
    )

    # Rendering / formatting hints
    pdf_header_layout = models.CharField(
        max_length=20, choices=PDF_HEADER_LAYOUT_CHOICES, default="inline-left"
    )
    header_logo_max_width_px = models.PositiveIntegerField(
        default=320,
        help_text="Render hint for PDF header logo max width."
    )
    default_currency = models.CharField(max_length=3, default="USD")
    default_locale = models.CharField(max_length=10, default="en_US")
    timezone = models.CharField(max_length=64, default="America/Indiana/Indianapolis")

    # Activation & metadata
    is_active = models.BooleanField(
        default=False,
        help_text="Only one active profile allowed per deployment."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Enforce at most one active profile
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name="unique_active_client_profile",
            ),
        ]
        ordering = ["-is_active", "slug"]

    def __str__(self):
        return f"{self.display_name or self.legal_name} ({self.slug})"

    @property
    def name_for_display(self):
        return self.display_name or self.legal_name

    def full_address_lines(self):
        lines = [self.address_line1]
        if self.address_line2:
            lines.append(self.address_line2)
        city_line = ", ".join(filter(None, [self.city, self.state_province]))  # "City, ST"
        if self.postal_code:
            city_line = f"{city_line} {self.postal_code}" if city_line else self.postal_code
        if city_line:
            lines.append(city_line)
        if self.country:
            lines.append(self.country)
        return lines

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def clean(self):
        missing = []
        if self.is_active:
            if not self.legal_name:
                missing.append("legal_name")
            if not self.address_line1:
                missing.append("address_line1")
            if not self.city:
                missing.append("city")
            if not self.state_province:
                missing.append("state_province")
            if not self.postal_code:
                missing.append("postal_code")
            if not self.country:
                missing.append("country")
            if not self.logo:
                missing.append("logo")
        if missing:
            raise ValidationError({"__all__": f"Active profile requires fields: {', '.join(missing)}"})





# --------------------------------------------  N E W  M O D E L S ---------------------- #




class InvoiceV2(models.Model):
    """
    New invoice model, designed to coexist with legacy Invoice.
    - Invoice-centric
    - Multi-client friendly
    - Event is optional
    - Uses YYNNNN invoice numbering (YY = year, NNNN starts at 0100 each year)
    """

    # ---------- Identity & relationships ----------
    invoice_number = models.CharField(
        max_length=25,
        blank=True,
        null=True,
        help_text="Human-visible invoice ID (YYNNNN format; auto-generated if blank).",
    )
    client = models.ForeignKey(
        "Client",
        on_delete=models.PROTECT,
        related_name="invoices_v2",
    )
    event = models.ForeignKey(
        "Event",
        on_delete=models.PROTECT,
        related_name="invoices_v2",
        null=True,
        blank=True,
        help_text="Optional: link this invoice to a specific event/race.",
    )
    event_name = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Display name of the event at time of invoicing.",
    )
    location = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Display location (city/track) at time of invoicing.",
    )
    service = models.ForeignKey(
        "Service",
        on_delete=models.PROTECT,
        related_name="invoices_v2",
        help_text="Primary service for this invoice.",
    )

    # ---------- Money & dates ----------
    amount = models.DecimalField(
        default=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        editable=False,
        help_text="Total invoice amount, calculated from line items.",
    )
    date = models.DateField(
        help_text="Invoice date.",
    )
    due = models.DateField(
        help_text="Due date.",
    )
    paid_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date fully paid.",
    )

    STATUS_UNPAID = "Unpaid"
    STATUS_PAID = "Paid"
    STATUS_PARTIAL = "Partial"

    STATUS_CHOICES = [
        (STATUS_UNPAID, "Unpaid"),
        (STATUS_PAID, "Paid"),
        (STATUS_PARTIAL, "Partial"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNPAID,
    )

    # ---------- Issuance / archiving ----------
    issued_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the invoice is officially issued/sent.",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Revision number; bump when you create a new version.",
    )
    pdf_url = models.URLField(
        blank=True,
        max_length=1500,  # increased for S3 / long URLs
        help_text="Location of the archived PDF (e.g., S3).",
    )
    pdf_sha256 = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional SHA-256 hash of the archived PDF for integrity checks.",
    )

    # ---------- Email metadata ----------
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this invoice email was last sent.",
    )
    sent_to = models.EmailField(
        null=True,
        blank=True,
        help_text="Email address the invoice was last sent to.",
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoice_v2_emails_sent",
        help_text="User who last sent this invoice.",
    )

    # Optional Postgres search vector
    if SearchVectorField is not None:
        search_vector = SearchVectorField(null=True, blank=True)

    # ---------- Immutable "From" snapshot ----------
    from_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Business name as shown on this invoice.",
    )
    from_address = models.TextField(
        blank=True,
        help_text="Postal address block as printed on this invoice.",
    )
    from_phone = models.CharField(
        max_length=50,
        blank=True,
    )
    from_email = models.EmailField(
        blank=True,
    )
    from_website = models.URLField(
        blank=True,
    )
    from_tax_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Tax ID / EIN as shown on this invoice.",
    )

    # Branding / render hints
    from_logo_url = models.URLField(
        blank=True,
        help_text="Absolute or storage URL to logo used on this invoice.",
    )
    from_header_logo_max_width_px = models.PositiveIntegerField(
        default=320,
    )

    # Policy defaults captured at issue time
    from_terms = models.CharField(
        max_length=100,
        blank=True,
        help_text='e.g., "Net 30".',
    )
    from_net_days = models.PositiveIntegerField(
        default=30,
        help_text="Number of days from invoice date to due date when issued.",
    )
    from_footer_text = models.TextField(
        blank=True,
        help_text="Footer notes / payment instructions as shown on this invoice.",
    )

    # Formatting hints
    from_currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO currency code captured at issue time.",
    )
    from_locale = models.CharField(
        max_length=10,
        default="en_US",
    )
    from_timezone = models.CharField(
        max_length=64,
        default="America/Indiana/Indianapolis",
    )

    # ---------- Stored PDF snapshot ----------
    pdf_snapshot = models.FileField(
        upload_to="invoices_v2/",
        blank=True,
        null=True,
        help_text="Archived PDF snapshot stored in default storage.",
    )
    pdf_snapshot_created_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the snapshot was generated.",
    )

    class Meta:
        ordering = ["invoice_number"]
        constraints = [
            # Ensure invoice_number is unique when set
            models.UniqueConstraint(
                fields=["invoice_number"],
                name="uniq_invoicev2_number",
                condition=models.Q(invoice_number__isnull=False),
            )
        ]
        indexes = [
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["client", "date"]),
            models.Index(fields=["event", "date"]),
            models.Index(fields=["status"]),
        ]

    # ---------- String / basic helpers ----------
    def __str__(self):
        if self.invoice_number:
            return f"{self.invoice_number} ({self.client})"
        return f"InvoiceV2 #{self.pk} ({self.client})"

    @property
    def year(self) -> int:
        return self.date.year

    # ---------- Invoice number generator: YYNNNN ----------
    def _generate_invoice_number(self) -> str:
        """
        Generates invoice numbers like:
            YYNNNN
        where:
            YY   = last 2 digits of year
            NNNN = sequence starting at 0100 each year

        Example first invoice in 2026: 260100
        Next: 260101, 260102, etc.
        """
        year_short = str(self.date.year)[-2:]  # "2026" -> "26"
        prefix = year_short  # all numbers begin with YY

        last_invoice = (
            InvoiceV2.objects
            .filter(
                invoice_number__startswith=prefix,
                invoice_number__regex=r"^\d+$",  # only pure digits
            )
            .annotate(
                numeric_part=Cast("invoice_number", IntegerField())
            )
            .order_by("-numeric_part")
            .first()
        )

        if not last_invoice or not last_invoice.invoice_number:
            return f"{year_short}0100"

        try:
            last_number = int(last_invoice.invoice_number)
        except (TypeError, ValueError):
            # Fallback if something weird is in the DB
            return f"{year_short}0100"

        next_number = last_number + 1
        return str(next_number)

    def save(self, *args, **kwargs):
        """
        Auto-generate invoice_number if missing using the YYNNNN pattern.
        Requires self.date to be set.
        """
        if not self.invoice_number and self.date:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    # ---------- Totals ----------
    def update_amount(self, save: bool = True):
        """
        Recalculate the total invoice amount based on related items (qty * price).
        Relies on InvoiceItemV2 with related_name='items'.
        """
        total = (
            self.items.annotate(
                line_total=ExpressionWrapper(
                    F("qty") * F("price"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .aggregate(sum=Sum("line_total"))
            .get("sum")
            or Decimal("0.00")
        )
        self.amount = total
        if save:
            self.save(update_fields=["amount"])

    # ---------- Convenience flags ----------
    @property
    def is_paid(self) -> bool:
        return bool(self.paid_date) or self.status == self.STATUS_PAID

    @property
    def is_locked(self) -> bool:
        """
        Consider the invoice 'locked' once issued.
        You can key your UI off this to prevent major edits.
        """
        return bool(self.issued_at)

    @property
    def days_to_pay(self):
        if self.paid_date:
            return (self.paid_date - self.date).days
        return None

    @property
    def has_pdf_snapshot(self) -> bool:
        return bool(self.pdf_snapshot)

    # ---------- Snapshot helpers ----------
    def has_from_snapshot(self) -> bool:
        """
        Returns True if the invoice already has a usable 'from' snapshot.
        """
        return bool(self.from_name or self.from_logo_url or self.from_address)

    def snapshot_from_profile(
        self,
        profile,
        absolute_logo_url: str | None = None,
        overwrite: bool = False,
    ):
        """
        Copy active business/profile details into this invoice's snapshot fields.
        Set overwrite=True ONLY if you explicitly want to replace an existing snapshot.
        """
        if not profile:
            return
        if self.has_from_snapshot() and not overwrite:
            return

        # Identity
        self.from_name = getattr(profile, "name_for_display", "") or ""
        address_lines = []
        if hasattr(profile, "full_address_lines"):
            try:
                address_lines = profile.full_address_lines()
            except Exception:
                address_lines = []
        self.from_address = "\n".join(address_lines)
        self.from_phone = getattr(profile, "main_phone", "") or ""
        self.from_email = (
            getattr(profile, "invoice_reply_to_email", "")
            or getattr(profile, "support_email", "")
            or ""
        )
        self.from_website = getattr(profile, "website", "") or ""
        self.from_tax_id = getattr(profile, "tax_id_ein", "") or ""

        # Branding / render hints
        if absolute_logo_url:
            self.from_logo_url = absolute_logo_url
        else:
            logo_url = ""
            logo = getattr(profile, "logo", None)
            if logo is not None:
                try:
                    logo_url = logo.url
                except Exception:
                    logo_url = ""
            self.from_logo_url = logo_url

        self.from_header_logo_max_width_px = getattr(
            profile,
            "header_logo_max_width_px",
            self.from_header_logo_max_width_px,
        )

        # Policy defaults
        self.from_terms = getattr(profile, "default_terms", "") or ""
        default_net_days = getattr(profile, "default_net_days", self.from_net_days)
        self.from_net_days = int(default_net_days or 30)
        self.from_footer_text = getattr(profile, "default_footer_text", "") or ""

        # Formatting hints
        self.from_currency = getattr(profile, "default_currency", "") or "USD"
        self.from_locale = getattr(profile, "default_locale", "") or "en_US"
        self.from_timezone = getattr(
            profile,
            "timezone",
            "America/Indiana/Indianapolis",
        )

    # ---------- Review helper tied to Transactions ----------
    @property
    def net_income(self) -> Decimal:
        """
        Convenience helper for review screens.
        Uses the existing Transaction model, matched by invoice_number.
        """
        if not self.invoice_number:
            return Decimal("0.00")

        Transaction = apps.get_model("money", "Transaction")
        qs = Transaction.objects.filter(invoice_number=self.invoice_number)

        income_total = (
            qs.filter(trans_type=Transaction.INCOME)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        expense_total = (
            qs.filter(trans_type=Transaction.EXPENSE)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        return income_total - expense_total

    # ---------- Income transaction helpers ----------
    def _get_income_subcat_from_items(self):
        """
        Use the sub-category from the first line item on this invoice.
        Assumes all invoice items use the same income subcategory.
        """
        first_item = self.items.select_related("sub_cat", "sub_cat__category").first()
        if not first_item or not first_item.sub_cat:
            raise ValueError(
                "Cannot determine income SubCategory from invoice items. "
                "Add at least one line item with a Sub Category before marking as paid."
            )
        return first_item.sub_cat

    def create_income_transaction(
        self,
        *,
        user,
        amount: Decimal | None = None,
        date=None,
        team=None,
        event=None,
        transport_type=None,
    ):
        """
        Create a single Income Transaction linked to this invoice.

        - Uses the SubCategory from the first invoice item.
        - Derives category from sub_cat.category for tax reporting.
        - Uses this invoice's invoice_number as the bridge.
        - If event is not provided, falls back to invoice.event.
        - If date is not provided, uses paid_date, then invoice date, then today.
        - If amount is not provided, uses the invoice amount.
        """
        from django.utils import timezone

        Transaction = apps.get_model("money", "Transaction")

        if not self.invoice_number:
            raise ValueError("Cannot create income transaction without invoice_number.")

        sub_cat = self._get_income_subcat_from_items()
        category = getattr(sub_cat, "category", None)
        if category is None:
            raise ValueError("Selected sub_cat has no category; cannot create Transaction.")

        tx_date = date or self.paid_date or self.date or timezone.now().date()
        tx_event = event if event is not None else self.event
        tx_amount = amount if amount is not None else self.amount

        description = self.event_name or f"Invoice {self.invoice_number}"

        transaction = Transaction.objects.create(
            user=user,
            trans_type=Transaction.INCOME,
            category=category,
            sub_cat=sub_cat,
            amount=tx_amount,
            transaction=description,
            team=team,
            event=tx_event,
            date=tx_date,
            invoice_number=self.invoice_number,
            transport_type=transport_type,
        )
        return transaction

    def mark_as_paid(
        self,
        *,
        user,
        payment_date=None,
        team=None,
        event=None,
        transport_type=None,
        commit=True,
    ):
        """
        Mark this invoice as fully paid and create a matching Income Transaction.

        - Sets paid_date (to payment_date or today).
        - Sets status to 'Paid'.
        - Creates one Income Transaction for the full invoice amount.
        - Uses the SubCategory from the first invoice item.
        - Returns the created Transaction.
        """
        from django.utils import timezone

        pay_date = payment_date or timezone.now().date()
        self.paid_date = pay_date
        self.status = self.STATUS_PAID

        if commit:
            self.save(update_fields=["paid_date", "status"])

        income_tx = self.create_income_transaction(
            user=user,
            amount=self.amount,
            date=pay_date,
            team=team,
            event=event,
            transport_type=transport_type,
        )
        return income_tx





# -------------------  N E W  M O D E L  ---------------------- #



class InvoiceItemV2(models.Model):
    """
    Line items for InvoiceV2.
    User selects sub_cat, and category is automatically derived
    from sub_cat.category for consistent tax reporting.
    """

    invoice = models.ForeignKey(
        InvoiceV2,
        on_delete=models.CASCADE,
        related_name="items",
    )
    description = models.CharField(max_length=255)
    qty = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Quantity (hours, days, units, etc.).",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Unit price.",
    )

    # User picks just the sub-category
    sub_cat = models.ForeignKey(
        "SubCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_items_v2",
        help_text="Choose the sub-category; category will be set automatically.",
    )

    # Category is derived from sub_cat.category and not edited directly
    category = models.ForeignKey(
        "Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_items_v2",
        editable=False,
        help_text="Set automatically from sub-category.",
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.description} ({self.qty} @ {self.price})"

    @property
    def line_total(self) -> Decimal:
        return (self.qty or Decimal("0")) * (self.price or Decimal("0"))

    def _sync_category_from_subcat(self):
        """
        Ensure category matches the selected sub-category's category.
        """
        if self.sub_cat and hasattr(self.sub_cat, "category"):
            self.category = self.sub_cat.category
        else:
            self.category = None

    def save(self, *args, **kwargs):
        # Always sync category before saving
        self._sync_category_from_subcat()
        super().save(*args, **kwargs)

        # After saving item, refresh invoice total
        if self.invoice_id:
            self.invoice.update_amount(save=True)

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        if invoice:
            self.invoice.update_amount(save=True)

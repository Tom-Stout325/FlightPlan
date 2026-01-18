# money/models.py
from __future__ import annotations

from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import DecimalField, ExpressionWrapper, F, IntegerField, Q, Sum
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.text import slugify

try:
    from django.contrib.postgres.indexes import GinIndex
    from django.contrib.postgres.search import SearchVectorField
except ImportError: 
    GinIndex = None
    SearchVectorField = None

from project.common.models import OwnedModelMixin



# -----------------------------------------------------------------------------
# Helpers / Validators
# -----------------------------------------------------------------------------

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
        raise ValidationError(
            f"Unsupported logo file type '.{ext}'. Allowed: {', '.join(sorted(allowed))}."
        )


def logo_upload_path(instance, filename):
    # e.g., branding/airborne-images/logo.png
    slug = instance.slug or "default"
    return f"branding/{slug}/{filename}"


def _safe_slug(value: str, max_len: int = 100) -> str:
    return slugify(value or "")[:max_len]


def _ownership_error():
    # Keep message generic to avoid leaking existence of other users' objects
    return "Invalid selection."


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _quantize_money(value: Decimal) -> Decimal:
    return (value or Decimal("0.00")).quantize(Decimal("0.01"))



# -----------------------------------------------------------------------------
# Core Taxonomy
# -----------------------------------------------------------------------------

class Category(OwnedModelMixin):
    INCOME = "Income"
    EXPENSE = "Expense"

    CATEGORY_TYPE_CHOICES = [
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
    ]

    category = models.CharField(max_length=500, blank=True, null=True)
    schedule_c_line = models.CharField(max_length=10, blank=True, null=True, help_text="Enter Schedule C line number (e.g., '8', '9', '27a')",)
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPE_CHOICES, default=EXPENSE, help_text="Default accounting nature for this category.",)
    slug = models.SlugField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["category"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"],
                condition=Q(slug__isnull=False),
                name="uniq_money_category_user_slug_not_null",
            )
        ]
        indexes = [
            models.Index(fields=["user", "category_type"]),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["user", "slug"]),
        ]

    def __str__(self):
        return self.category or "Unnamed Category"

    def save(self, *args, **kwargs):
        if _is_blank(self.slug) and self.category:
            self.slug = _safe_slug(self.category, 255) or None
        super().save(*args, **kwargs)




class SubCategory(OwnedModelMixin):
    sub_cat = models.CharField(max_length=500, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name="subcategories",)
    slug = models.SlugField(max_length=100, blank=True, null=True)
    schedule_c_line = models.CharField(max_length=10, blank=True, null=True, help_text="Enter Schedule C line number.",)
    include_in_tax_reports = models.BooleanField(default=True, help_text="If unchecked, this sub-category is excluded from tax-related reports.",)
    include_in_pl_reports = models.BooleanField(default=True, help_text="If unchecked, this sub-category is excluded from Profit & Loss reports.",)

    class Meta:
        verbose_name_plural = "Sub Categories"
        ordering = ["sub_cat"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"],
                condition=Q(slug__isnull=False),
                name="uniq_money_subcategory_user_slug_not_null",
            )
        ]
        indexes = [
            models.Index(fields=["user", "sub_cat"]),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["user", "slug"]),
        ]

    def __str__(self):
        return f"{self.category} - {self.sub_cat or 'Unnamed SubCategory'}"

    @property
    def category_type(self):
        if self.category and hasattr(self.category, "category_type"):
            return self.category.category_type
        return Category.EXPENSE

    def clean(self):
        super().clean()
        self._assert_owned_fk("category", self.category)

    def save(self, *args, **kwargs):
        if _is_blank(self.slug) and self.sub_cat:
            if self.category and self.category.slug:
                base = f"{self.category.slug}-{self.sub_cat}"
            elif self.category_id:
                base = f"{self.category_id}-{self.sub_cat}"
            else:
                base = self.sub_cat
            self.slug = _safe_slug(base, 100) or None

        # Enforce ownership consistency
        self.full_clean()
        super().save(*args, **kwargs)




class Team(OwnedModelMixin):
    name = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uniq_money_team_per_user")
        ]
        indexes = [
            models.Index(fields=["user", "name"]),
        ]

    def __str__(self):
        return self.name or "Unnamed Team"




class Client(OwnedModelMixin):
    business = models.CharField(max_length=500, blank=True, null=True)
    first = models.CharField(max_length=500, blank=True, null=True)
    last = models.CharField(max_length=500, blank=True, null=True)
    street = models.CharField(max_length=500, blank=True, null=True)
    address2 = models.CharField(max_length=500, blank=True, null=True)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ["business", "last", "first"]
        indexes = [
            models.Index(fields=["user", "business"]),
            models.Index(fields=["user", "email"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "email"], name="uniq_money_client_user_email"),
        ]

    def __str__(self):
        if self.business:
            return self.business

        name = f"{self.first or ''} {self.last or ''}".strip()
        if name:
            return name

        return self.email or "Unnamed Client"


    def clean(self):
        super().clean()
        if self.business is not None:
            self.business = self.business.strip() or None
        if self.first is not None:
            self.first = self.first.strip() or None
        if self.last is not None:
            self.last = self.last.strip() or None
        if self.street is not None:
            self.street = self.street.strip() or None
        if self.address2 is not None:
            self.address2 = self.address2.strip() or None
        if self.phone is not None:
            self.phone = self.phone.strip() or None
        if self.email:
            self.email = self.email.strip().lower()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)





class Event(OwnedModelMixin):
    CATEGORY_TYPE_CHOICES = [
        ("race", "Race"),
        ("live_event", "Live Event"),
        ("real_estate", "Real Estate"),
        ("inspection", "Inspection"),
        ("construction", "Construction"),
        ("photography", "Photography"),
        ("mapping", "Mapping"),
        ("marketing", "Marketing"),
        ("commercial", "Commercial"),
        ("training", "Training"),
        ("internal", "Internal"),
        ("other", "Other"),
    ]

    title                      = models.CharField(max_length=200)
    event_type                 = models.CharField(max_length=50, choices=CATEGORY_TYPE_CHOICES, default="race")
    event_year                 = models.PositiveIntegerField(default=timezone.localdate().year, validators=[MinValueValidator(2000), MaxValueValidator(2100)], db_index=True, help_text="Year this event belongs to (used for reporting and invoice grouping).",)
    location_address           = models.CharField(max_length=500, blank=True, null=True)
    location_city              = models.CharField(max_length=200, blank=True, null=True)
    notes                      = models.TextField(blank=True, null=True)
    client                     = models.ForeignKey("money.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs", help_text="Optional. Attach a client to this job for reporting and defaults.",)
    slug                       = models.SlugField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"],
                condition=Q(slug__isnull=False),
                name="uniq_money_event_user_slug_not_null",
            )
        ]
        indexes = [
            models.Index(fields=["user", "title"]),
            models.Index(fields=["user", "event_type"]),
            models.Index(fields=["user", "event_year"]),
            models.Index(fields=["user", "slug"]),
            models.Index(fields=["user", "client"]),
        ]

    def __str__(self):
        return self.title
    
    def clean(self):
        super().clean()
        self._assert_owned_fk("client", self.client)

    def save(self, *args, **kwargs):
        if _is_blank(self.slug):
            self.slug = _safe_slug(self.title, 100) or None
        super().save(*args, **kwargs)


class Service(OwnedModelMixin):
    service = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ["service"]
        constraints = [
            models.UniqueConstraint(fields=["user", "service"], name="uniq_money_service_per_user")
        ]
        indexes = [
            models.Index(fields=["user", "service"]),
        ]

    def __str__(self):
        return self.service or "Unnamed Service"


# -----------------------------------------------------------------------------
# Transactions
# -----------------------------------------------------------------------------

class Transaction(OwnedModelMixin):
    TRANSPORT_CHOICES = [
        ("personal_vehicle", "Personal Vehicle"),
        ("rental_car", "Rental Car"),
    ]

    INCOME = "Income"
    EXPENSE = "Expense"

    TRANS_TYPE_CHOICES = [
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
    ]

    trans_type         = models.CharField(max_length=10, choices=TRANS_TYPE_CHOICES, default=EXPENSE)
    category           = models.ForeignKey("Category", on_delete=models.PROTECT)
    sub_cat            = models.ForeignKey("SubCategory", on_delete=models.PROTECT, null=True, blank=True)
    amount             = models.DecimalField(max_digits=20, decimal_places=2)
    transaction        = models.CharField(max_length=255)
    team               = models.ForeignKey("Team", null=True, blank=True, on_delete=models.PROTECT)
    event              = models.ForeignKey("Event", null=True, blank=True, on_delete=models.PROTECT, related_name="transactions",)
    receipt            = models.FileField(upload_to="receipts/", blank=True, null=True)
    date               = models.DateField()
    invoice_number     = models.CharField(max_length=25, blank=True, null=True, help_text="Optional")
    recurring_template = models.ForeignKey("RecurringTransaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="generated_transactions",)
    transport_type     = models.CharField(max_length=30, choices=TRANSPORT_CHOICES, null=True, blank=True, help_text="Used to identify if actual expenses apply",)
    contractor         = models.ForeignKey("Contractor", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    
    
    class Meta:
        ordering = ["date"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "trans_type", "date"]),
            models.Index(fields=["user", "invoice_number"]),
            models.Index(fields=["user", "event"]),
            models.Index(fields=["user", "category"]),
            models.Index(fields=["user", "sub_cat"]),
        ]

    def __str__(self):
        return f"{self.transaction} - {self.amount}"

    @property
    def deductible_amount(self):
        # NOTE: If you have a dedicated tax flag for meals, swap this check accordingly.
        if self.sub_cat and self.sub_cat.slug == "meals":
            return _quantize_money(self.amount * Decimal("0.5"))
        return _quantize_money(self.amount)

    def clean(self):
        super().clean()


        # If sub_cat exists, force category alignment (single source of truth)
        if self.sub_cat_id:
            self.category = self.sub_cat.category

        # Now ownership checks are safe and consistent
        self._assert_owned_fk("category", self.category)
        self._assert_owned_fk("sub_cat", self.sub_cat)
        self._assert_owned_fk("event", self.event)
        self._assert_owned_fk("team", self.team)
        self._assert_owned_fk("contractor", self.contractor)


    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# Mileage / Vehicles
# -----------------------------------------------------------------------------

class MileageRate(models.Model):
    """
    Mileage rate stored per-year so historical reports remain correct.

    - user = NULL means "global default for that year"
    - user != NULL means per-user override for that year
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="mileage_rates", help_text="Optional: set per-user rates. Leave blank for a global rate.",)
    year = models.PositiveIntegerField(db_index=True)
    rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.7000"), validators=[MinValueValidator(Decimal("0"))], help_text="Dollars per mile for this year (e.g. 0.6700).",)

    class Meta:
        verbose_name = "Mileage Rate"
        verbose_name_plural = "Mileage Rates"
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(fields=["user", "year"], name="uniq_mileage_rate_user_year"),
            models.UniqueConstraint(
                fields=["year"],
                condition=Q(user__isnull=True),
                name="uniq_mileage_rate_global_year",
            ),
        ]

    def __str__(self):
        who = self.user.username if self.user else "Global"
        return f"{who} – {self.year}: ${self.rate}/mi"


class Vehicle(OwnedModelMixin):
    name = models.CharField(max_length=255)
    placed_in_service_date = models.DateField()
    placed_in_service_mileage = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        validators=[MinValueValidator(0)],
    )
    year = models.PositiveIntegerField()
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    plate = models.CharField(max_length=20, blank=True, null=True)
    vin = models.CharField(max_length=17, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_active", "name"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "name"]),
            models.Index(fields=["vin"]),
        ]

    def __str__(self):
        return self.name


class VehicleYear(models.Model):
    """
    Vehicle year records are owned by the vehicle's user.

    Keeping an explicit user FK here is redundant and can drift. We omit it and
    enforce ownership through vehicle.user in views/forms.
    """

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="year_records")
    tax_year = models.PositiveIntegerField()
    begin_mileage = models.DecimalField(max_digits=10, decimal_places=1, validators=[MinValueValidator(0)])
    end_mileage = models.DecimalField(max_digits=10, decimal_places=1, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["-tax_year"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle", "tax_year"], name="uniq_vehicle_year"),
        ]
        indexes = [
            models.Index(fields=["tax_year"]),
            models.Index(fields=["vehicle", "tax_year"]),
        ]

    def __str__(self):
        return f"{self.vehicle} – {self.tax_year}"

    def clean(self):
        super().clean()
        if self.begin_mileage is not None and self.end_mileage is not None:
            if self.end_mileage < self.begin_mileage:
                raise ValidationError({"end_mileage": "End mileage must be >= begin mileage."})


class VehicleExpense(OwnedModelMixin):
    EXPENSE_TYPE_CHOICES = [
        ("Maintenance", "Maintenance"),
        ("Repair", "Repair"),
        ("Tires", "Tires"),
        ("Fuel", "Fuel"),
        ("Insurance", "Insurance"),
        ("Registration", "Registration"),
        ("Citation", "Citation"),
        ("Equipment", "Equipment"),
        ("Other", "Other"),
    ]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="expenses")
    date = models.DateField()
    expense_type = models.CharField(max_length=30, choices=EXPENSE_TYPE_CHOICES, default="Other")
    description = models.CharField(max_length=255)
    vendor = models.CharField(max_length=255, null=True, blank=True)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    odometer = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    notes = models.TextField(null=True, blank=True)
    receipt = models.FileField(upload_to="vehicle/receipts/", null=True, blank=True)
    is_tax_related = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "vehicle", "date"]),
            models.Index(fields=["user", "expense_type"]),
        ]

    def __str__(self):
        return f"{self.vehicle} – {self.expense_type} ({self.date})"

    def clean(self):
        super().clean()
        self._assert_owned_fk("vehicle", self.vehicle)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Miles(OwnedModelMixin):
    MILEAGE_TYPE_CHOICES = [
        ("Business", "Business"),
        ("Commuting", "Commuting"),
        ("Other", "Other"),
        ("Reimbursed", "Reimbursed"),
    ]

    date = models.DateField()
    begin = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    end = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    total = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True, editable=False)
    client = models.ForeignKey("Client", on_delete=models.PROTECT)
    event = models.ForeignKey("Event", on_delete=models.SET_NULL, null=True, blank=True, help_text="Event this mileage was associated with (for event-level cost analysis).",)
    invoice_v2 = models.ForeignKey("InvoiceV2", on_delete=models.SET_NULL, null=True, blank=True, related_name="mileage_entries", help_text="If set, this mileage entry is tied to an Invoice V2.",)
    invoice_number = models.CharField(max_length=255, null=True, blank=True, db_index=True, help_text="Legacy invoice number string. For new entries, usually mirrors InvoiceV2.invoice_number.",)
    vehicle = models.ForeignKey("Vehicle", on_delete=models.PROTECT)
    mileage_type = models.CharField(max_length=20, choices=MILEAGE_TYPE_CHOICES, default="Business")

    class Meta:
        verbose_name_plural = "Miles"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "vehicle"]),
            models.Index(fields=["user", "mileage_type"]),
        ]

    def __str__(self):
        label = self.invoice_number or (self.invoice_v2.invoice_number if self.invoice_v2 else "No invoice")
        return f"{label} – {self.client} ({self.date})"

    def clean(self):
        super().clean()
        self._assert_owned_fk("client", self.client)
        self._assert_owned_fk("event", self.event)
        self._assert_owned_fk("invoice_v2", self.invoice_v2)
        self._assert_owned_fk("vehicle", self.vehicle)

        if self.invoice_v2 and self.invoice_v2.invoice_number and _is_blank(self.invoice_number):
            self.invoice_number = self.invoice_v2.invoice_number

        if self.begin is not None and self.end is not None:
            if self.end < self.begin:
                raise ValidationError({"end": "End mileage must be >= begin mileage."})
            self.total = (self.end - self.begin).quantize(Decimal("0.1"))
        else:
            self.total = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# Recurring Transactions & Receipts
# -----------------------------------------------------------------------------

class RecurringTransaction(OwnedModelMixin):
    INCOME = "Income"
    EXPENSE = "Expense"
    TRANS_TYPE_CHOICES = [(INCOME, "Income"), (EXPENSE, "Expense")]

    trans_type = models.CharField(max_length=10, choices=TRANS_TYPE_CHOICES, default=EXPENSE)
    category = models.ForeignKey(
        "Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Auto-filled from Sub-Category.",
    )
    sub_cat = models.ForeignKey("SubCategory", on_delete=models.PROTECT, null=True, blank=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    transaction = models.CharField(max_length=255)
    day = models.IntegerField(
        help_text="Day of the month to apply",
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    team = models.ForeignKey("Team", null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey("Event", null=True, blank=True, on_delete=models.PROTECT)
    receipt = models.FileField(upload_to="receipts/", blank=True, null=True)
    active = models.BooleanField(default=True)
    last_created = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "day", "active"])]

    def __str__(self):
        return f"{self.transaction} - {self.amount} on day {self.day}"

    def clean(self):
        super().clean()

        self._assert_owned_fk("sub_cat", self.sub_cat)
        self._assert_owned_fk("category", self.category)
        self._assert_owned_fk("event", self.event)
        self._assert_owned_fk("team", self.team)

        # Auto-fill category from sub_cat
        if self.sub_cat:
            self.category = self.sub_cat.category

        if not self.sub_cat and not self.category:
            raise ValidationError("Select either a Sub-Category or a Category.")

        if self.sub_cat and self.category and self.sub_cat.category_id != self.category_id:
            raise ValidationError({"sub_cat": "Sub-Category does not belong to the selected Category."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Receipt(OwnedModelMixin):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="receipts")
    date = models.DateField(blank=True, null=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    event = models.ForeignKey("Event", null=True, blank=True, on_delete=models.SET_NULL)
    invoice_number = models.CharField(max_length=255, blank=True, null=True)
    receipt_file = models.FileField(upload_to="receipts/", blank=True, null=True)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["user", "invoice_number"]),
        ]

    def __str__(self):
        return f"Receipt: {self.transaction.transaction} - {self.amount or 'No Amount'}"

    def clean(self):
        super().clean()
        self._assert_owned_fk("transaction", self.transaction)
        self._assert_owned_fk("event", self.event)

        # Ensure receipt.user matches transaction.user
        if self.transaction and self.user_id and self.transaction.user_id != self.user_id:
            raise ValidationError({"transaction": _ownership_error()})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# Company Profile 
# -----------------------------------------------------------------------------

PDF_HEADER_LAYOUT_CHOICES = [
    ("stacked", "Stacked (logo above address)"),
    ("inline-left", "Inline (logo left, address right)"),
    ("inline-right", "Inline (address left, logo right)"),
]


class CompanyProfile(models.Model):
    """
    Deployment-level profile (not per-user).
    If you ever need per-user profiles, add user FK + constraints similar to above.
    """

    VEHICLE_EXPENSE_METHOD_MILEAGE = "mileage"
    VEHICLE_EXPENSE_METHOD_ACTUAL = "actual"
    VEHICLE_EXPENSE_METHOD_CHOICES = [
        (VEHICLE_EXPENSE_METHOD_MILEAGE, "Standard mileage"),
        (VEHICLE_EXPENSE_METHOD_ACTUAL, "Actual vehicle expenses"),
    ]

    slug                     = models.SlugField(unique=True, help_text="Short identifier (e.g., 'airborne-images', 'skyguy').")
    legal_name               = models.CharField(max_length=255, help_text="Registered legal name used on invoices.")
    display_name             = models.CharField(max_length=255, blank=True, help_text="Trade name; falls back to legal name if blank.",)
    logo                     = models.ImageField(upload_to=logo_upload_path, validators=[validate_image_extension_no_svg], help_text="Primary logo used in invoice header.",)
    logo_light               = models.ImageField(upload_to=logo_upload_path, blank=True, null=True, validators=[validate_image_extension_no_svg], help_text="Optional light-mode logo variation.",)
    logo_dark                = models.ImageField(upload_to=logo_upload_path, blank=True, null=True, validators=[validate_image_extension_no_svg], help_text="Optional dark-mode logo variation.",)
    logo_alt_text            = models.CharField(max_length=255, blank=True)
    brand_color_primary      = models.CharField(max_length=7, blank=True, validators=[HEX_COLOR_VALIDATOR])
    brand_color_secondary    = models.CharField(max_length=7, blank=True, validators=[HEX_COLOR_VALIDATOR])
    website                  = models.URLField(blank=True)

    address_line1            = models.CharField(max_length=255)
    address_line2            = models.CharField(max_length=255, blank=True)
    city                     = models.CharField(max_length=100)
    state_province           = models.CharField(max_length=100)
    postal_code              = models.CharField(max_length=20)
    country                  = models.CharField(max_length=100, default="United States")
    main_phone               = models.CharField(max_length=50, blank=True)
    support_email            = models.EmailField(blank=True)
    invoice_reply_to_email   = models.EmailField(blank=True)

    billing_contact_name     = models.CharField(max_length=255, blank=True)
    billing_contact_email    = models.EmailField(blank=True)

    tax_id_ein               = models.CharField(max_length=64, blank=True, help_text="EIN / Tax ID displayed on invoices.")
    vehicle_expense_method   = models.CharField(max_length=20, choices=VEHICLE_EXPENSE_METHOD_CHOICES, default=VEHICLE_EXPENSE_METHOD_MILEAGE, help_text="Tax reporting method for vehicle costs.",)

    pay_to_name              = models.CharField(max_length=255, blank=True)
    remittance_address       = models.TextField(blank=True)

    default_terms            = models.CharField(max_length=100, blank=True, help_text='e.g., "Net 30".')
    default_net_days         = models.PositiveIntegerField(default=30)
    default_late_fee_policy  = models.CharField(max_length=255, blank=True)
    default_footer_text      = models.TextField(blank=True)

    pdf_header_layout        = models.CharField(max_length=20, choices=PDF_HEADER_LAYOUT_CHOICES, default="inline-left")
    header_logo_max_width_px = models.PositiveIntegerField(default=320)
    default_currency         = models.CharField(max_length=3, default="USD")
    default_locale           = models.CharField(max_length=10, default="en_US")
    timezone                 = models.CharField(max_length=64, default="America/Indiana/Indianapolis")

    is_active                = models.BooleanField(default=False, help_text="Only one active profile allowed per deployment.")
    created_at               = models.DateTimeField(auto_now_add=True)
    updated_at               = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name="unique_active_company_profile",
            ),
        ]

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return f"{self.display_name or self.legal_name} ({self.slug})"

    @property
    def name_for_display(self) -> str:
        """
        Canonical brand display name used across PDFs and UI.

        Priority:
        1) display_name (if non-empty after stripping whitespace)
        2) legal_name (if non-empty after stripping whitespace)
        3) empty string
        """
        display = (self.display_name or "").strip()
        if display:
            return display

        legal = (self.legal_name or "").strip()
        return legal

    @property
    def logo_alt(self) -> str:
        alt = (self.logo_alt_text or "").strip()
        return alt or self.name_for_display or "Brand Logo"

    def full_address_lines(self):
        lines = [self.address_line1]
        if self.address_line2:
            lines.append(self.address_line2)

        city_line = ", ".join(filter(None, [self.city, self.state_province]))
        if self.postal_code:
            city_line = f"{city_line} {self.postal_code}" if city_line else self.postal_code
        if city_line:
            lines.append(city_line)

        if self.country:
            lines.append(self.country)
        return lines

    def clean(self):
        missing = []
        if self.is_active:
            for f in ("legal_name", "address_line1", "city", "state_province", "postal_code", "country"):
                if not getattr(self, f, None):
                    missing.append(f)
            if not self.logo:
                missing.append("logo")

        if missing:
            raise ValidationError({"__all__": f"Active profile requires fields: {', '.join(missing)}"})


# -----------------------------------------------------------------------------
# Invoice V2 (user-scoped)
# -----------------------------------------------------------------------------

class InvoiceV2(OwnedModelMixin):
    invoice_number     = models.CharField(max_length=25, blank=True, null=True, help_text="Human-visible invoice ID (YYNNNN format; auto-generated if blank).",)
    client             = models.ForeignKey("Client", on_delete=models.PROTECT, related_name="invoices_v2")
    event              = models.ForeignKey("Event", on_delete=models.PROTECT, related_name="invoices_v2", null=True, blank=True, help_text="Optional: link this invoice to a specific event/race.",)
    event_name         = models.CharField(max_length=500, blank=True, null=True)
    location           = models.CharField(max_length=500, blank=True, null=True)
    service            = models.ForeignKey("Service", on_delete=models.PROTECT, related_name="invoices_v2")
    amount             = models.DecimalField(default=Decimal("0.00"), max_digits=12, decimal_places=2, editable=False, help_text="Total invoice amount, calculated from line items.",)
    date               = models.DateField(help_text="Invoice date.")
    due                = models.DateField(help_text="Due date.")
    paid_date          = models.DateField(null=True, blank=True, help_text="Date fully paid.")

    STATUS_UNPAID = "Unpaid"
    STATUS_PAID = "Paid"
    STATUS_PARTIAL = "Partial"
    STATUS_CHOICES = [
        (STATUS_UNPAID, "Unpaid"),
        (STATUS_PAID, "Paid"),
        (STATUS_PARTIAL, "Partial"),
    ]
    status             = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNPAID)
    issued_at          = models.DateTimeField(null=True, blank=True)
    version            = models.PositiveIntegerField(default=1)
    pdf_url            = models.URLField(blank=True, max_length=1000)
    pdf_sha256         = models.CharField(max_length=64, blank=True)

    sent_at            = models.DateTimeField(null=True, blank=True)
    sent_to            = models.EmailField(null=True, blank=True)
    sent_by            = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoice_v2_emails_sent",)

    if SearchVectorField is not None:
        search_vector = SearchVectorField(null=True, blank=True)

    # Snapshot fields (“From”)
    from_name          = models.CharField(max_length=255, blank=True)
    from_address       = models.TextField(blank=True)
    from_phone         = models.CharField(max_length=50, blank=True)
    from_email         = models.EmailField(blank=True)
    from_website       = models.URLField(blank=True)
    from_tax_id        = models.CharField(max_length=64, blank=True)

    from_logo_url      = models.URLField(blank=True)
    from_header_logo_max_width_px = models.PositiveIntegerField(default=320)

    from_terms         = models.CharField(max_length=100, blank=True)
    from_net_days      = models.PositiveIntegerField(default=30)
    from_footer_text   = models.TextField(blank=True)

    from_currency      = models.CharField(max_length=3, default="USD")
    from_locale        = models.CharField(max_length=10, default="en_US")
    from_timezone      = models.CharField(max_length=64, default="America/Indiana/Indianapolis")

    pdf_snapshot       = models.FileField(upload_to="invoices_v2/", blank=True, null=True)
    pdf_snapshot_created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["invoice_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "invoice_number"],
                name="uniq_invoicev2_user_number",
                condition=Q(invoice_number__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["user", "invoice_number"]),
            models.Index(fields=["user", "client", "date"]),
            models.Index(fields=["user", "event", "date"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        if self.invoice_number:
            return f"{self.invoice_number} ({self.client})"
        return f"InvoiceV2 #{self.pk} ({self.client})"

    @property
    def year(self) -> int:
        return self.date.year if self.date else timezone.localdate().year

    def clean(self):
        super().clean()
        self._assert_owned_fk("client", self.client)
        self._assert_owned_fk("event", self.event)
        self._assert_owned_fk("service", self.service)

    def _generate_invoice_number(self) -> str:
        """
        Generates invoice numbers like YYNNNN per *user*.
        Sequence starts at 0100 each year.
        """
        if not self.date:
            raise ValueError("Invoice date is required to generate invoice_number.")
        if not self.user_id:
            raise ValueError("Invoice user is required to generate invoice_number.")

        year_short = str(self.date.year)[-2:] 
        prefix = year_short

        qs = (
            InvoiceV2.objects.select_for_update()
            .filter(
                user=self.user,
                invoice_number__startswith=prefix,
                invoice_number__regex=r"^\d+$",
            )
            .annotate(numeric_part=Cast("invoice_number", IntegerField()))
            .order_by("-numeric_part")
        )

        last_invoice = qs.first()
        if not last_invoice or not last_invoice.invoice_number:
            return f"{year_short}0100"

        try:
            last_number = int(last_invoice.invoice_number)
        except (TypeError, ValueError):
            return f"{year_short}0100"

        return str(last_number + 1)

    def save(self, *args, **kwargs):
        self.full_clean()

        if not self.invoice_number and self.date:
            with transaction.atomic():
                self.full_clean()
                self.invoice_number = self._generate_invoice_number()
                super().save(*args, **kwargs)
                return

        super().save(*args, **kwargs)

    # ---------- Totals ----------
    def update_amount(self, save: bool = True):
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
        self.amount = _quantize_money(total)
        if save:
            self.save(update_fields=["amount"])

    @property
    def is_paid(self) -> bool:
        return bool(self.paid_date) or self.status == self.STATUS_PAID

    @property
    def is_locked(self) -> bool:
        return bool(self.issued_at)

    @property
    def days_to_pay(self):
        if self.paid_date and self.date:
            return (self.paid_date - self.date).days
        return None

    @property
    def has_pdf_snapshot(self) -> bool:
        return bool(self.pdf_snapshot)

    def has_from_snapshot(self) -> bool:
        return bool(self.from_name or self.from_logo_url or self.from_address)

    def snapshot_from_profile(self, profile, absolute_logo_url: str | None = None, overwrite: bool = False):
        if not profile:
            return
        if self.has_from_snapshot() and not overwrite:
            return

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

        self.from_terms = getattr(profile, "default_terms", "") or ""
        default_net_days = getattr(profile, "default_net_days", self.from_net_days)
        self.from_net_days = int(default_net_days or 30)
        self.from_footer_text = getattr(profile, "default_footer_text", "") or ""

        self.from_currency = getattr(profile, "default_currency", "") or "USD"
        self.from_locale = getattr(profile, "default_locale", "") or "en_US"
        self.from_timezone = getattr(profile, "timezone", "America/Indiana/Indianapolis")

    @property
    def net_income(self) -> Decimal:
        """
        Scoped to this invoice's user to prevent cross-user leakage.
        """
        if not self.invoice_number:
            return Decimal("0.00")

        TransactionModel = apps.get_model("money", "Transaction")
        qs = TransactionModel.objects.filter(user=self.user, invoice_number=self.invoice_number)

        income_total = (
            qs.filter(trans_type=TransactionModel.INCOME)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        expense_total = (
            qs.filter(trans_type=TransactionModel.EXPENSE)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0.00")
        )
        return _quantize_money(income_total - expense_total)

    def _get_income_subcat_from_items(self):
        items = self.items.select_related("sub_cat__category")
        for item in items:
            sub_cat = getattr(item, "sub_cat", None)
            if not sub_cat:
                continue
            if sub_cat.category_type == Category.INCOME:
                return sub_cat
        raise ValueError(
            "Cannot determine income SubCategory from invoice items. "
            "Add at least one line item with an Income category before marking this invoice as paid."
        )

    def create_income_transaction(
        self,
        *,
        user,
        amount: Decimal | None = None,
        date=None,
        team=None,
        event=None,
        transport_type=None,
        overwrite_existing: bool = False,
    ):
        TransactionModel = apps.get_model("money", "Transaction")

        if not self.invoice_number:
            raise ValueError("Cannot create income transaction without invoice_number.")

        sub_cat = self._get_income_subcat_from_items()
        category = getattr(sub_cat, "category", None)
        if category is None:
            raise ValueError("Selected income SubCategory has no Category; cannot create Transaction.")

        tx_date = date or self.paid_date or self.date or timezone.localdate()
        tx_event = event if event is not None else self.event
        tx_amount = amount if amount is not None else self.amount
        description = self.event_name or f"Invoice {self.invoice_number}"

        existing_qs = TransactionModel.objects.filter(
            user=user,
            invoice_number=self.invoice_number,
            trans_type=TransactionModel.INCOME,
        ).order_by("pk")

        if overwrite_existing and existing_qs.exists():
            tx = existing_qs.first()
            tx.category = category
            tx.sub_cat = sub_cat
            tx.amount = tx_amount
            tx.transaction = description
            tx.team = team or tx.team
            tx.event = tx_event
            tx.date = tx_date
            tx.transport_type = transport_type or tx.transport_type
            tx.save()
            return tx

        return TransactionModel.objects.create(
            user=user,
            trans_type=TransactionModel.INCOME,
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
        pay_date = payment_date or timezone.localdate()
        self.paid_date = pay_date
        self.status = self.STATUS_PAID

        if commit:
            self.update_amount(save=False)
            self.save(update_fields=["amount", "paid_date", "status"])

        return self.create_income_transaction(
            user=user,
            amount=self.amount,
            date=pay_date,
            team=team,
            event=event,
            transport_type=transport_type,
            overwrite_existing=True,
        )


class InvoiceItemV2(OwnedModelMixin):
    invoice     = models.ForeignKey(InvoiceV2, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    qty         = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"), help_text="Quantity (hours, days, units, etc.).",)
    price       = models.DecimalField(max_digits=10, decimal_places=2, help_text="Unit price.")
    sub_cat     = models.ForeignKey("SubCategory", on_delete=models.PROTECT, null=True, blank=True, related_name="invoice_items_v2", help_text="Choose the sub-category; category will be set automatically.",)
    category    = models.ForeignKey("Category", on_delete=models.PROTECT, null=True, blank=True, related_name="invoice_items_v2", editable=False, help_text="Set automatically from sub-category.",)

    class Meta:
        ordering = ["pk"]
        indexes = [
            models.Index(fields=["user", "invoice"]),
            models.Index(fields=["user", "sub_cat"]),
        ]

    def __str__(self):
        return f"{self.description} ({self.qty} @ {self.price})"

    @property
    def line_total(self) -> Decimal:
        return (self.qty or Decimal("0")) * (self.price or Decimal("0"))

    def _sync_category_from_subcat(self):
        if self.sub_cat and hasattr(self.sub_cat, "category"):
            self.category = self.sub_cat.category
        else:
            self.category = None

    
    def clean(self):
        super().clean()

        if self.invoice is None:
            raise ValidationError({"invoice": "Invoice is required."})

        self._assert_owned_fk("invoice", self.invoice)
        self._assert_owned_fk("sub_cat", self.sub_cat)
        self._assert_owned_fk("category", self.category)

        if self.user_id and self.invoice.user_id != self.user_id:
            raise ValidationError({"invoice": _ownership_error()})

        if self.sub_cat:
            self._sync_category_from_subcat()

        if self.sub_cat and self.category and self.sub_cat.category_id != self.category_id:
            raise ValidationError({"sub_cat": "Sub-Category does not belong to the selected Category."})


    def save(self, *args, **kwargs):
        self._sync_category_from_subcat()
        self.full_clean()
        super().save(*args, **kwargs)

        if self.invoice_id:
            self.invoice.update_amount(save=True)

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        if invoice:
            invoice.update_amount(save=True)






# ------------------------------------------------------------------
# CONTRACTORS
# ------------------------------------------------------------------


class Contractor(OwnedModelMixin):
    """
    Contractor / Subcontractor for W-9 tracking and 1099 preparation.

    Security posture:
    - Store only TIN last-4 (optional) + TIN type (SSN/EIN).
    - Store the W-9 PDF as a document (S3), do NOT store full TIN in DB.
    """

    # ------------------------------------------------------------------
    # Human-friendly ID (optional)
    # ------------------------------------------------------------------
    contractor_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional human-friendly ID, e.g. C-00023",
    )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    business_name = models.CharField(max_length=200, blank=True)

    # ------------------------------------------------------------------
    # Contact
    # ------------------------------------------------------------------
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # ------------------------------------------------------------------
    # Mailing address (for 1099 delivery fallback)
    # ------------------------------------------------------------------
    address1 = models.CharField(max_length=200, blank=True)
    address2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(
        max_length=2,
        blank=True,
        validators=[RegexValidator(r"^[A-Z]{2}$", "Use 2-letter state code (e.g., IN).")],
        help_text="2-letter state code",
    )
    zip_code = models.CharField(
        max_length=10,
        blank=True,
        validators=[RegexValidator(r"^\d{5}(-\d{4})?$", "Use ZIP format 12345 or 12345-6789.")],
    )

    # ------------------------------------------------------------------
    # Tax classification
    # ------------------------------------------------------------------
    INDIVIDUAL_SOLEPROP = "individual_soleprop"
    SINGLE_MEMBER_LLC = "single_member_llc"
    PARTNERSHIP_LLC = "partnership_llc"
    C_CORP = "c_corp"
    S_CORP = "s_corp"
    TRUST_ESTATE = "trust_estate"
    OTHER = "other"

    ENTITY_TYPE_CHOICES = [
        (INDIVIDUAL_SOLEPROP, "Individual / Sole proprietor"),
        (SINGLE_MEMBER_LLC, "Single-member LLC"),
        (PARTNERSHIP_LLC, "Partnership / Multi-member LLC"),
        (C_CORP, "C Corporation"),
        (S_CORP, "S Corporation"),
        (TRUST_ESTATE, "Trust / Estate"),
        (OTHER, "Other"),
    ]

    entity_type = models.CharField(max_length=30, choices=ENTITY_TYPE_CHOICES)

    SSN = "ssn"
    EIN = "ein"
    TIN_TYPE_CHOICES = [
        (SSN, "SSN"),
        (EIN, "EIN"),
    ]

    tin_type = models.CharField(max_length=3, choices=TIN_TYPE_CHOICES, blank=True)
    tin_last4 = models.CharField(
        max_length=4,
        blank=True,
        validators=[RegexValidator(r"^\d{4}$", "Enter last 4 digits.")],
        help_text="Last 4 digits only. Do not store full TIN.",
    )

    is_1099_eligible = models.BooleanField(
        default=True,
        help_text="Whether this contractor should receive a 1099 (default True; you can override).",
    )

    # ------------------------------------------------------------------
    # W-9 tracking (metadata + document)
    # ------------------------------------------------------------------
    W9_NOT_REQUESTED = "not_requested"
    W9_REQUESTED = "requested"
    W9_RECEIVED = "received"
    W9_VERIFIED = "verified"

    W9_STATUS_CHOICES = [
        (W9_NOT_REQUESTED, "Not requested"),
        (W9_REQUESTED, "Requested"),
        (W9_RECEIVED, "Received"),
        (W9_VERIFIED, "Verified"),
    ]

    w9_status = models.CharField(
        max_length=20,
        choices=W9_STATUS_CHOICES,
        default=W9_NOT_REQUESTED,
    )
    w9_sent_date = models.DateField(null=True, blank=True)
    w9_received_date = models.DateField(null=True, blank=True)
    w9_document = models.FileField(
        upload_to="money/tax-documents/w9/%Y/",
        blank=True,
        help_text="Store W-9 PDF (S3). Do not store full TIN in DB.",
    )

    notes = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # 1099 e-delivery consent
    # ------------------------------------------------------------------
    edelivery_consent = models.BooleanField(default=False)
    edelivery_consent_date = models.DateTimeField(null=True, blank=True)

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name", "id"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "last_name", "first_name"]),
        ]
        constraints = [
            # contractor_number is optional, but if present it should be unique per user.
            models.UniqueConstraint(
                fields=["user", "contractor_number"],
                name="uniq_contractor_number_per_user",
                condition=~models.Q(contractor_number=""),
            )
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        
        if self.business_name:
            return self.business_name
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        super().clean() 
        
        if self.edelivery_consent and not self.edelivery_consent_date:
            self.edelivery_consent_date = timezone.now()

        if self.tin_last4 and not self.tin_type:
            from django.core.exceptions import ValidationError
            raise ValidationError({"tin_type": "Select SSN or EIN when entering last-4 digits."})
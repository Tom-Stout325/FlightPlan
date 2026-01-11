import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models


def receipt_upload_path(instance: "Equipment", filename: str) -> str:
    return f"equipment/{instance.user_id}/receipts/{filename}"


def registration_upload_path(instance: "Equipment", filename: str) -> str:
    return f"equipment/{instance.user_id}/registrations/{filename}"


class Equipment(models.Model):
    """
    User-facing "Equipment" (drones/cameras/etc), but tax-aware for depreciation + Form 4797.
    """

    ALLOWED_FILE_EXTENSIONS = ["jpg", "jpeg", "png", "pdf"]

    PROPERTY_1245 = "1245"
    PROPERTY_1250 = "1250"
    PROPERTY_TYPE_CHOICES = [
        (PROPERTY_1245, "Section 1245 (Depreciable personal property)"),
        (PROPERTY_1250, "Section 1250 (Depreciable real property)"),
    ]

    DEPR_METHOD_MACRS = "MACRS"
    DEPR_METHOD_STRAIGHT = "SL"
    DEPR_METHOD_CHOICES = [
        (DEPR_METHOD_MACRS, "MACRS"),
        (DEPR_METHOD_STRAIGHT, "Straight-line"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ✅ User scoping
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="equipment_items",
        null=True,
        blank=True,
    )

    # --- Core identity ---
    name = models.CharField(max_length=200)
    equipment_type = models.CharField(
        max_length=50,
        choices=(
            ("Drone", "Drone"),
            ("Battery", "Battery"),
            ("Controller", "Controller"),
            ("Camera", "Camera"),
            ("Lens", "Lens"),
            ("Vehicle", "Vehicle"),
            ("Trailer", "Trailer"),
            ("Other", "Other"),
        ),
        default="Drone",
    )
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=200, blank=True)

    # --- FAA / drone-only fields ---
    faa_number = models.CharField(max_length=100, blank=True)
    faa_certificate = models.FileField(
        upload_to=registration_upload_path,  # ✅ user-scoped upload path
        validators=[FileExtensionValidator(ALLOWED_FILE_EXTENSIONS)],
        blank=True,
        null=True,
    )

    # --- Purchase / disposition ---
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Original purchase cost (basis) of this item.",
    )
    receipt = models.FileField(
        upload_to=receipt_upload_path,  # ✅ user-scoped upload path
        validators=[FileExtensionValidator(ALLOWED_FILE_EXTENSIONS)],
        blank=True,
        null=True,
    )

    date_sold = models.DateField(null=True, blank=True)
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Gross sale proceeds received for this item.",
    )

    # --- Tax / depreciation metadata ---
    property_type = models.CharField(
        max_length=10,
        choices=PROPERTY_TYPE_CHOICES,
        default=PROPERTY_1245,
        help_text="Tax classification for gain/loss reporting (e.g., Form 4797).",
    )
    placed_in_service_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the asset was first placed in service for business use (may differ from purchase date).",
    )
    useful_life_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Optional: useful life in years (for planning/straight-line cases).",
    )
    depreciation_method = models.CharField(
        max_length=10,
        choices=DEPR_METHOD_CHOICES,
        default=DEPR_METHOD_MACRS,
        help_text="Optional: depreciation approach used for planning/reporting.",
    )

    deducted_full_cost = models.BooleanField(
        default=True,
        help_text="If True, indicates the cost was fully expensed (e.g., Section 179/bonus) rather than depreciated over time.",
    )

    business_use_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Optional: business-use percentage (0-100). Useful for mixed-use assets like a travel trailer.",
    )

    # --- Operational flags ---
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    drone_safety_profile = models.ForeignKey(
        "equipment.DroneSafetyProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment_items",
        help_text="If set, links this equipment item to a known safety profile (drones only).",
    )

    def is_drone(self) -> bool:
        return self.equipment_type == "Drone"

    def clean(self):
        super().clean()

        if self.date_sold and self.sale_price is None:
            raise ValidationError({"sale_price": "Sale price is required when a sold date is provided."})
        if self.sale_price is not None and not self.date_sold:
            raise ValidationError({"date_sold": "Sold date is required when a sale price is provided."})

        if self.business_use_percent is not None:
            if self.business_use_percent < Decimal("0.00") or self.business_use_percent > Decimal("100.00"):
                raise ValidationError({"business_use_percent": "Business use percent must be between 0 and 100."})

        if not self.is_drone():
            if self.faa_number:
                raise ValidationError({"faa_number": "FAA number is only applicable to drones."})
            if self.faa_certificate:
                raise ValidationError({"faa_certificate": "FAA certificate is only applicable to drones."})
            if self.drone_safety_profile:
                raise ValidationError({"drone_safety_profile": "Safety profiles are only applicable to drones."})

    def __str__(self):
        return f"{self.name} ({self.equipment_type})"

    class Meta:
        ordering = ["equipment_type", "name"]
        verbose_name_plural = "Equipment"
        db_table = "flightplan_equipment"


class DroneSafetyProfile(models.Model):
    BRAND_CHOICES = [
        ("DJI", "DJI"),
        ("DJI Enterprise", "DJI Enterprise"),
        ("Autel", "Autel"),
        ("Skydio", "Skydio"),
        ("Other", "Other"),
    ]

    brand = models.CharField(max_length=50, choices=BRAND_CHOICES, default="DJI")
    model_name = models.CharField(max_length=100)
    full_display_name = models.CharField(max_length=150, unique=True)
    year_released = models.PositiveSmallIntegerField(null=True, blank=True)
    is_enterprise = models.BooleanField(default=False)
    safety_features = models.TextField()
    aka_names = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["brand", "model_name"]
        constraints = [
            models.UniqueConstraint(fields=["brand", "model_name"], name="uniq_dronesafetyprofile_brand_model"),
        ]
        verbose_name = "Drone Safety Profile"
        verbose_name_plural = "Drone Safety Profiles"

    def __str__(self) -> str:
        return self.full_display_name or f"{self.brand} {self.model_name}"

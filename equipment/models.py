from django.db import models
from django.core.validators import FileExtensionValidator
import uuid
from django.core.exceptions import ValidationError




class Equipment(models.Model):
    ALLOWED_FILE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'pdf']

    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name                   = models.CharField(max_length=200)
    equipment_type         = models.CharField(max_length=50, choices=(("Drone", "Drone"),("Battery", "Battery"),("Controller", "Controller"),("Other", "Other"),),default="Drone",)
    brand                  = models.CharField(max_length=100, blank=True)
    model                  = models.CharField(max_length=200, blank=True)
    serial_number          = models.CharField(max_length=200, blank=True)
    faa_number             = models.CharField(max_length=100, blank=True)
    faa_certificate        = models.FileField(upload_to='registrations/', validators=[FileExtensionValidator(ALLOWED_FILE_EXTENSIONS)], blank=True, null=True)
    purchase_date          = models.DateField(null=True, blank=True)
    purchase_cost          = models.DecimalField( max_digits=10, decimal_places=2, null=True, blank=True, help_text="Enter the original purchase cost of the equipment.")
    receipt                = models.FileField(upload_to='receipts/', validators=[FileExtensionValidator(ALLOWED_FILE_EXTENSIONS)], blank=True, null=True)
    date_sold              = models.DateField(null=True, blank=True)
    sale_price             = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deducted_full_cost     = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    notes                  = models.TextField(blank=True)
    drone_safety_profile = models.ForeignKey(
        "equipment.DroneSafetyProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipment_items",
        help_text="If set, this links this piece of equipment to a known safety profile.",
    )


    def is_drone(self):
        return self.equipment_type == 'Drone'

    def clean(self):
        super().clean()

        # Non-drones cannot have FAA data
        if not self.is_drone():
            if self.faa_number:
                raise ValidationError({'faa_number': 'FAA number is only applicable to drones.'})
            if self.faa_certificate:
                raise ValidationError({'faa_certificate': 'FAA certificate is only applicable to drones.'})
            if self.drone_safety_profile:
                raise ValidationError({'drone_safety_profile': 'Safety profiles are only applicable to drones.'})


    def __str__(self):
        return f"{self.name} ({self.equipment_type})"

    class Meta:
        ordering = ['equipment_type', 'name']
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

    brand = models.CharField(
        max_length=50,
        choices=BRAND_CHOICES,
        default="DJI",
        help_text="Manufacturer / brand of the aircraft.",
    )

    model_name = models.CharField(
        max_length=100,
        help_text="Short model name, e.g. 'Mavic Air 2', 'Evo II Pro'.",
    )

    full_display_name = models.CharField(
        max_length=150,
        unique=True,
        help_text="Canonical display name, e.g. 'DJI Mavic Air 2'.",
    )

    year_released = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Approximate release year (optional).",
    )


    is_enterprise = models.BooleanField(
        default=False,
        help_text="True if this is an enterprise / commercial platform.",
    )

    safety_features = models.TextField(
        help_text=(
            "Bulleted or paragraph list of key safety features. "
            "Example: return-to-home, obstacle avoidance, ADS-B In, "
            "geo-fencing, parachute system, etc."
        ),
    )

    aka_names = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional alternate names, one line of text.",
    )

    active = models.BooleanField(
        default=True,
        help_text="Uncheck if this profile should no longer be suggested.",
    )

    class Meta:
        ordering = ["brand", "model_name"]
        unique_together = [
            ("brand", "model_name"),
        ]
        verbose_name = "Drone Safety Profile"
        verbose_name_plural = "Drone Safety Profiles"

    def __str__(self) -> str:
        return self.full_display_name or f"{self.brand} {self.model_name}"

from django.db import models
from django.utils.text import slugify
from django.core.validators import FileExtensionValidator
import uuid
from django.core.exceptions import ValidationError




class Equipment(models.Model):
    EQUIPMENT_TYPE_CHOICES = [
        ('Drone', 'Drone'),
        ('Controller', 'Controller'),
        ('Battery', 'Battery'),
        ('Charger', 'Charger'),
        ('Accessory', 'Accessory'),
        ('Other', 'Other'),
    ]

    ALLOWED_FILE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'pdf']

    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name                   = models.CharField(max_length=200)
    equipment_type         = models.CharField(max_length=50, choices=EQUIPMENT_TYPE_CHOICES)
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
    active                 = models.BooleanField(default="True")
    notes                  = models.TextField(blank=True)


    def is_drone(self):
        return self.equipment_type == 'Drone'

    def clean(self):
        super().clean()
        if not self.is_drone():
            if self.faa_number:
                raise ValidationError({'faa_number': 'FAA number is only applicable to drones.'})
            if self.faa_certificate:
                raise ValidationError({'faa_certificate': 'FAA certificate is only applicable to drones.'})

    def __str__(self):
        return f"{self.name} ({self.equipment_type})"

    class Meta:
        ordering = ['equipment_type', 'name']
        verbose_name_plural = "Equipment"
        db_table = "flightplan_equipment"




class DroneSafetyProfile(models.Model):
    BRAND_CHOICES = [
        ("DJI", "DJI"),
        ("Autel", "Autel"),
        ("Skydio", "Skydio"),
        ("Other", "Other"),
    ]

    brand = models.CharField(
        max_length=50,
        choices=BRAND_CHOICES,
        help_text="Manufacturer name, e.g. DJI, Autel.",
    )

    model_name = models.CharField(
        max_length=100,
        help_text="Short model name, e.g. 'Mavic 4 Pro', 'EVO II Pro'.",
    )

    full_display_name = models.CharField(
        max_length=150,
        unique=True,
        help_text="Friendly full name, e.g. 'DJI Mavic 4 Pro'.",
    )

    year_released = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Approximate year the drone was released (optional).",
    )

    is_enterprise = models.BooleanField(
        default=False,
        help_text="Check if this is an Enterprise / commercial series aircraft.",
    )

    safety_features = models.TextField(
        help_text=(
            "Plain text or bullet list of safety features. "
            "This will be used to pre-fill waiver safety sections."
        ),
    )

    aka_names = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Optional comma-separated alternate names, e.g. "
            "'M4P, Mavic 4 Pro, Mavic 4'. Used when matching user input."
        ),
    )

    active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide this profile from suggestions without deleting it.",
    )

    class Meta:
        ordering = ["brand", "model_name"]
        unique_together = ("brand", "model_name")
        verbose_name = "Drone safety profile"
        verbose_name_plural = "Drone safety profiles"

    def __str__(self) -> str:
        return self.full_display_name or f"{self.brand} {self.model_name}"

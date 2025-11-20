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

from django.db import models
from django.utils.text import slugify
from django.core.validators import FileExtensionValidator
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
import hashlib
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse
from django.utils import timezone




User = settings.AUTH_USER_MODEL

class OpsPlan(models.Model):
    # Status workflow
    DRAFT = "Draft"
    IN_REVIEW = "In Review"
    APPROVED = "Approved"
    ARCHIVED = "Archived"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (IN_REVIEW, "In Review"),
        (APPROVED, "Approved"),
        (ARCHIVED, "Archived"),
    ]

    event                    = models.ForeignKey("money.Event", on_delete=models.CASCADE, related_name="ops_plans")
    event_name               = models.CharField(max_length=200, blank=True)
    plan_year                = models.PositiveIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    status                   = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    start_date               = models.DateField(null=True, blank=True)
    end_date                 = models.DateField(null=True, blank=True)
    client                   = models.ForeignKey("money.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="ops_plans")
    address                  = models.CharField(max_length=255, blank=True)
    pilot_in_command         = models.CharField(max_length=150, blank=True)
    visual_observers         = models.CharField(max_length=255, blank=True, help_text="Comma-separated names")
    airspace_class           = models.CharField(max_length=50, blank=True)
    waivers_required         = models.BooleanField(default=False)
    airport                  = models.CharField(max_length=50, blank=True)
    airport_phone            = models.CharField(max_length=50, blank=True)
    contact                  = models.CharField(max_length=50, blank=True)
    emergency_procedures     = models.TextField(blank=True)
    notes                    = models.TextField(blank=True)
    waiver                   = models.FileField(upload_to="ops_plans/", null=True, blank=True)
    location_map             = models.FileField(upload_to="ops_plans/", null=True, blank=True)
    client_approval          = models.FileField(upload_to="ops_plans/", null=True, blank=True)
    client_approval_notes  = models.TextField(blank=True)

    # === Digital approval (single approver, checkbox + typed name) ===
    approval_requested_at    = models.DateTimeField(null=True, blank=True, help_text="When the approval link was generated/sent.")
    approval_token           = models.CharField(max_length=64, null=True, blank=True, db_index=True, help_text="One-time token embedded in approval URL.")
    approval_token_expires_at= models.DateTimeField(null=True, blank=True)

    approved_name            = models.CharField(max_length=200, blank=True, help_text="Typed full name used to approve.")
    approved_email           = models.EmailField(blank=True, help_text="Expected recipient email (optional but recommended).")
    approved_at              = models.DateTimeField(null=True, blank=True)
    approved_ip              = models.GenericIPAddressField(null=True, blank=True)
    approved_user_agent      = models.TextField(blank=True)

    # Snapshot of the Notes at approval time for auditability
    approved_notes_snapshot  = models.TextField(blank=True, help_text="Immutable copy of Notes as seen by the approver.")
    # Tamper-evident checksum of key approval data (hex SHA-256)
    attestation_hash         = models.CharField(max_length=64, blank=True)

    created_by               = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="opsplans_created")
    updated_by               = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="opsplans_updated")
    created_at               = models.DateTimeField(auto_now_add=True)
    updated_at               = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "plan_year"], name="uniq_opsplan_event_year")
        ]
        indexes = [
            models.Index(fields=["event", "plan_year"]),
            models.Index(fields=["event", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["approved_at"]),
        ]
        db_table = "flightplan_opsplan"
        ordering = ["-plan_year", "-updated_at"]

    def __str__(self):
        return f"Ops Plan: {self.event} ({self.plan_year}) [{self.status}]"

    def get_absolute_url(self):
        return reverse("ops_plan_detail", args=[self.pk])

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise models.ValidationError("End date must be after start date.")

    def save(self, *args, **kwargs):
        # Backfill event_name from related Event if empty
        if self.event and not self.event_name:
            event_title = getattr(self.event, "title", None) or getattr(self.event, "name", None)
            self.event_name = event_title or str(self.event)

        # Default client from event if available
        if not self.client and hasattr(self.event, "client_id"):
            self.client = getattr(self.event, "client", None)

        super().save(*args, **kwargs)

    # ===== Convenience helpers (optional to use later) =====
    def generate_approval_token(self) -> str:
        """Create a cryptographically-strong token for the approval URL."""
        token = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
        self.approval_token = token
        return token

    def compute_attestation_hash(self) -> str:
        """
        Build a tamper-evident hash from approval attributes.
        Combine name + snapshot + ISO timestamp + plan id.
        """
        parts = [
            (self.approved_name or "").strip(),
            (self.approved_notes_snapshot or ""),
            (self.approved_at.isoformat() if self.approved_at else ""),
            str(self.pk or ""),
        ]
        digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
        self.attestation_hash = digest
        return digest

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date must be after start date.")
        
    @property
    def is_approved(self) -> bool:
        return bool(self.approved_at and (self.status == self.APPROVED))


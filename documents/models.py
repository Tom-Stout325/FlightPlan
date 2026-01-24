from __future__ import annotations

from django.conf import settings
from django.db import models


class DroneIncidentReport(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="drone_incident_reports",
        null=True,   # temporary for migration/backfill; we will make NOT NULL after backfill
        blank=True,
    )

    report_date = models.DateField()
    reported_by = models.CharField(max_length=100)
    contact = models.CharField(max_length=100)
    role = models.CharField(max_length=100)

    event_date = models.DateField()
    event_time = models.TimeField()
    location = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20)
    description = models.TextField()
    injuries = models.BooleanField(default=False)
    injury_details = models.TextField(blank=True)
    damage = models.BooleanField(default=False)
    damage_cost = models.CharField(max_length=100, blank=True)
    damage_desc = models.TextField(blank=True)

    drone_model = models.CharField(max_length=100)
    registration = models.CharField(max_length=100)
    controller = models.CharField(max_length=100)
    payload = models.CharField(max_length=100)
    battery = models.CharField(max_length=50)

    weather = models.CharField(max_length=100)
    wind = models.CharField(max_length=50)
    temperature = models.CharField(max_length=50)
    lighting = models.CharField(max_length=100)

    witnesses = models.BooleanField(default=False)
    witness_details = models.TextField(blank=True)

    emergency = models.BooleanField(default=False)
    agency_response = models.TextField(blank=True)
    scene_action = models.TextField(blank=True)
    faa_report = models.BooleanField(default=False)
    faa_ref = models.CharField(max_length=100, blank=True)

    cause = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    signature = models.CharField(max_length=100)
    sign_date = models.DateField()

    def __str__(self):
        return f"{self.report_date} - {self.reported_by}"

    class Meta:
        db_table = "flightplan_droneincidentreport"
        ordering = ["-report_date"]


class SOPDocument(models.Model):
    # ✅ NEW: ownership
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sop_documents",
        null=True,   # temporary for migration/backfill; we will make NOT NULL after backfill
        blank=True,
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="sop_docs/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "flightplan_sopdocument"
        ordering = ["-title"]


class GeneralDocument(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="general_documents", null=True,  blank=True,)

    CATEGORY_CHOICES = [
        ("Insurance", "Insurance"),
        ("FAA Airspace Waivers", "FAA Airspace Waivers"),
        ("FAA Operational Waivers", "FAA Operational Waivers"),
        ("Registrations", "Drone Registrations"),
        ("event", "Event Instructions"),
        ("Policies", "Policies"),
        ("Compliance", "Compliance"),
        ("Legal", "Legal"),
        ("Other", "Other"),
    ]

    title = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="general_documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.category})"

    class Meta:
        db_table = "flightplan_generaldocument"
        ordering = ["-title"]

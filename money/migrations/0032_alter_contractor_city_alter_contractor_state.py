from __future__ import annotations

from django.db import migrations, models


STATE_NAME_TO_ABBR = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

VALID_ABBRS = set(STATE_NAME_TO_ABBR.values())


def normalize_contractor_state(apps, schema_editor):
    Contractor = apps.get_model("money", "Contractor")

    for c in Contractor.objects.all().only("id", "state"):
        raw = (c.state or "").strip()
        if not raw:
            continue

        upper = raw.upper()

        if len(upper) == 2 and upper in VALID_ABBRS:
            if c.state != upper:
                c.state = upper
                c.save(update_fields=["state"])
            continue

        abbr = STATE_NAME_TO_ABBR.get(raw.lower())
        if abbr:
            c.state = abbr
            c.save(update_fields=["state"])
        else:
            c.state = ""
            c.save(update_fields=["state"])


class Migration(migrations.Migration):

    dependencies = [
        ("money", "0031_companyprofile_state_1099_reporting_enabled_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_contractor_state, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="contractor",
            name="state",
            field=models.CharField(max_length=2, blank=True),
        ),
    ]

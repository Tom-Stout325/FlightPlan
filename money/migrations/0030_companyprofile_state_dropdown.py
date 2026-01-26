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


def normalize_companyprofile_state(apps, schema_editor):
    CompanyProfile = apps.get_model("money", "CompanyProfile")

    for cp in CompanyProfile.objects.all().only("id", "state"):
        raw = (cp.state or "").strip()
        if not raw:
            continue

        upper = raw.upper()

        if len(upper) == 2 and upper.isalpha() and upper in VALID_ABBRS:
            if cp.state != upper:
                cp.state = upper
                cp.save(update_fields=["state"])
            continue

        abbr = STATE_NAME_TO_ABBR.get(raw.lower())
        if abbr:
            cp.state = abbr
            cp.save(update_fields=["state"])
        else:
            cp.state = ""
            cp.save(update_fields=["state"])


class Migration(migrations.Migration):

    dependencies = [
        ("money", "0029_alter_contractorw9submission_business_name_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="companyprofile",
            old_name="state_province",
            new_name="state",
        ),
        migrations.RunPython(normalize_companyprofile_state, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="companyprofile",
            name="state",
            field=models.CharField(max_length=2, blank=True),
        ),
    ]

# money/migrations/0036_drop_event_waiver_approved.py
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("money", "0035_contractor1099_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE money_event DROP COLUMN IF EXISTS waiver_approved;",
            reverse_sql="ALTER TABLE money_event ADD COLUMN waiver_approved boolean;",
        ),
    ]

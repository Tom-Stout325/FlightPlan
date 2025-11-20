from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector
from django.db.models import Value
from .models import Invoice

@receiver(post_save, sender=Invoice)
def update_search_vector(sender, instance, **kwargs):
    from django.db.models.signals import post_save

    post_save.disconnect(update_search_vector, sender=Invoice)

    try:
        client_business = instance.client.business if instance.client else ""
        service_name = instance.service.service if instance.service else ""

        instance.search_vector = (
            SearchVector(Value(instance.invoice_numb), weight='A') +
            SearchVector(Value(client_business), weight='B') +
            SearchVector(Value(service_name), weight='B')
        )
        instance.save(update_fields=['search_vector'])

    finally:
        # Reconnect after save
        post_save.connect(update_search_vector, sender=Invoice)

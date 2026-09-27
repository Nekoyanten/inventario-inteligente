from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Negocio


@receiver(post_save, sender=Negocio)
def configurar_negocio_nuevo(sender, instance, created, **kwargs):
    """Al crear un negocio se aplica automáticamente la plantilla de su giro."""
    if created:
        from datetime import timedelta

        from django.conf import settings
        from django.utils import timezone

        from .models import Suscripcion
        from .plantillas import aplicar_plantilla

        aplicar_plantilla(instance)
        Suscripcion.objects.get_or_create(
            negocio=instance, defaults={"prueba_hasta": timezone.localdate() + timedelta(days=settings.DIAS_PRUEBA)}
        )

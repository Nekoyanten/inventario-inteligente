from datetime import date, timedelta

from django.db import migrations


def crear(apps, schema_editor):
    Negocio = apps.get_model("core", "Negocio")
    Suscripcion = apps.get_model("core", "Suscripcion")
    for n in Negocio.objects.all():
        Suscripcion.objects.get_or_create(negocio=n, defaults={"prueba_hasta": date.today() + timedelta(days=14)})


class Migration(migrations.Migration):
    dependencies = [("core", "0005_suscripcion")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]

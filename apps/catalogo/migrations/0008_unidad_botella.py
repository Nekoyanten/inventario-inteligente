from django.db import migrations


def crear(apps, schema_editor):
    UnidadMedida = apps.get_model("catalogo", "UnidadMedida")
    # Las botellas se venden completas o por tragos: el stock queda en fracciones de botella (0,96 = abierta)
    UnidadMedida.objects.get_or_create(nombre="Botella", defaults={"abreviatura": "bot", "permite_decimales": True})


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0007_fase9")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]

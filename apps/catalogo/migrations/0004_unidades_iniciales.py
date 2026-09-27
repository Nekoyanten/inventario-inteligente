from django.db import migrations

UNIDADES = [
    ("Unidad", "und", False), ("Kilogramo", "kg", True), ("Gramo", "g", True), ("Litro", "L", True),
    ("Mililitro", "ml", True), ("Metro", "m", True), ("Caja", "caja", False), ("Paquete", "paq", False),
    ("Docena", "doc", False), ("Par", "par", False),
]


def crear(apps, schema_editor):
    UnidadMedida = apps.get_model("catalogo", "UnidadMedida")
    for nombre, abrev, dec in UNIDADES:
        UnidadMedida.objects.get_or_create(nombre=nombre, defaults={"abreviatura": abrev, "permite_decimales": dec})


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0003_variantes")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]

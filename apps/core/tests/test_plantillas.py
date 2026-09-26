import pytest

from apps.catalogo.models import AtributoPersonalizado
from apps.core.models import Giro, Negocio


@pytest.mark.django_db
def test_plantilla_ropa_activa_variantes_y_atributos():
    n = Negocio.objects.create(nombre="Boutique", giro=Giro.ROPA)
    assert n.config.usa_variantes and not n.config.usa_vencimientos
    assert AtributoPersonalizado.objects.filter(categoria__negocio=n, nombre="Talla").exists()


@pytest.mark.django_db
def test_plantilla_farmacia_activa_vencimientos_largos():
    n = Negocio.objects.create(nombre="Droguería", giro=Giro.FARMACIA)
    assert n.config.usa_vencimientos and n.config.usa_lotes
    assert n.config.dias_vencimiento_amarillo == 90

"""El simulador del piloto recorre los servicios reales; esta prueba corta asegura que no se rompa."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.catalogo.models import Producto
from apps.core.simulacion.motor import SimuladorNegocio
from apps.core.simulacion.perfiles import PERFILES
from apps.ventas.models import Venta


def _perfil(clave, **cambios):
    perfil = dict(next(p for p in PERFILES if p["clave"] == clave))
    perfil.update(cambios)
    return perfil


@pytest.mark.django_db
def test_simulacion_corta_con_cambio_de_proveedor():
    perfil = _perfil("farma-salud-total", productos=40, tickets=15, cambia_proveedor=3)
    inicio = timezone.localdate() - timedelta(days=8)
    sim = SimuladorNegocio(perfil, inicio, 8, semilla=1).crear()
    for n in range(8):
        sim.simular_dia(n)
    r = sim.cerrar().resumen()

    assert r["productos"] == 40
    assert r["ventas"]["tickets"] > 0
    assert Venta.objects.filter(negocio=sim.negocio).exists()
    assert r["cambio_proveedor"]["a"] == "Proveedor Confiable S.A.S."
    assert not Producto.objects.filter(negocio=sim.negocio, proveedor_principal__activo=False).exists()


@pytest.mark.django_db
def test_simulacion_ropa_crea_variantes_sin_alertas_en_agrupadores():
    perfil = _perfil("ropa-kids", productos=30, tickets=6)
    sim = SimuladorNegocio(perfil, timezone.localdate() - timedelta(days=3), 3, semilla=2).crear()
    for n in range(3):
        sim.simular_dia(n)
    sim.cerrar()
    assert Producto.objects.filter(negocio=sim.negocio, es_agrupador=True).exists()
    assert not Alerta.objects.filter(negocio=sim.negocio, producto__es_agrupador=True).exists()


@pytest.mark.django_db
def test_simulacion_antes_de_la_fase8_bloquea_ventas_sin_stock():
    perfil = _perfil("mini-la-esquina", productos=30, tickets=12)
    sim = SimuladorNegocio(perfil, timezone.localdate() - timedelta(days=4), 4, semilla=3, fase8=False).crear()
    for n in range(4):
        sim.simular_dia(n)
    r = sim.cerrar().resumen()
    assert r["fase8"] is False and r["exactitud"]["ventas_sin_stock_con_ajuste"] == 0
    assert not sim.negocio.config.permite_venta_sin_stock


@pytest.mark.django_db
def test_simulacion_nocturna_corta():
    from apps.core.simulacion.nocturno import ejecutar
    from apps.core.simulacion.perfiles_nocturnos import PERFILES_NOCTURNOS
    from apps.nocturno.models import Cuenta

    perfil = dict(next(p for p in PERFILES_NOCTURNOS if p["clave"] == "disco-son-loma"), pool=150)
    perfil["dias"] = {d: 6 for d in perfil["dias"]}
    r = ejecutar(perfil, dias=8, semilla=4)
    assert r["noches"] >= 3 and r["ventas"] > 0 and r["clientes_registrados"] > 0
    assert not Cuenta.objects.filter(estado="ABIERTA").exists()  # todas las cuentas se cobraron o anularon

"""El simulador del piloto recorre los servicios reales; esta prueba corta asegura que no se rompa."""

import io
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


@pytest.mark.django_db
def test_demo_de_negocios_crea_la_tienda_de_vapeadores_en_plan_gratis(client):
    from django.core.management import call_command

    from apps.clientes.models import Cliente, Encuesta
    from apps.core.models import Negocio
    from apps.core.simulacion.demo_negocios import CLAVE_DEMO

    call_command("cargar_demo_negocios", dias=8, solo=["vape.nube"], stdout=io.StringIO())
    n = Negocio.objects.get(nombre="Nube Vape Shop")
    assert n.giro == "VAPE" and n.suscripcion.plan_efectivo == "GRATIS"
    assert Producto.objects.filter(negocio=n, es_agrupador=False).count() <= n.suscripcion.limites["productos"]
    assert n.proveedores.filter(nombre__startswith="Vaporesso").exists()
    assert Producto.objects.filter(negocio=n, marca__nombre="Vaporesso").exists()
    clientes = Cliente.objects.filter(negocio=n)
    assert clientes.exists() and not clientes.filter(mayor_edad_verificado=False).exists()  # Ley 2354
    assert not clientes.filter(nombre__startswith="Cliente ").exists() and Encuesta.objects.filter(negocio=n).exists()
    assert Venta.objects.filter(negocio=n, cliente_ref__isnull=False).exists()
    assert client.login(username="vape.nube", password=CLAVE_DEMO)
    for url in ("/", "/clientes/", "/clientes/ofertas/", "/negocio/plan/"):
        assert client.get(url, follow=True).status_code == 200
    call_command("cargar_demo_negocios", borrar=True, stdout=io.StringIO())
    assert not Negocio.objects.filter(nombre="Nube Vape Shop").exists()


@pytest.mark.django_db
def test_demo_se_retoma_si_se_corto_y_no_duplica_lo_completo():
    from django.core.management import call_command

    from apps.core.models import Negocio

    nulo = open("/dev/null", "w")
    call_command("cargar_demo_negocios", dias=3, solo=["vape.nube"], stdout=nulo)
    completo = Negocio.objects.get(nombre="Nube Vape Shop")
    # otra corrida (p. ej. el servidor se reinició): lo completo no se toca
    call_command("cargar_demo_negocios", dias=3, solo=["vape.nube"], stdout=nulo)
    assert Negocio.objects.get(nombre="Nube Vape Shop").pk == completo.pk
    # una carga cortada a medias (sin la marca de completa) se borra y se vuelve a crear
    s = completo.suscripcion
    s.notas = ""
    s.save()
    call_command("cargar_demo_negocios", dias=3, solo=["vape.nube"], stdout=nulo)
    nuevo = Negocio.objects.get(nombre="Nube Vape Shop")
    assert nuevo.pk != completo.pk and "Negocio de demostración" in nuevo.suscripcion.notas

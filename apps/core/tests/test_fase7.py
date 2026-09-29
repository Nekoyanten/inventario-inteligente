from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.arranque import progreso_arranque
from apps.core.models import EjecucionTarea
from apps.core.salud import configuracion, revisar
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.usuarios.models import Usuario
from apps.ventas.services import registrar_venta


@pytest.fixture
def dueno_plataforma(db):
    return Usuario.objects.create_superuser("dueno", "d@d.co", "x")


def test_panel_solo_para_el_dueno_de_la_plataforma(client, admin, dueno_plataforma):
    client.force_login(admin)  # administrador de un negocio
    assert client.get("/plataforma/").status_code == 302
    client.force_login(dueno_plataforma)
    resp = client.get("/plataforma/")
    assert resp.status_code == 200 and "Crear negocio" in resp.content.decode()


def test_metricas_del_piloto(client, admin, producto, dueno_plataforma):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=50, usuario=admin)
    for d in range(3):
        registrar_venta(negocio=producto.negocio, vendedor=admin, fecha=timezone.now() - timedelta(days=d),
                        lineas=[{"producto": producto, "cantidad": 1}])
    client.force_login(dueno_plataforma)
    fila = client.get("/plataforma/").context["filas"][0]
    assert fila["dias_activos"] == 3 and fila["ventas_7d"] == 3 and fila["plan"] == "Prueba"
    csv = client.get("/plataforma/?formato=csv").content.decode("utf-8-sig")
    assert "Días con ventas" in csv and producto.negocio.nombre in csv


def test_salud_y_configuracion(db):
    r = revisar(completo=True)
    assert r["base_de_datos"]["ok"] and r["cache"]["ok"] and r["almacenamiento"]["ok"]
    nombres = [c["nombre"] for c in configuracion()]
    assert any("SENTRY_DSN" in n for n in nombres) and any("AWS_STORAGE_BUCKET_NAME" in n for n in nombres)


def test_salud_responde_503_si_falla_la_base(client, db):
    with mock.patch("apps.core.salud.base_de_datos", side_effect=RuntimeError("caída")):
        resp = client.get("/salud/")
    assert resp.status_code == 503 and resp.json()["estado"] == "error"


def test_tareas_quedan_registradas_y_un_negocio_con_error_no_frena_a_los_demas(negocio, producto):
    with mock.patch("apps.alertas.management.commands.analizar_inventario.evaluar_negocio",
                    side_effect=[RuntimeError("datos raros"), 0]):
        from apps.core.models import Giro, Negocio

        Negocio.objects.create(nombre="Segundo", giro=Giro.GENERICO)
        call_command("analizar_inventario", stdout=StringIO())
    t = EjecucionTarea.objects.get(nombre="analizar_inventario")
    assert t.ok and "ERROR en" in t.detalle and "Segundo" in t.detalle
    assert revisar(completo=True)["tareas"]["ok"]


def test_alerta_si_el_analisis_nocturno_no_corre(db):
    EjecucionTarea.objects.create(nombre="analizar_inventario", ok=True, fin=timezone.now())
    EjecucionTarea.objects.update(inicio=timezone.now() - timedelta(hours=30))
    r = revisar(completo=True)["tareas"]
    assert not r["ok"] and "no corre hace" in r["detalle"]


def test_lista_de_arranque(client, admin, negocio, producto):
    p = progreso_arranque(negocio)
    assert not p["completo"] and p["total"] == 6
    client.force_login(admin)
    assert "Tu arranque" in client.get("/").content.decode()

import pytest

from apps.core.models import RegistroAuditoria
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def vendedor(negocio):
    return Usuario.objects.create_user("vende", password="x", negocio=negocio, rol=Rol.VENDEDOR)


def _datos(negocio, **cambios):
    c = negocio.config
    datos = {
        "n-nombre": negocio.nombre, "n-nit": "", "n-telefono": "", "n-direccion": "",
        "c-dias_vencimiento_rojo": c.dias_vencimiento_rojo, "c-dias_vencimiento_amarillo": c.dias_vencimiento_amarillo,
        "c-dias_sin_movimiento": c.dias_sin_movimiento, "c-dias_exceso": c.dias_exceso,
        "c-horizonte_compra_dias": c.horizonte_compra_dias, "c-tiempo_entrega_defecto": c.tiempo_entrega_defecto,
        "c-usa_vencimientos": "on",
    }
    datos.update(cambios)
    return datos


def test_admin_cambia_banderas(client, admin, negocio):
    client.force_login(admin)
    resp = client.post("/negocio/configuracion/", _datos(negocio, **{"c-usa_variantes": "on"}))
    assert resp.status_code == 302
    negocio.config.refresh_from_db()
    assert negocio.config.usa_variantes and negocio.config.usa_vencimientos and not negocio.config.usa_lotes
    assert RegistroAuditoria.objects.filter(accion="configurar_negocio").exists()


def test_valida_umbrales_de_vencimiento(client, admin, negocio):
    client.force_login(admin)
    resp = client.post("/negocio/configuracion/", _datos(negocio, **{"c-dias_vencimiento_rojo": 40}))
    assert resp.status_code == 200 and "mayor o igual" in resp.content.decode()


def test_vendedor_no_configura(client, vendedor):
    client.force_login(vendedor)
    assert client.get("/negocio/configuracion/").status_code == 403


def test_bitacora_filtra_por_accion(client, admin, negocio):
    client.force_login(admin)
    client.post("/negocio/configuracion/", _datos(negocio))
    resp = client.get("/negocio/auditoria/?accion=configurar_negocio")
    assert resp.status_code == 200 and len(resp.context["pagina"]) == 1


def test_menu_segun_rol(client, admin, vendedor):
    client.force_login(vendedor)
    textos = [i["texto"] for i in client.get("/").context["menu"]]
    assert "Usuarios" not in textos and "Ajustes" not in textos
    client.force_login(admin)
    textos = [i["texto"] for i in client.get("/").context["menu"]]
    assert "Usuarios" in textos and "Ajustes" in textos

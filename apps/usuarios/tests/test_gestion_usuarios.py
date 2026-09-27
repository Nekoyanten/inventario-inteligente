import pytest

from apps.core.models import Giro, Negocio, RegistroAuditoria
from apps.inventario.models import TipoMovimiento
from apps.usuarios.models import Rol, Usuario
from apps.usuarios.permisos import PERMISOS_POR_ROL


@pytest.fixture
def vendedor(negocio):
    return Usuario.objects.create_user("vende", password="x", negocio=negocio, rol=Rol.VENDEDOR)


@pytest.fixture
def usuario_ajeno(db):
    otro = Negocio.objects.create(nombre="Otro", giro=Giro.GENERICO)
    return Usuario.objects.create_user("ajeno", password="x", negocio=otro, rol=Rol.VENDEDOR)


def test_admin_crea_usuario_en_su_negocio(client, admin):
    client.force_login(admin)
    resp = client.post("/usuarios/nuevo/", {
        "username": "ana", "first_name": "Ana", "rol": Rol.INVENTARIO,
        "password1": "ClaveSegura123!", "password2": "ClaveSegura123!",
    })
    assert resp.status_code == 302
    ana = Usuario.objects.get(username="ana")
    assert ana.negocio == admin.negocio and ana.rol == Rol.INVENTARIO
    assert RegistroAuditoria.objects.filter(accion="crear_usuario").exists()


def test_lista_solo_muestra_usuarios_del_negocio(client, admin, vendedor, usuario_ajeno):
    client.force_login(admin)
    usuarios = list(client.get("/usuarios/").context["usuarios"])
    assert vendedor in usuarios and usuario_ajeno not in usuarios


def test_no_puede_editar_usuario_de_otro_negocio(client, admin, usuario_ajeno):
    client.force_login(admin)
    assert client.get(f"/usuarios/{usuario_ajeno.pk}/").status_code == 404


def test_vendedor_no_gestiona_usuarios(client, vendedor):
    client.force_login(vendedor)
    assert client.get("/usuarios/").status_code == 403


def test_admin_no_puede_desactivarse(client, admin):
    client.force_login(admin)
    resp = client.post(f"/usuarios/{admin.pk}/", {"rol": Rol.ADMIN, "is_active": ""})
    assert resp.status_code == 200 and "No puedes desactivar" in resp.content.decode()
    admin.refresh_from_db()
    assert admin.is_active


def test_matriz_de_permisos():
    assert "registrar_venta" in PERMISOS_POR_ROL[Rol.VENDEDOR]
    assert "registrar_movimiento" not in PERMISOS_POR_ROL[Rol.VENDEDOR]   # vendedor no hace ajustes
    assert "aprobar_ajuste" not in PERMISOS_POR_ROL[Rol.INVENTARIO]      # encargado registra, admin aprueba
    assert "ver_reportes_financieros" not in PERMISOS_POR_ROL[Rol.INVENTARIO]
    assert TipoMovimiento.SALIDA_AJUSTE  # referencia usada en issue de entradas/salidas


def test_vendedor_no_ve_reportes(client, vendedor):
    client.force_login(vendedor)
    assert client.get("/reportes/inventario-actual.csv").status_code == 403

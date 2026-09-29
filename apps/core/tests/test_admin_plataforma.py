"""El administrador de la plataforma (superusuario) tiene el control de todo: entra a cualquier negocio para dar
soporte, cambia planes, y todo queda en la bitácora. Nadie más puede hacerlo."""

import pytest

from apps.core.models import Negocio, RegistroAuditoria
from apps.usuarios.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def plataforma(client):
    root = Usuario.objects.create_superuser("neko", "neko@example.com", "clave-larga-123")
    client.force_login(root)
    return root


def test_inicio_lleva_al_panel_y_se_ve_como_administrador_de_la_plataforma(client, plataforma, negocio):
    r = client.get("/", follow=True)
    assert r.redirect_chain[-1][0].endswith("/plataforma/")
    html = r.content.decode()
    assert "Administrador de la plataforma" in html and "Vendedor" not in html and negocio.nombre in html


def test_entrar_a_un_negocio_ver_todo_y_salir(client, plataforma, negocio, producto):
    r = client.post(f"/plataforma/negocios/{negocio.pk}/entrar/", follow=True)
    html = r.content.decode()
    assert "como administrador de la plataforma" in html and "Ventas" in html  # su panel de administrador
    assert producto.nombre in client.get("/productos/").content.decode()
    assert client.get("/negocio/configuracion/").status_code == 200  # puede configurar su negocio
    assert RegistroAuditoria.objects.filter(negocio=negocio, accion="soporte_entrar", usuario=plataforma).exists()
    r = client.post("/plataforma/salir-del-negocio/", follow=True)
    assert r.redirect_chain[-1][0].endswith("/plataforma/")
    assert RegistroAuditoria.objects.filter(negocio=negocio, accion="soporte_salir").exists()
    assert client.get("/productos/").status_code == 403  # fuera del negocio ya no ve sus productos


def test_cambiar_plan(client, plataforma, negocio):
    client.post(f"/plataforma/negocios/{negocio.pk}/plan/", {"plan": "EMPRENDEDOR", "dias": "60"})
    s = Negocio.objects.get(pk=negocio.pk).suscripcion
    assert s.plan_efectivo == "EMPRENDEDOR" and s.dias_restantes == 60 and s.prueba_hasta is None
    client.post(f"/plataforma/negocios/{negocio.pk}/plan/", {"plan": "GRATIS"})
    assert Negocio.objects.get(pk=negocio.pk).suscripcion.plan_efectivo == "GRATIS"
    client.post(f"/plataforma/negocios/{negocio.pk}/plan/", {"plan": "ORO"})  # inválido: no cambia nada
    assert Negocio.objects.get(pk=negocio.pk).suscripcion.plan == "GRATIS"
    assert RegistroAuditoria.objects.filter(negocio=negocio, accion="cambiar_plan").count() == 2


def test_un_administrador_de_negocio_no_puede_usar_la_plataforma(client, negocio):
    otro = Negocio.objects.create(nombre="Otro")
    jefe = Usuario.objects.create_user("jefe", password="x", negocio=negocio, rol=Rol.ADMIN)
    client.force_login(jefe)
    assert client.get("/plataforma/").status_code in (302, 403)
    client.post(f"/plataforma/negocios/{otro.pk}/entrar/")
    client.post(f"/plataforma/negocios/{otro.pk}/plan/", {"plan": "NEGOCIO"})
    s = client.session
    assert "negocio_soporte" not in s
    assert Negocio.objects.get(pk=otro.pk).suscripcion.plan == "GRATIS"
    assert not RegistroAuditoria.objects.filter(accion__in=["soporte_entrar", "cambiar_plan"]).exists()
    # y aunque meta a mano el negocio en la sesión, sigue viendo solo el suyo
    s["negocio_soporte"] = otro.pk
    s.save()
    r = client.get("/")
    assert r.context["negocio"] == negocio


def test_entrar_solo_por_post(client, plataforma, negocio):
    assert client.get(f"/plataforma/negocios/{negocio.pk}/entrar/").status_code == 405

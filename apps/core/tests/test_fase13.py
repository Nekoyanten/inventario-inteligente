"""Fase 13: planes a la medida desde la plataforma, alta de negocios y apariencia de cada negocio."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.limites import LimiteDelPlan, verificar_productos
from apps.core.models import Negocio, RegistroAuditoria
from apps.usuarios.models import Rol, Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def root(client):
    u = Usuario.objects.create_superuser("neko", "neko@example.com", "clave-larga-123")
    client.force_login(u)
    return u


def _sin_prueba(negocio, plan="GRATIS"):
    s = negocio.suscripcion
    s.plan, s.prueba_hasta = plan, None
    s.pagado_hasta = None if plan == "GRATIS" else timezone.localdate() + timedelta(days=30)
    s.save()
    return s


def test_plan_a_la_medida_limites_y_modulos(client, root, negocio):
    _sin_prueba(negocio)
    r = client.post(f"/plataforma/negocios/{negocio.pk}/", {
        "plan": "GRATIS", "limite_productos": "120", "limite_usuarios": "4", "reportes_pdf": "1", "api": "",
        "modulos": ["compras", "reportes"], "notas": "Pagó por Nequi"})
    assert r.status_code == 302
    s = Negocio.objects.get(pk=negocio.pk).suscripcion
    assert s.limites["productos"] == 120 and s.limites["usuarios"] == 4 and s.limites["reportes_pdf"] is True
    assert s.limites["api"] is False and s.limites["nombre"] == "Gratis a la medida"
    assert not s.tiene_modulo("clientes") and s.tiene_modulo("compras") and s.notas == "Pagó por Nequi"
    assert RegistroAuditoria.objects.filter(negocio=negocio, accion="ajustar_plan").exists()


def test_modulo_apagado_no_se_abre_ni_sale_en_el_menu(client, negocio, admin):
    s = _sin_prueba(negocio)
    s.modulos_apagados = ["clientes"]
    s.save()
    client.force_login(admin)
    r = client.get("/clientes/")
    assert r.status_code == 403 and "no está activo en tu plan" in r.content.decode()
    assert "/clientes/" not in client.get("/").content.decode()  # tampoco en el menú
    s.modulos_apagados = []
    s.save()
    assert client.get("/clientes/").status_code == 200


def test_limite_a_la_medida_se_aplica(negocio):
    s = _sin_prueba(negocio)
    s.limite_productos = 1
    s.save()
    verificar_productos(negocio)
    from apps.catalogo.models import Producto

    Producto.objects.create(negocio=negocio, sku="A", nombre="A")
    with pytest.raises(LimiteDelPlan):
        verificar_productos(negocio)


def test_plan_vencido_vuelve_a_lo_basico(negocio):
    s = _sin_prueba(negocio, "NEGOCIO")
    s.limite_productos = 9000
    s.pagado_hasta = timezone.localdate() - timedelta(days=1)
    s.save()
    assert s.vencido and s.limites["productos"] == 50


def test_crear_negocio_desde_la_plataforma(client, root):
    r = client.post("/plataforma/negocios/nuevo/", {
        "nombre": "Cafetería Luna", "giro": "RESTAURANTE", "telefono": "3001234567", "dueno": "María Pérez",
        "usuario": "cafe.luna", "correo": "maria@example.com", "plan": "EMPRENDEDOR", "dias": "60"})
    html = r.content.decode()
    n = Negocio.objects.get(nombre="Cafetería Luna")
    dueno = Usuario.objects.get(username="cafe.luna")
    assert dueno.negocio == n and dueno.rol == Rol.ADMIN
    assert n.categorias.exists()  # plantilla del giro aplicada
    assert n.suscripcion.plan_efectivo == "EMPRENDEDOR" and n.suscripcion.dias_restantes == 60
    clave = html.split("Clave temporal: ")[1].split("\n")[0].strip()
    assert dueno.check_password(clave) and "wa.me/573001234567" in html
    assert RegistroAuditoria.objects.filter(negocio=n, accion="crear_negocio").exists()
    # usuario repetido: no crea nada
    client.post("/plataforma/negocios/nuevo/", {"nombre": "Otra", "giro": "ROPA", "dueno": "X", "usuario": "cafe.luna",
                                                 "plan": "GRATIS", "dias": "30"})
    assert not Negocio.objects.filter(nombre="Otra").exists()


def test_solo_la_plataforma_administra_y_crea(client, negocio, admin):
    client.force_login(admin)
    assert client.get(f"/plataforma/negocios/{negocio.pk}/").status_code in (302, 403)
    client.post("/plataforma/negocios/nuevo/", {"nombre": "Pirata", "giro": "ROPA", "dueno": "X", "usuario": "pirata",
                                                 "plan": "NEGOCIO", "dias": "999"})
    assert not Negocio.objects.filter(nombre="Pirata").exists()


def test_mi_plan_muestra_lo_que_tiene_y_como_pedir_cambios(client, admin, negocio, settings):
    settings.CONTACTO_VENTAS = "573001112233"
    s = _sin_prueba(negocio)
    s.modulos_apagados = ["reportes"]
    s.save()
    client.force_login(admin)
    html = client.get("/negocio/plan/").content.decode()
    assert "a la medida" in html and "wa.me/573001112233" in html and "(no incluido)" in html
    assert "/mes" not in html  # ya no hay tarjetas de precios para elegir


def _png():
    import io

    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (40, 20), "#ff0000").save(b, format="PNG")
    return SimpleUploadedFile("logo.png", b.getvalue(), content_type="image/png")


def test_apariencia_color_modo_letra_y_logo(client, admin, negocio, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client.force_login(admin)
    r = client.post("/negocio/apariencia/", {"color_principal": "#7c3aed", "tema": "OSCURO", "letra_grande": "on",
                                             "logo": _png()})
    assert r.status_code == 302
    html = client.get("/").content.decode()
    assert "--marca:#7c3aed" in html and 'data-tema="oscuro"' in html and 'class="letra-grande"' in html
    assert "logo-negocio" in html
    negocio.config.refresh_from_db()
    assert negocio.config.logo.name.endswith(".webp")  # optimizado
    r = client.post("/negocio/apariencia/", {"color_principal": "rojo", "tema": "AUTO"})
    assert r.status_code == 200 and r.context["form"].errors["color_principal"]  # color inválido: no se guarda


def test_apariencia_solo_administrador(client, negocio):
    v = Usuario.objects.create_user("mesero", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    client.force_login(v)
    assert client.get("/negocio/apariencia/").status_code == 403


def test_color_claro_sigue_legible():
    from apps.core.apariencia import tokens

    t = tokens("#fde047")  # amarillo claro
    assert t["sobre"] == "#111827"  # texto oscuro sobre el botón
    assert t["texto"] != "#fde047"  # enlaces oscurecidos para leerse sobre blanco

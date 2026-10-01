from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.core.limites import LimiteDelPlan, verificar_productos
from apps.core.models import Comentario, Suscripcion
from apps.usuarios.models import Usuario


@pytest.fixture(autouse=True)
def limpiar_cache():
    cache.clear()


def _vencer_prueba(negocio, plan="GRATIS"):
    s = negocio.suscripcion
    s.prueba_hasta = timezone.localdate() - timedelta(days=1)
    s.plan = plan
    s.save()


def test_negocio_nuevo_empieza_en_prueba_con_todo(negocio):
    s = negocio.suscripcion
    assert s.en_prueba and s.plan_efectivo == Suscripcion.Plan.NEGOCIO


def test_limite_de_productos_en_plan_gratis(negocio):
    _vencer_prueba(negocio)
    Producto.objects.bulk_create([Producto(negocio=negocio, sku=f"P{i}", nombre=f"P{i}") for i in range(50)])
    with pytest.raises(LimiteDelPlan):
        verificar_productos(negocio)


def test_plan_vencido_no_bloquea_datos_solo_limita(client, admin, negocio, producto):
    _vencer_prueba(negocio, plan="EMPRENDEDOR")  # sin pagado_hasta → vencido
    client.force_login(admin)
    html = client.get("/").content.decode()
    assert "Tu plan venció" in html
    assert client.get(f"/productos/{producto.pk}/").status_code == 200


def test_limite_de_usuarios(client, admin, negocio):
    _vencer_prueba(negocio)
    client.force_login(admin)
    resp = client.post("/usuarios/nuevo/", {"username": "otro", "rol": "VENDEDOR", "password1": "ClaveSegura123!",
                                            "password2": "ClaveSegura123!"})
    assert "permite 1 usuario" in resp.content.decode() and not Usuario.objects.filter(username="otro").exists()


def test_api_requiere_plan_negocio(admin, negocio):
    from rest_framework.test import APIClient

    _vencer_prueba(negocio)
    c = APIClient()
    c.force_authenticate(admin)
    assert c.get("/api/v1/productos/").status_code == 403


def test_bloqueo_por_intentos_fallidos(client, admin):
    for _ in range(5):
        client.post("/ingresar/", {"username": "admin", "password": "mala"})
    resp = client.post("/ingresar/", {"username": "admin", "password": "x"})  # la clave correcta ya no sirve
    assert "Demasiados intentos" in resp.content.decode()


def test_paginas_publicas(client, db):
    for url in ("/ayuda/", "/terminos/", "/privacidad/", "/salud/", "/clave/recuperar/"):
        assert client.get(url).status_code == 200, url


def test_comentarios_y_exportar_datos(client, admin, producto):
    client.force_login(admin)
    client.post("/comentarios/", {"tipo": "IDEA", "texto": "Me gustaría ver ventas por hora", "calificacion": "5"})
    assert Comentario.objects.get().calificacion == 5
    resp = client.get("/negocio/exportar-datos/")
    assert resp["Content-Type"] == "application/zip" and resp.content[:2] == b"PK"


MATRIZ = [
    # (url, vendedor, encargado)
    ("/ventas/vender/", 200, 403),
    ("/inventario/", 403, 200),
    ("/compras/", 403, 200),
    ("/proveedores/", 403, 200),  # bodega: compras y proveedores van juntos
    ("/usuarios/", 403, 403),
    ("/negocio/configuracion/", 403, 403),
    ("/reportes/utilidad/", 403, 403),
    ("/alertas/", 403, 200),
    ("/productos/", 200, 200),
]


@pytest.mark.parametrize("url,vendedor,encargado", MATRIZ)
def test_matriz_de_permisos_por_rol(client, negocio, url, vendedor, encargado):
    v = Usuario.objects.create_user("v", password="x", negocio=negocio, rol="VENDEDOR")
    e = Usuario.objects.create_user("e", password="x", negocio=negocio, rol="INVENTARIO")
    client.force_login(v)
    assert client.get(url).status_code == vendedor
    client.force_login(e)
    assert client.get(url).status_code == encargado


def test_no_hay_redireccion_abierta(client, admin):
    client.force_login(admin)
    resp = client.post("/comentarios/", {"texto": "hola", "pagina": "https://sitio-malicioso.example/robar"})
    assert resp["Location"] == "/"
    resp = client.post("/comentarios/", {"texto": "hola", "pagina": "/productos/"})
    assert resp["Location"] == "/productos/"


def test_importacion_rechaza_archivos_grandes(client, admin, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.TAMANO_MAX_ARCHIVO_MB = 0
    client.force_login(admin)
    archivo = SimpleUploadedFile("p.csv", b"sku,nombre\nA,B\n")
    assert "supera" in client.post("/reportes/importar/", {"archivo": archivo}).content.decode()

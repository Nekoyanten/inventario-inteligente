"""Clientes habituales: puntos, niveles, ofertas, WhatsApp, encuestas, análisis y datos personales."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto
from apps.clientes import analisis
from apps.clientes.models import Cliente, Encuesta, MovimientoPuntos, Nivel, Oferta, Segmento
from apps.clientes.services import ErrorClientes, cotizar, normalizar_telefono, recalcular, registrar_envio, url_whatsapp
from apps.clientes.sugerencias import crear_desde_sugerencia, sugerir
from apps.core.models import Negocio
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.usuarios.models import Rol, Usuario
from apps.ventas.models import Venta
from apps.ventas.services import anular_venta, registrar_venta

pytestmark = pytest.mark.django_db
HOY = timezone.localdate()


@pytest.fixture
def cliente(negocio):
    return Cliente.objects.create(negocio=negocio, nombre="Rosa Burbano", telefono="3001234567", acepta_datos=True,
                                  acepta_ofertas=True)


@pytest.fixture
def surtido(producto, admin):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=500, usuario=admin)
    producto.refresh_from_db()
    return producto


def _vender(negocio, admin, producto, cantidad=2, cliente=None, puntos=0, fecha=None):
    return registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": cantidad}],
                           cliente_ref=cliente, puntos_canjear=puntos, fecha=fecha)


# ---------------------------------------------------------------- puntos y niveles
def test_venta_con_cliente_gana_puntos_y_actualiza_su_historia(negocio, admin, surtido, cliente):
    venta = _vender(negocio, admin, surtido, 2, cliente)  # 2 × 12.000 = 24.000 → 24 puntos
    cliente.refresh_from_db()
    assert venta.puntos_ganados == 24 and cliente.puntos == 24
    assert cliente.n_compras == 1 and cliente.total_compras == 24000 and venta.cliente == "Rosa Burbano"
    assert MovimientoPuntos.objects.get(cliente=cliente).tipo == MovimientoPuntos.Tipo.GANADOS


def test_canje_de_puntos_descuenta_y_reparte_en_las_lineas(negocio, admin, surtido, cliente):
    Cliente.objects.filter(pk=cliente.pk).update(puntos=150)
    cliente.refresh_from_db()
    venta = _vender(negocio, admin, surtido, 2, cliente, puntos=100)  # 100 × $10 = $1.000
    cliente.refresh_from_db()
    assert venta.total == 23000 and venta.descuento_puntos == 1000 and venta.puntos_canjeados == 100
    assert sum(d.descuento for d in venta.detalles.all()) == 1000  # los reportes de utilidad lo ven
    assert cliente.puntos == 150 - 100 + 23


def test_canje_invalido(negocio, admin, surtido, cliente):
    Cliente.objects.filter(pk=cliente.pk).update(puntos=150)
    cliente.refresh_from_db()
    with pytest.raises(ErrorClientes, match="desde 100"):
        _vender(negocio, admin, surtido, 1, cliente, puntos=50)
    with pytest.raises(ErrorClientes, match="tiene 150"):
        _vender(negocio, admin, surtido, 1, cliente, puntos=200)
    with pytest.raises(ErrorClientes, match="identifica"):
        _vender(negocio, admin, surtido, 1, None, puntos=100)
    assert not Venta.objects.exists()


def test_no_se_gastan_puntos_de_mas(negocio, admin, surtido, cliente):
    Cliente.objects.filter(pk=cliente.pk).update(puntos=5000)
    cliente.refresh_from_db()
    venta = _vender(negocio, admin, surtido, 1, cliente, puntos=5000)  # $50.000 en puntos para una compra de $12.000
    assert venta.total == 0 and venta.puntos_canjeados == 1200


def test_anular_devuelve_los_puntos(negocio, admin, surtido, cliente):
    Cliente.objects.filter(pk=cliente.pk).update(puntos=200)
    cliente.refresh_from_db()
    venta = _vender(negocio, admin, surtido, 2, cliente, puntos=100)
    cliente.refresh_from_db()
    assert cliente.puntos == 200 - 100 + 23
    anular_venta(venta, admin, "Error")
    cliente.refresh_from_db()
    assert cliente.puntos == 200 and cliente.n_compras == 0


def test_niveles_y_multiplicador(negocio, admin, surtido, cliente):
    for _ in range(4):
        _vender(negocio, admin, surtido, 1, cliente)
    cliente.refresh_from_db()
    assert cliente.nivel == Nivel.FRECUENTE
    venta = _vender(negocio, admin, surtido, 1, cliente)
    assert venta.puntos_ganados == 15  # 12 × 1,25
    _vender(negocio, admin, surtido, 40, cliente)  # $480.000 → pasa los $500.000 en 90 días
    cliente.refresh_from_db()
    assert cliente.nivel == Nivel.VIP


def test_telefono_normalizado_y_whatsapp():
    assert normalizar_telefono("+57 300 123 4567") == "3001234567"
    assert url_whatsapp("300 123 4567", "Hola").startswith("https://wa.me/573001234567?text=Hola")


# ---------------------------------------------------------------- ofertas
def test_oferta_para_todos_aplica_sin_cliente_y_respeta_el_costo(negocio, admin, surtido):
    cat = surtido.categoria
    Oferta.objects.create(negocio=negocio, titulo="Semana del café", descuento_pct=50, categoria=cat,
                          segmento=Segmento.TODOS, desde=HOY, hasta=HOY)
    venta = _vender(negocio, admin, surtido, 1)
    detalle = venta.detalles.get()
    # margen = (12.000 − 8.500) / 12.000 = 29,17 % → el 50 % se limita para no vender a pérdida
    assert detalle.descuento == 3500 and detalle.oferta.titulo == "Semana del café"
    assert venta.total == 8500


def test_oferta_vip_solo_para_vip(negocio, admin, surtido, cliente):
    Oferta.objects.create(negocio=negocio, titulo="VIP", descuento_pct=10, segmento=Segmento.VIP, desde=HOY, hasta=HOY)
    assert _vender(negocio, admin, surtido, 1, cliente).total == 12000
    Cliente.objects.filter(pk=cliente.pk).update(nivel=Nivel.VIP)
    cliente.refresh_from_db()
    assert _vender(negocio, admin, surtido, 1, cliente).total == 10800


def test_oferta_vencida_no_aplica(negocio, admin, surtido):
    Oferta.objects.create(negocio=negocio, titulo="Vieja", descuento_pct=10, desde=HOY - timedelta(days=10),
                          hasta=HOY - timedelta(days=1))
    assert _vender(negocio, admin, surtido, 1).total == 12000


def test_cotizar_en_caja(client, negocio, admin, surtido, cliente):
    Cliente.objects.filter(pk=cliente.pk).update(puntos=300)
    Oferta.objects.create(negocio=negocio, titulo="Clientes", descuento_pct=10, segmento=Segmento.FRECUENTES,
                          desde=HOY, hasta=HOY)
    client.force_login(admin)
    cuerpo = {"lineas": [{"producto": surtido.pk, "cantidad": 2}], "cliente_id": cliente.pk, "puntos": 100}
    r = client.post("/ventas/cotizar/", json.dumps(cuerpo), content_type="application/json")
    d = r.json()
    assert r.status_code == 200 and d["total"] == 23000 and d["descuento_puntos"] == 1000 and d["puntos_ganados"] == 23
    assert d["ofertas"] == []  # el cliente es nuevo, la oferta es para frecuentes
    r = client.post("/ventas/registrar/", json.dumps(cuerpo), content_type="application/json")
    assert r.status_code == 200 and Venta.objects.get().cliente_ref == cliente


def test_caja_no_acepta_cliente_de_otro_negocio(client, negocio, admin, surtido):
    ajeno = Cliente.objects.create(negocio=Negocio.objects.create(nombre="Otro"), nombre="Ajeno", acepta_datos=True)
    client.force_login(admin)
    cuerpo = {"lineas": [{"producto": surtido.pk, "cantidad": 1}], "cliente_id": ajeno.pk}
    assert client.post("/ventas/registrar/", json.dumps(cuerpo), content_type="application/json").status_code == 400


def test_enviar_oferta_por_whatsapp_y_medir_retorno(client, negocio, admin, surtido, cliente):
    oferta = Oferta.objects.create(negocio=negocio, titulo="Te extrañamos", descuento_pct=10, desde=HOY, hasta=HOY,
                                   mensaje="Hola {nombre}, {descuento}% en {negocio}")
    client.force_login(admin)
    r = client.post(f"/clientes/ofertas/{oferta.pk}/enviar/{cliente.pk}/")
    assert r.status_code == 302 and r.url.startswith("https://wa.me/573001234567?text=Hola%20Rosa%2C%2010%25")
    _vender(negocio, admin, surtido, 1, cliente)
    e = analisis.efectividad(oferta)
    assert e["enviados"] == 1 and e["volvieron"] == 1 and e["ventas_con_oferta"] == 1


def test_no_se_envian_ofertas_sin_autorizacion(negocio, admin, cliente):
    oferta = Oferta.objects.create(negocio=negocio, titulo="X", descuento_pct=5, desde=HOY, hasta=HOY)
    cliente.acepta_ofertas = False
    cliente.save()
    with pytest.raises(ErrorClientes):
        registrar_envio(oferta, cliente, admin)
    from apps.clientes.services import destinatarios

    assert not destinatarios(oferta).exists()


def test_enviar_a_cliente_de_otro_negocio_da_404(client, negocio, admin):
    oferta = Oferta.objects.create(negocio=negocio, titulo="X", descuento_pct=5, desde=HOY, hasta=HOY)
    ajeno = Cliente.objects.create(negocio=Negocio.objects.create(nombre="Otro"), nombre="Ajeno", telefono="3009999999",
                                   acepta_datos=True, acepta_ofertas=True)
    client.force_login(admin)
    assert client.post(f"/clientes/ofertas/{oferta.pk}/enviar/{ajeno.pk}/").status_code == 404


def test_compradores_de_una_categoria(negocio, admin, surtido, cliente):
    from apps.clientes.services import destinatarios

    otro = Cliente.objects.create(negocio=negocio, nombre="Otro", telefono="3110000000", acepta_datos=True,
                                  acepta_ofertas=True)
    _vender(negocio, admin, surtido, 1, cliente)
    oferta = Oferta.objects.create(negocio=negocio, titulo="Café", descuento_pct=5, categoria=surtido.categoria,
                                   segmento=Segmento.COMPRADORES, desde=HOY, hasta=HOY)
    assert list(destinatarios(oferta)) == [cliente] and otro not in destinatarios(oferta)


# ---------------------------------------------------------------- encuesta
def test_encuesta_en_el_comprobante_y_respuesta_publica(client, negocio, admin, surtido, cliente):
    venta = _vender(negocio, admin, surtido, 1, cliente)
    client.force_login(admin)
    html = client.get(f"/ventas/{venta.pk}/").content.decode()
    enc = Encuesta.objects.get(venta=venta)
    assert f"/encuesta/{enc.token}/" in html and "wa.me/573001234567" in html
    client.logout()
    assert client.get(f"/encuesta/{enc.token}/").status_code == 200
    client.post(f"/encuesta/{enc.token}/", {"calificacion": "4", "comentario": "Faltaba cambio"})
    client.post(f"/encuesta/{enc.token}/", {"calificacion": "1", "comentario": "otra vez"})  # no se sobrescribe
    enc.refresh_from_db()
    assert enc.calificacion == 4 and enc.comentario == "Faltaba cambio" and enc.cliente == cliente
    assert analisis.satisfaccion(negocio)["promedio"] == 4
    assert client.get("/encuesta/token-que-no-existe/").status_code == 404


# ---------------------------------------------------------------- análisis
def test_segmentos_rfm(negocio, admin, surtido, cliente):
    ahora = timezone.now()
    for semanas in (12, 11, 10, 9, 8, 7):  # compraba cada semana y lleva 7 semanas sin venir
        _vender(negocio, admin, surtido, 1, cliente, fecha=ahora - timedelta(weeks=semanas))
    nuevo = Cliente.objects.create(negocio=negocio, nombre="Nuevo", acepta_datos=True)
    _vender(negocio, admin, surtido, 1, nuevo, fecha=ahora - timedelta(days=3))
    dormido = Cliente.objects.create(negocio=negocio, nombre="Dormido", acepta_datos=True)
    _vender(negocio, admin, surtido, 1, dormido, fecha=ahora - timedelta(days=120))
    seg = {f["cliente"].nombre: f["segmento"] for f in analisis.rfm(negocio)}
    assert seg == {"Rosa Burbano": "EN_RIESGO", "Nuevo": "NUEVO", "Dormido": "PERDIDO"}
    r = analisis.resumen(negocio)
    assert r["clientes"] == 3 and r["en_riesgo"][0]["cliente"] == cliente


def test_sugerencias_de_ofertas(negocio, admin, surtido, cliente):
    ahora = timezone.now()
    for semanas in (12, 11, 10, 9, 8, 7):
        _vender(negocio, admin, surtido, 1, cliente, fecha=ahora - timedelta(weeks=semanas))
    claves = {s["clave"].split("-")[0] for s in sugerir(negocio)}
    assert "regreso" in claves
    clave = next(s["clave"] for s in sugerir(negocio) if s["clave"].startswith("regreso"))
    oferta = crear_desde_sugerencia(negocio, clave, admin)
    assert oferta.segmento == Segmento.EN_RIESGO and oferta.origen == "SUGERIDA" and oferta.razon
    assert clave not in {s["clave"] for s in sugerir(negocio)}  # no se vuelve a sugerir


def test_sugerencia_de_producto_por_vencer(negocio, admin, surtido, cliente):
    from apps.inventario.models import Lote

    Lote.objects.create(producto=surtido, cantidad=20, fecha_vencimiento=HOY + timedelta(days=10))
    s = [x for x in sugerir(negocio) if x["clave"].startswith("vence")]
    assert s and s[0]["producto"] == surtido and s[0]["descuento_pct"] <= Decimal("17.5")  # 60 % del margen


# ---------------------------------------------------------------- datos personales y permisos
def test_registrar_cliente_exige_autorizacion(client, negocio, admin):
    client.force_login(admin)
    r = client.post("/clientes/nuevo.json", {"nombre": "Ana", "telefono": "300 555 1234", "activo": "on"})
    assert r.status_code == 400 and not Cliente.objects.exists()
    r = client.post("/clientes/nuevo.json", {"nombre": "Ana", "telefono": "+57 300 555 1234", "acepta_datos": "on",
                                             "activo": "on"})
    c = Cliente.objects.get()
    assert r.status_code == 200 and c.telefono == "3005551234" and c.fecha_autorizacion and not c.acepta_ofertas
    r = client.post("/clientes/nuevo.json", {"nombre": "Otra", "telefono": "3005551234", "acepta_datos": "on"})
    assert r.status_code == 400  # celular repetido


def test_vendedor_registra_clientes_pero_no_ve_el_panel(client, negocio, cliente):
    vendedor = Usuario.objects.create_user("v", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    client.force_login(vendedor)
    assert client.get("/clientes/buscar.json?q=Rosa").json()["resultados"][0]["nombre"] == "Rosa Burbano"
    assert client.get("/clientes/").status_code == 403
    assert client.get(f"/clientes/{cliente.pk}/").status_code == 403


def test_busqueda_aislada_por_negocio(client, negocio, admin):
    Cliente.objects.create(negocio=Negocio.objects.create(nombre="Otro"), nombre="Rosa de otro", acepta_datos=True)
    client.force_login(admin)
    assert client.get("/clientes/buscar.json?q=Rosa").json()["resultados"] == []


def test_borrar_datos_de_un_cliente(client, negocio, admin, surtido, cliente):
    venta = _vender(negocio, admin, surtido, 1, cliente)
    client.force_login(admin)
    client.post(f"/clientes/{cliente.pk}/eliminar/")
    venta.refresh_from_db()
    assert not Cliente.objects.exists() and venta.cliente == "" and venta.cliente_ref is None


def test_paginas_de_clientes(client, negocio, admin, surtido, cliente):
    _vender(negocio, admin, surtido, 1, cliente)
    oferta = Oferta.objects.create(negocio=negocio, titulo="X", descuento_pct=5, desde=HOY, hasta=HOY)
    client.force_login(admin)
    for url in ["/clientes/", "/clientes/lista/", "/clientes/lista/?segmento=NUEVO", f"/clientes/{cliente.pk}/",
                "/clientes/nuevo/", f"/clientes/{cliente.pk}/editar/", "/clientes/ofertas/", "/clientes/ofertas/nueva/",
                f"/clientes/ofertas/{oferta.pk}/", "/clientes/programa/", "/ventas/vender/"]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "{{" not in r.content.decode(), url


def test_configurar_programa(client, negocio, admin):
    client.force_login(admin)
    datos = {"fidelizacion_activa": "on", "pesos_por_punto": 1000, "valor_punto": 500, "puntos_minimos_canje": 100,
             "nivel_frecuente_compras": 4, "nivel_vip_monto": 500000}
    assert "demasiado" in client.post("/clientes/programa/", datos).content.decode()
    datos["valor_punto"] = 20
    assert client.post("/clientes/programa/", datos).status_code == 302
    negocio.config.refresh_from_db()
    assert negocio.config.valor_punto == 20 and not negocio.config.encuesta_satisfaccion


def test_cotizar_sin_cliente_no_da_puntos(negocio, surtido):
    c = cotizar(negocio, [{"producto": surtido, "cantidad": 1}])
    assert c["total"] == 12000 and c["puntos_ganados"] == 0


def test_recalcular_sin_ventas(cliente):
    assert recalcular(cliente).n_compras == 0


def test_categoria_de_otro_negocio_no_se_ofrece(negocio):
    from apps.clientes.forms import OfertaForm

    otra = Categoria.objects.create(negocio=Negocio.objects.create(nombre="Otro"), nombre="Ajena")
    form = OfertaForm({"titulo": "x", "descuento_pct": 5, "segmento": "TODOS", "desde": HOY, "hasta": HOY,
                       "categoria": otra.pk, "activa": "on"}, negocio=negocio)
    assert not form.is_valid() and "categoria" in form.errors
    assert Producto.objects.count() == 0


def test_vapeadores_solo_adultos_y_ofertas_a_verificados(db):
    """Ley 2354 de 2024: en una tienda de vapeadores se verifica la edad y las ofertas no van a no verificados."""
    from datetime import date

    from apps.clientes.forms import ClienteForm
    from apps.clientes.services import destinatarios
    from apps.core.models import Negocio

    n = Negocio.objects.create(nombre="Nube Vape", giro="VAPE")
    assert n.categorias.filter(nombre="Líquidos y sales de nicotina").exists()
    datos = {"nombre": "Ana", "telefono": "3001234567", "acepta_datos": True, "activo": True}
    form = ClienteForm(datos, negocio=n)
    assert not form.is_valid() and "mayor_edad_verificado" in form.errors
    menor = ClienteForm({**datos, "mayor_edad_verificado": True, "fecha_nacimiento": date.today().replace(
        year=date.today().year - 16)}, negocio=n)
    assert not menor.is_valid() and "2354" in str(menor.errors["fecha_nacimiento"])
    ok = ClienteForm({**datos, "mayor_edad_verificado": True, "acepta_ofertas": True}, negocio=n).save()
    sin = Cliente.objects.create(negocio=n, nombre="Beto", telefono="3007654321", acepta_datos=True, acepta_ofertas=True)
    hoy = date.today()
    oferta = Oferta.objects.create(negocio=n, titulo="Cartuchos", descuento_pct=5, desde=hoy, hasta=hoy)
    assert list(destinatarios(oferta)) == [ok]
    with pytest.raises(ErrorClientes):
        registrar_envio(oferta, sin, None)


def test_oferta_de_cumpleanos_con_el_mes_en_espanol(negocio):
    """Hallazgo de la demo: con «%B» el título salía «Cumpleaños de September» en un servidor en inglés."""
    from datetime import date

    Cliente.objects.create(negocio=negocio, nombre="Ana", telefono="3001112233", acepta_datos=True,
                           fecha_nacimiento=date(1990, 9, 10))
    s = next(x for x in sugerir(negocio, hoy=date(2026, 9, 1)) if x["clave"].startswith("cumple"))
    assert s["titulo"] == "Cumpleaños de septiembre"

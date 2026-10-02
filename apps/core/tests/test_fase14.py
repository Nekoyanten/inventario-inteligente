"""Fase 14: roles con áreas por persona, mesas asignadas a meseros, módulos que guardan datos en segundo plano y un
sistema más fácil de entender (menú corto, inicio por rol, ayudas)."""

from decimal import Decimal

import pytest
from django.template import Context, Template
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto
from apps.clientes.models import Cliente
from apps.clientes.services import cotizar
from apps.core.models import Negocio
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.nocturno import services as s
from apps.nocturno.models import AsignacionMesa, Cuenta, Mesa, noche_de
from apps.usuarios.models import Rol, Usuario
from apps.usuarios.permisos import AREAS

pytestmark = pytest.mark.django_db


@pytest.fixture
def bar(db):
    n = Negocio.objects.create(nombre="Bar La Pola", giro="BAR")
    dueno = Usuario.objects.create_user("dueno", password="x", negocio=n, rol=Rol.ADMIN)
    ana = Usuario.objects.create_user("ana", password="x", first_name="Ana", negocio=n, rol=Rol.MESERO)
    luis = Usuario.objects.create_user("luis", password="x", first_name="Luis", negocio=n, rol=Rol.MESERO)
    caja = Usuario.objects.create_user("caja", password="x", negocio=n, rol=Rol.CAJERO)
    cerveza = Producto.objects.create(negocio=n, sku="CER", nombre="Cerveza", precio_compra=2500, precio_venta=6000,
                                      categoria=Categoria.objects.filter(negocio=n).first())
    registrar_movimiento(producto=cerveza, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=100, usuario=dueno)
    mesas = [Mesa.objects.create(negocio=n, nombre=f"M{i}") for i in range(1, 5)]
    return {"n": n, "dueno": dueno, "ana": ana, "luis": luis, "caja": caja, "cerveza": cerveza, "mesas": mesas}


def _hoy(n):
    return noche_de(timezone.now(), n)


# ---------------------------------------------------------------- roles y áreas
def test_cada_rol_solo_lo_suyo(bar):
    ana, caja, dueno = bar["ana"], bar["caja"], bar["dueno"]
    assert ana.puede("atender_mesas") and not ana.puede("cobrar_cuentas") and not ana.puede("registrar_venta")
    assert caja.puede("cobrar_cuentas") and caja.puede("registrar_venta") and not caja.puede("gestionar_productos")
    assert dueno.puede("asignar_mesas") and dueno.puede("configurar_negocio")
    ana.areas = ["mesas", "inventario"]  # el dueño le suma inventario
    assert ana.puede("registrar_movimiento") and not ana.puede("gestionar_compras")


def test_el_dueno_ajusta_lo_que_ve_cada_persona(client, bar):
    client.force_login(bar["dueno"])
    r = client.post("/usuarios/nuevo/", {"username": "pedro", "rol": "MESERO", "password1": "ClaveSegura123!",
                                        "password2": "ClaveSegura123!", "areas_elegidas": ["mesas", "productos"]})
    assert r.status_code == 302
    pedro = Usuario.objects.get(username="pedro")
    assert pedro.areas == ["mesas", "productos"] and pedro.puede("gestionar_productos")
    # si deja exactamente lo del rol, se guarda como «lo de su rol» (sigue los cambios futuros del rol)
    r = client.post(f"/usuarios/{pedro.pk}/", {"rol": "MESERO", "is_active": "on", "areas_elegidas": ["mesas"]})
    pedro.refresh_from_db()
    assert r.status_code == 302 and pedro.areas is None
    pagina = client.get("/usuarios/").content.decode()
    assert "Tu equipo" in pagina and "Atender mesas" in pagina and "¿Qué hace cada rol?" in pagina


def test_el_formulario_no_ofrece_mesas_en_una_tienda(client, admin):
    client.force_login(admin)
    html = client.get("/usuarios/nuevo/").content.decode()
    assert AREAS["vender"][0] in html and AREAS["mesas"][0] not in html


def test_menu_por_rol(client, bar):
    client.force_login(bar["ana"])
    textos = [i["texto"] for i in client.get("/noche/mis-mesas/").context["menu"]]
    assert "Mesas" in textos and "La noche" not in textos and "Vender" not in textos and "Equipo" not in textos
    client.force_login(bar["caja"])
    textos = [i["texto"] for i in client.get("/").context["menu"]]
    assert "La noche" in textos and "Mesas" not in textos
    client.force_login(bar["dueno"])
    menu = client.get("/").context["menu"]
    assert len(menu) > 5 and sum(i["principal"] for i in menu) == 4  # en el celular: 4 botones y «Más»


def test_inicio_segun_rol(client, bar):
    client.force_login(bar["ana"])
    assert client.get("/").url == "/noche/mis-mesas/"  # el mesero va directo a sus mesas
    client.force_login(bar["caja"])
    html = client.get("/").content.decode()
    assert "Cobrar cuentas, puerta y reservas" in html and "Tus ventas de hoy" in html
    assert "¿Cómo está mi negocio?" not in html


def test_meseros_de_la_demo_pasan_a_rol_mesero(bar):
    from importlib import import_module

    from django.apps import apps as registro

    u = Usuario.objects.create_user("bar.x-mesero1", password="x", negocio=bar["n"], rol=Rol.VENDEDOR)
    import_module("apps.usuarios.migrations.0003_roles_y_areas").meseros(registro, None)
    u.refresh_from_db()
    assert u.rol == Rol.MESERO


# ---------------------------------------------------------------- mesas
def test_repartir_y_repetir_asignacion(bar):
    n, ana, luis = bar["n"], bar["ana"], bar["luis"]
    hoy = _hoy(n)
    assert s.repartir_mesas(n, hoy, [ana, luis], bar["dueno"]) == 4
    assert list(s.mesas_de(n, ana, hoy).values_list("nombre", flat=True)) == ["M1", "M2"]
    manana = hoy + timezone.timedelta(days=1)
    assert s.copiar_asignacion(n, manana, bar["dueno"]) == 4
    assert s.mesas_de(n, luis, manana).count() == 2


def test_pantalla_de_asignar_mesas(client, bar):
    n, m1 = bar["n"], bar["mesas"][0]
    client.force_login(bar["dueno"])
    html = client.get("/noche/mesas/").content.decode()
    assert "Mesas de esta noche" in html and "Repartir automático" in html
    r = client.post("/noche/mesas/", {"accion": "guardar", f"mesa-{m1.pk}": bar["luis"].pk})
    assert r.status_code == 302 and s.mesero_de(m1, _hoy(n)) == bar["luis"]
    client.force_login(bar["ana"])
    assert client.get("/noche/mesas/").status_code == 403  # solo el dueño asigna


def test_el_mesero_solo_atiende_sus_mesas(client, bar):
    n, ana, luis, m1, m2 = bar["n"], bar["ana"], bar["luis"], *bar["mesas"][:2]
    hoy = _hoy(n)
    s.asignar_mesas(n, hoy, {m1.pk: ana, m2.pk: luis}, bar["dueno"])
    client.force_login(ana)
    html = client.get("/noche/mis-mesas/").content.decode()
    assert "Tomar la mesa M1" in html and "ficha otro" in html and "Luis" in html
    # abre su mesa: queda como mesero de la cuenta
    r = client.post(f"/noche/mesas/{m1.pk}/tomar/", {"personas": 3})
    cuenta = Cuenta.objects.get(mesa=m1)
    assert r.url == f"/noche/cuentas/{cuenta.pk}/" and cuenta.mesero == ana and cuenta.personas == 3
    # no puede tomar la que el dueño le asignó a Luis ni ver sus cuentas
    client.post(f"/noche/mesas/{m2.pk}/tomar/")
    assert not Cuenta.objects.filter(mesa=m2).exists()
    ajena = s.abrir_cuenta(n, luis, mesa=m2)
    assert ajena.mesero == luis
    assert client.get(f"/noche/cuentas/{ajena.pk}/").status_code == 403
    assert "ficha otro" in client.get("/noche/mis-mesas/").content.decode()
    # toma el pedido y puede pedirle a la caja que cobre
    client.post(f"/noche/cuentas/{cuenta.pk}/pedir/", {"producto": bar["cerveza"].pk, "cantidad": 2})
    html = client.get(f"/noche/cuentas/{cuenta.pk}/").content.decode()
    assert "dejar la mesa libre" in html and "Que cobre la caja" in html and "datos-carta" in html
    client.post(f"/noche/cuentas/{cuenta.pk}/pedir-cuenta/")
    cuenta.refresh_from_db()
    assert cuenta.pide_cuenta is not None


def test_tablero_cualquier_mesa_libre_y_ocupada_por_otro(client, bar):
    ana, luis, m3 = bar["ana"], bar["luis"], bar["mesas"][2]
    client.force_login(luis)
    client.post(f"/noche/mesas/{m3.pk}/tomar/", {"personas": 2})
    assert Cuenta.objects.get(mesa=m3, estado=Cuenta.Estado.ABIERTA).mesero == luis
    client.force_login(ana)
    r = client.post(f"/noche/mesas/{m3.pk}/tomar/", follow=True)
    assert "ya la está atendiendo Luis" in r.content.decode()


def test_el_mesero_cobra_y_la_caja_recibe_la_plata(client, bar):
    ana, m1 = bar["ana"], bar["mesas"][0]
    client.force_login(ana)
    client.post(f"/noche/mesas/{m1.pk}/tomar/")
    c = Cuenta.objects.get(mesa=m1, estado=Cuenta.Estado.ABIERTA)
    client.post(f"/noche/cuentas/{c.pk}/pedir/", {"producto": bar["cerveza"].pk, "cantidad": 3})  # $18.000
    r = client.post(f"/noche/cuentas/{c.pk}/cobrar/", {"medio_pago": "EFECTIVO", "paga_con": "50000"}, follow=True)
    html = r.content.decode()
    assert "vueltas $32.000" in html and "Entrega $18.000 en la caja" in html and "quedó libre" in html
    c.refresh_from_db()
    assert c.estado == Cuenta.Estado.COBRADA
    e = c.entregas.get()
    assert e.valor == Decimal("18000") and e.vueltas == Decimal("32000") and e.recibida is None
    # la caja lo ve y lo marca como recibido
    client.force_login(bar["caja"])
    assert "Plata que deben entregar los meseros" in client.get("/noche/").content.decode()
    client.post(f"/noche/entregas/{e.pk}/recibir/")
    e.refresh_from_db()
    assert e.recibida is not None and e.recibida_por == bar["caja"]
    # pagos con transferencia no quedan pendientes
    client.force_login(ana)
    client.post(f"/noche/mesas/{m1.pk}/tomar/")
    c2 = Cuenta.objects.get(mesa=m1, estado=Cuenta.Estado.ABIERTA)
    client.post(f"/noche/cuentas/{c2.pk}/pedir/", {"producto": bar["cerveza"].pk, "cantidad": 1})
    client.post(f"/noche/cuentas/{c2.pk}/cobrar/", {"medio_pago": "TRANSFERENCIA"})
    assert not c2.entregas.exists()


def test_liberar_mesa_sin_pedidos(client, bar):
    ana, m1 = bar["ana"], bar["mesas"][0]
    client.force_login(ana)
    client.post(f"/noche/mesas/{m1.pk}/tomar/")
    c = Cuenta.objects.get(mesa=m1, estado=Cuenta.Estado.ABIERTA)
    client.post(f"/noche/cuentas/{c.pk}/liberar/")
    c.refresh_from_db()
    assert c.estado == Cuenta.Estado.ANULADA and "Tomar la mesa" in client.get("/noche/mis-mesas/").content.decode()


def test_la_caja_ve_primero_las_que_piden_la_cuenta_y_cobra(client, bar):
    n, ana, m1, m2 = bar["n"], bar["ana"], *bar["mesas"][:2]
    s.asignar_mesas(n, _hoy(n), {m1.pk: ana, m2.pk: ana}, bar["dueno"])
    c1 = s.abrir_cuenta(n, ana, mesa=m1)
    c2 = s.abrir_cuenta(n, ana, mesa=m2)
    for c in (c1, c2):
        s.agregar_item(c, bar["cerveza"], 1, ana)
    s.pedir_la_cuenta(c2, ana)
    client.force_login(bar["caja"])
    r = client.get("/noche/")
    assert [c.pk for c in r.context["cuentas"]][:1] == [c2.pk] and r.context["por_cobrar"] == 1
    assert "Pide la cuenta" in r.content.decode()
    client.post(f"/noche/cuentas/{c2.pk}/cobrar/", {"medio_pago": "EFECTIVO"})
    c2.refresh_from_db()
    assert c2.estado == Cuenta.Estado.COBRADA and c2.pide_cuenta is None


def test_reasignar_mueve_la_cuenta_abierta(bar):
    n, ana, luis, m1 = bar["n"], bar["ana"], bar["luis"], bar["mesas"][0]
    hoy = _hoy(n)
    s.asignar_mesas(n, hoy, {m1.pk: ana}, bar["dueno"])
    c = s.abrir_cuenta(n, ana, mesa=m1)
    s.asignar_mesas(n, hoy, {m1.pk: luis}, bar["dueno"])  # Ana se fue: Luis sigue con la mesa
    c.refresh_from_db()
    assert c.mesero == luis and AsignacionMesa.objects.get(mesa=m1, noche=hoy).mesero == luis


def test_mesero_sin_mesas_ve_que_hacer(client, bar):
    client.force_login(bar["luis"])
    assert "Tomar la mesa" in client.get("/noche/mis-mesas/").content.decode()


# ---------------------------------------------------------------- módulos en segundo plano
def test_sin_fidelizacion_los_clientes_se_siguen_guardando(client, admin, negocio):
    s_ = negocio.suscripcion
    s_.modulos_apagados = ["clientes"]
    s_.save()
    client.force_login(admin)
    r = client.post("/clientes/nuevo.json", {"nombre": "Marta Díaz", "telefono": "3001234567",
                                             "acepta_datos": "1"})
    assert r.status_code == 200 and Cliente.objects.filter(negocio=negocio, nombre="Marta Díaz").exists()
    assert client.get("/clientes/buscar.json?q=Marta").status_code == 200
    apagado = client.get("/clientes/")
    assert apagado.status_code == 403 and "No pierdes nada" in apagado.content.decode()
    assert "1 cliente registrados" in apagado.content.decode()


def test_sin_fidelizacion_no_hay_canje_ni_ofertas(negocio, producto):
    cliente = Cliente.objects.create(negocio=negocio, nombre="Juan", puntos=500)
    s_ = negocio.suscripcion
    s_.modulos_apagados = ["clientes"]
    s_.save()
    negocio.refresh_from_db()
    producto.refresh_from_db()
    c = cotizar(negocio, [{"producto": producto, "cantidad": 1}], cliente, puntos_canjear=100)
    assert c["puntos_canjeados"] == 0 and c["descuento_puntos"] == Decimal("0")


# ---------------------------------------------------------------- ayudas
def test_ayuda_explica_en_una_linea():
    html = Template('{% load ui %}{% ayuda "Lo que ganas." %}').render(Context())
    assert 'class="ayuda"' in html and "Lo que ganas." in html


def test_el_tablero_del_dueno_explica_sus_datos(client, admin):
    client.force_login(admin)
    html = client.get("/").content.decode()
    assert "Te queda este mes" in html and "Para hacer hoy" in html and 'class="ayuda"' in html


def test_mesas_en_orden_natural(bar):
    n = bar["n"]
    Mesa.objects.create(negocio=n, nombre="M10")
    assert [m.nombre for m in s.orden_natural(Mesa.objects.filter(negocio=n))] == ["M1", "M2", "M3", "M4", "M10"]


def test_pedir_sin_elegir_producto_explica(client, bar):
    n, ana, m1 = bar["n"], bar["ana"], bar["mesas"][0]
    s.asignar_mesas(n, _hoy(n), {m1.pk: ana}, bar["dueno"])
    c = s.abrir_cuenta(n, ana, mesa=m1)
    client.force_login(ana)
    r = client.post(f"/noche/cuentas/{c.pk}/pedir/", {"producto": "", "cantidad": 1}, follow=True)
    assert "Elige el producto de la lista" in r.content.decode()


# ---------------------------------------------------------------- Fase 15: equipo
def test_entrar_con_pin_desde_el_ingreso(client, bar):
    from django.core.cache import cache

    cache.clear()
    ana = bar["ana"]
    ana.fijar_pin("4321")
    ana.save()
    r = client.post("/ingresar/", {"username": "ana", "password": "4321"})
    assert r.status_code == 302 and int(client.session["_auth_user_id"]) == ana.pk
    # el equipo queda recordado: en la pantalla de ingreso salen los nombres
    client.logout()
    client.cookies["equipo_negocio"] = r.cookies["equipo_negocio"].value
    html = client.get("/ingresar/").content.decode()
    assert "¿Quién eres?" in html and "Ana" in html
    # el administrador no entra con PIN
    dueno = bar["dueno"]
    dueno.fijar_pin("1111")
    dueno.save()
    client.post("/ingresar/", {"username": "dueno", "password": "1111"})
    assert "_auth_user_id" not in client.session


def test_cambiar_al_administrador_con_su_contrasena(client, bar):
    from django.core.cache import cache

    cache.clear()
    dueno = bar["dueno"]
    dueno.set_password("ClaveDelDueno1")
    dueno.save()
    client.force_login(bar["caja"])
    assert "dueno" in client.get("/usuarios/cambiar/").content.decode()
    client.post("/usuarios/cambiar/", {"usuario": dueno.pk, "pin": "ClaveDelDueno1"})
    assert int(client.session["_auth_user_id"]) == dueno.pk


def test_eliminar_o_desactivar_del_equipo(client, bar):
    from apps.ventas.services import registrar_venta

    client.force_login(bar["dueno"])
    nuevo = Usuario.objects.create_user("temporal", password="x", negocio=bar["n"], rol=Rol.VENDEDOR)
    client.post(f"/usuarios/{nuevo.pk}/eliminar/")
    assert not Usuario.objects.filter(pk=nuevo.pk).exists()
    # con ventas a su nombre: se desactiva y conserva el historial
    caja = bar["caja"]
    registrar_venta(negocio=bar["n"], vendedor=caja, lineas=[{"producto": bar["cerveza"], "cantidad": 1}])
    client.post(f"/usuarios/{caja.pk}/eliminar/")
    caja.refresh_from_db()
    assert not caja.is_active
    # no se elimina a sí mismo
    client.post(f"/usuarios/{bar['dueno'].pk}/eliminar/")
    assert Usuario.objects.filter(pk=bar["dueno"].pk, is_active=True).exists()
    assert "Usas" in client.get("/usuarios/").content.decode()


def test_el_vendedor_ve_sus_ventas(client, admin, negocio, producto):
    from apps.inventario.models import TipoMovimiento as T
    from apps.ventas.services import registrar_venta

    producto.refresh_from_db()
    registrar_movimiento(producto=producto, tipo=T.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    vende = Usuario.objects.create_user("vende", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    registrar_venta(negocio=negocio, vendedor=vende, lineas=[{"producto": producto, "cantidad": 1}])
    registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 2}])
    client.force_login(vende)
    r = client.get("/ventas/")
    assert r.status_code == 200 and r.context["resumen"]["cantidad"] == 1


def test_porque_corto_en_compras(bar):
    from apps.recomendaciones.models import RecomendacionCompra

    r = RecomendacionCompra(stock_al_calcular=4, demanda_diaria=2, tiempo_entrega=3)
    assert r.motivo_corto == "Alcanza ~2 días · el proveedor tarda 3 días"


# ---------------------------------------------------------------- Fase 16: rápido y simple
def test_pedido_de_un_toque_sin_recargar(client, bar):
    ana, m1, cer = bar["ana"], bar["mesas"][0], bar["cerveza"]
    client.force_login(ana)
    client.post(f"/noche/mesas/{m1.pk}/tomar/")
    c = Cuenta.objects.get(mesa=m1, estado=Cuenta.Estado.ABIERTA)
    h = {"HTTP_X_REQUESTED_WITH": "fetch"}
    for _ in range(3):
        r = client.post(f"/noche/cuentas/{c.pk}/pedir/", {"producto": cer.pk, "cantidad": 1}, **h)
    j = r.json()
    assert j["unidades"] == 3 and j["total"] == 18000 and j["por_producto"][str(cer.pk)] == 3
    j = client.post(f"/noche/cuentas/{c.pk}/menos/", {"producto": cer.pk}, **h).json()
    assert j["unidades"] == 2 and j["a_pagar"] == 12000
    # no puede quitar lo que agregó otra persona
    s.agregar_item(c, cer, 1, bar["dueno"])
    client.post(f"/noche/cuentas/{c.pk}/menos/", {"producto": cer.pk}, **h)
    client.post(f"/noche/cuentas/{c.pk}/menos/", {"producto": cer.pk}, **h)
    r = client.post(f"/noche/cuentas/{c.pk}/menos/", {"producto": cer.pk}, **h)
    assert r.status_code == 400 and c.items.count() == 1


def test_superusuario_es_de_la_plataforma_no_de_una_tienda(client, bar):
    neko = Usuario.objects.create_superuser("neko", "n@example.com", "clave-larga-123", negocio=bar["n"])
    client.force_login(neko)
    r = client.get("/", follow=True)
    html = r.content.decode()
    assert r.redirect_chain[-1][0].endswith("/plataforma/") and "Tus negocios" in html and "Superusuario" in html
    # solo ve una tienda en modo soporte, con la franja que lo dice
    html = client.post(f"/plataforma/negocios/{bar['n'].pk}/entrar/", follow=True).content.decode()
    assert "Modo soporte" in html and "Volver a tus negocios" in html


def test_enlace_del_equipo_deja_listo_el_ingreso(client, bar):
    client.force_login(bar["dueno"])
    html = client.get("/usuarios/").content.decode()
    enlace = html.split('id="enlace-equipo" value="')[1].split('"')[0]
    client.logout()
    r = client.get(enlace.replace("http://testserver", ""))
    assert r.status_code == 302 and "equipo_negocio" in r.cookies
    html = client.get("/ingresar/").content.decode()
    assert "¿Quién eres?" in html and 'id="teclado"' in html and "Ana" in html
    assert client.get("/equipo/no-vale/").status_code == 404


def test_sin_emojis_en_las_pantallas_de_trabajo(client, bar):
    import re

    emoji = re.compile("[\U0001F300-\U0001FAFF]")
    client.force_login(bar["dueno"])
    for url in ("/", "/noche/", "/noche/mesas/", "/usuarios/", "/productos/", "/alertas/", "/ventas/"):
        assert not emoji.search(client.get(url).content.decode()), url


# ---------------------------------------------------------------- Fase 17: el superusuario arma las mesas
def test_superusuario_define_cuantas_mesas_tiene_el_negocio(client, bar):
    n = bar["n"]  # empieza con 4 normales
    neko = Usuario.objects.create_superuser("neko", "n@example.com", "clave-larga-123")
    client.force_login(neko)
    assert "¿Cuántas mesas tiene?" in client.get(f"/plataforma/negocios/{n.pk}/mesas/").content.decode()
    client.post(f"/plataforma/negocios/{n.pk}/mesas/", {"accion": "cantidad", "normales": 6, "vip": 2})
    assert s.conteo_mesas(n) == {"normales": 6, "vip": 2}
    assert set(Mesa.objects.filter(negocio=n, zona="VIP").values_list("nombre", flat=True)) == {"V1", "V2"}
    # un negocio pequeño: se quitan las de número más alto; la ocupada y las que tienen historial no se pierden
    ocupada = Mesa.objects.get(negocio=n, nombre="M6")
    s.abrir_cuenta(n, bar["ana"], mesa=ocupada)
    client.post(f"/plataforma/negocios/{n.pk}/mesas/", {"accion": "cantidad", "normales": 2, "vip": 0})
    nombres = set(Mesa.objects.filter(negocio=n, activa=True).values_list("nombre", flat=True))
    assert nombres == {"M1", "M6"} and not Mesa.objects.filter(negocio=n, zona="VIP").exists()
    # mover de zona, renombrar y quitar una
    m1 = Mesa.objects.get(negocio=n, nombre="M1")
    client.post(f"/plataforma/negocios/{n.pk}/mesas/", {"accion": "guardar", "mesa": m1.pk, "nombre": "Terraza 1",
                                                       "zona": "TERRAZA", "capacidad": 8, "consumo_minimo": 0})
    m1.refresh_from_db()
    assert (m1.nombre, m1.zona, m1.capacidad) == ("Terraza 1", "TERRAZA", 8)
    client.post(f"/plataforma/negocios/{n.pk}/mesas/", {"accion": "quitar", "mesa": m1.pk})
    assert not Mesa.objects.filter(pk=m1.pk).exists()
    # el dueño no entra a esta pantalla
    client.force_login(bar["dueno"])
    assert client.get(f"/plataforma/negocios/{n.pk}/mesas/").status_code in (302, 403)

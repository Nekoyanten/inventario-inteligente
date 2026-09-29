"""Bares y discotecas: cuentas por mesa, happy hour, cover y aforo, reservas y grupos, botellas y fidelización."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, TipoProducto
from apps.clientes.models import Cliente, MovimientoPuntos, Nivel
from apps.core.models import Negocio
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.nocturno import analisis
from apps.nocturno import services as s
from apps.nocturno.fidelizacion import recordatorios
from apps.nocturno.models import BotellaGuardada, Cuenta, Invitado, Mesa, PrecioEspecial, Reserva, noche_de
from apps.usuarios.models import Rol, Usuario
from apps.ventas.models import Venta
from apps.ventas.services import anular_venta

pytestmark = pytest.mark.django_db
TZ = timezone.get_current_timezone()


def _hora(dia_semana_offset=0, h=22, m=0):
    """Un momento de esta semana a la hora dada (hora local)."""
    hoy = timezone.localdate() + timedelta(days=dia_semana_offset)
    return timezone.make_aware(datetime.combine(hoy, time(h, m)), TZ)


@pytest.fixture
def bar(db):
    n = Negocio.objects.create(nombre="Bar La Pola", giro="BAR_DISCOTECA")
    admin = Usuario.objects.create_user("dueno", password="x", negocio=n, rol=Rol.ADMIN)
    cat_bot = Categoria.objects.get(negocio=n, nombre="Botellas")
    cat_cer = Categoria.objects.get(negocio=n, nombre="Cervezas")
    aguardiente = Producto.objects.create(negocio=n, sku="AGU", nombre="Aguardiente 750", categoria=cat_bot,
                                          precio_compra=35000, precio_venta=90000)
    cerveza = Producto.objects.create(negocio=n, sku="CER", nombre="Cerveza", categoria=cat_cer, precio_compra=2500,
                                      precio_venta=6000)
    registrar_movimiento(producto=aguardiente, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    registrar_movimiento(producto=cerveza, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=200, usuario=admin)
    return n, admin, aguardiente, cerveza


def test_plantilla_y_configuracion(bar):
    n, *_ = bar
    assert n.nocturno.cover_valor == 20000 and n.nocturno.aforo == 300
    assert Negocio.objects.create(nombre="Solo bar", giro="BAR").nocturno.cover_valor == 0


def test_noche_de_madrugada():
    sabado_2am = _hora(1, 2)
    assert noche_de(sabado_2am) == timezone.localdate()  # la madrugada es de la noche anterior


def test_cuenta_por_mesa_con_cobro_parcial_y_final(bar):
    n, admin, agu, cer = bar
    mesa = Mesa.objects.create(negocio=n, nombre="M1")
    c = s.abrir_cuenta(n, admin, mesa=mesa, personas=4)
    with pytest.raises(s.ErrorNocturno):
        s.abrir_cuenta(n, admin, mesa=mesa)  # la mesa ya está ocupada
    i1 = s.agregar_item(c, cer, 4, admin)
    s.agregar_item(c, agu, 1, admin)
    r = s.resumen(c)
    assert r["total"] == 114000 and r["por_persona"] == 28500 and r["propina_sugerida"] == 11400
    v1 = s.cobrar(c, admin, items_ids=[i1.pk])  # uno paga sus cervezas
    c.refresh_from_db()
    assert v1.total == 24000 and c.estado == Cuenta.Estado.ABIERTA
    v2 = s.cobrar(c, admin, propina=9000)
    c.refresh_from_db()
    agu.refresh_from_db()
    assert v2.total == 90000 and v2.propina == 9000 and c.estado == Cuenta.Estado.COBRADA and agu.stock_actual == 9


def test_quitar_pedido_exige_motivo_y_queda_en_bitacora(bar):
    from apps.core.models import RegistroAuditoria

    n, admin, _, cer = bar
    c = s.abrir_cuenta(n, admin, nombre="Barra")
    item = s.agregar_item(c, cer, 2, admin)
    with pytest.raises(s.ErrorNocturno):
        s.quitar_item(item, admin, "")
    s.quitar_item(item, admin, "Se equivocó el mesero")
    assert RegistroAuditoria.objects.filter(accion="quitar_pedido").exists()


def test_happy_hour_2x1_segun_la_hora_del_pedido(bar):
    n, admin, _, cer = bar
    hoy = timezone.localdate().weekday()
    PrecioEspecial.objects.create(negocio=n, nombre="Happy hour", tipo="DOS_POR_UNO", dias=[hoy],
                                  hora_inicio=time(19), hora_fin=time(21), categoria=cer.categoria)
    c = s.abrir_cuenta(n, admin, nombre="Barra")
    s.agregar_item(c, cer, 4, admin, momento=_hora(0, 20))   # en happy hour: paga 2
    s.agregar_item(c, cer, 2, admin, momento=_hora(0, 22))   # después: precio normal
    r = s.resumen(c)
    assert r["total"] == 2 * 6000 + 2 * 6000
    assert {linea["promocion"] for linea in r["lineas"]} == {"Happy hour", ""}
    venta = s.cobrar(c, admin)
    assert venta.detalles.filter(promocion="Happy hour").exists()


def test_2x1_junta_rondas_distintas_de_la_misma_cuenta(bar):
    """Hallazgo del piloto simulado: cada ronda es una línea; una cerveza y otra 20 minutos después son un par."""
    n, admin, _, cer = bar
    hoy = timezone.localdate().weekday()
    PrecioEspecial.objects.create(negocio=n, nombre="2x1 cervezas", tipo="DOS_POR_UNO", dias=[hoy],
                                  hora_inicio=time(19), hora_fin=time(21), categoria=cer.categoria)
    c = s.abrir_cuenta(n, admin, nombre="Barra")
    for minuto in (0, 20, 40):
        s.agregar_item(c, cer, 1, admin, momento=_hora(0, 19, minuto))
    s.agregar_item(c, cer, 1, admin, momento=_hora(0, 21, 30))  # fuera de la franja: no hace par
    assert s.resumen(c)["total"] == 3 * 6000  # 4 cervezas, 1 gratis (el par de las 19:00 y 19:20)
    venta = s.cobrar(c, admin)
    assert venta.detalles.filter(promocion="2x1 cervezas").count() == 1


def test_happy_hour_que_pasa_la_medianoche():
    regla = PrecioEspecial(dias=[4], hora_inicio=time(22), hora_fin=time(1))  # viernes 10 p. m. a 1 a. m.
    viernes = timezone.localdate() + timedelta(days=(4 - timezone.localdate().weekday()) % 7)
    en = lambda d, h: timezone.make_aware(datetime.combine(d, time(h, 30)), TZ)  # noqa: E731
    assert regla.vigente_en(en(viernes, 23)) and regla.vigente_en(en(viernes + timedelta(days=1), 0))
    assert not regla.vigente_en(en(viernes + timedelta(days=1), 2)) and not regla.vigente_en(en(viernes, 21))


def test_cover_consumible_y_aforo(bar):
    n, admin, _, cer = bar
    n.nocturno.aforo = 5
    n.nocturno.save()
    ing = s.registrar_ingreso(n, admin, personas=2)
    c = ing.cuenta
    assert ing.total == 40000 and c.credito == 40000
    s.agregar_item(c, cer, 3, admin)  # consume 18.000 de los 40.000
    venta = s.cobrar(c, admin)
    assert venta.pagado_con_credito == 18000
    sobrante = Venta.objects.filter(negocio=n, detalles__producto__sku="COVER").get()
    assert sobrante.total == 22000  # lo no consumido queda como ingreso de la noche
    with pytest.raises(s.ErrorNocturno, match="Aforo"):
        s.registrar_ingreso(n, admin, personas=4)


def test_cover_no_consumible_es_venta(bar):
    n, admin, *_ = bar
    n.nocturno.cover_consumible = False
    n.nocturno.save()
    ing = s.registrar_ingreso(n, admin, personas=3)
    assert ing.venta.total == 60000 and ing.cuenta is None


def test_vip_entra_gratis(bar):
    n, admin, *_ = bar
    vip = Cliente.objects.create(negocio=n, nombre="VIP", acepta_datos=True, nivel=Nivel.VIP)
    ing = s.registrar_ingreso(n, admin, cliente=vip)
    assert ing.total == 0 and ing.motivo_gratis == "Cliente VIP"
    # con 4 amigos: entra gratis con 1 acompañante; los otros 3 pagan (el beneficio es del cliente, no del grupo)
    ing = s.registrar_ingreso(n, admin, cliente=vip, personas=5)
    assert ing.personas_gratis == 2 and ing.total == 3 * 20000 and ing.cuenta.credito == 60000
    costo = analisis.costo_fidelizacion(n)
    assert costo["cover_gratis"] == 3 * 20000 and costo["cover_gratis_pct"] == 50.0
    assert any("cover gratis" in x["titulo"] for x in analisis.sugerencias(n))


def test_reserva_de_grupo_con_anticipo_minimo_descuento_y_puntos(bar):
    n, admin, agu, cer = bar
    org = Cliente.objects.create(negocio=n, nombre="Organizadora", telefono="3001112233", acepta_datos=True)
    r = Reserva.objects.create(negocio=n, nombre="Cumple Ana", cliente=org, fecha=timezone.localdate(), personas=12,
                               consumo_minimo=400000, anticipo=100000, promotor="Juan RRPP")
    assert r.es_grupo
    for i in range(12):
        Invitado.objects.create(reserva=r, nombre=f"Invitado {i}", telefono=f"31000000{i:02d}")
    for inv in list(r.invitados.all())[:11]:
        s.llegada_invitado(inv, admin, registrar_cliente=True, mayor_edad=True)
    c = s.marcar_llegada(r, admin)
    assert c.credito == 100000 and c.descuento_grupo_pct == 10 and c.consumo_minimo == 400000
    s.agregar_item(c, agu, 3, admin)  # 270.000 − 10 % = 243.000 < mínimo
    res = s.resumen(c)
    assert res["faltante_minimo"] == 157000 and res["total"] == 400000 and res["a_pagar"] == 300000
    venta = s.cobrar(c, admin)
    assert venta.pagado_con_credito == 100000
    bono = MovimientoPuntos.objects.get(cliente=org, tipo=MovimientoPuntos.Tipo.BONO)
    assert bono.puntos == 11 * 20  # 20 puntos por cada uno de los 11 que llegaron
    assert Cliente.objects.filter(negocio=n, referido_por=org).count() == 11


def test_invitado_sin_verificar_edad_no_se_registra(bar):
    n, admin, *_ = bar
    r = Reserva.objects.create(negocio=n, nombre="X", fecha=timezone.localdate(), personas=2)
    inv = Invitado.objects.create(reserva=r, nombre="Pepe", telefono="3005556677")
    with pytest.raises(s.ErrorNocturno, match="mayor de edad"):
        s.llegada_invitado(inv, admin, registrar_cliente=True, mayor_edad=False)


def test_bono_por_visitas_y_referidos(bar):
    n, admin, _, cer = bar
    amigo = Cliente.objects.create(negocio=n, nombre="Amigo", acepta_datos=True)
    nuevo = Cliente.objects.create(negocio=n, nombre="Nuevo", acepta_datos=True, referido_por=amigo)
    for noche in range(5):  # 5 noches distintas → bono de visitas
        c = s.abrir_cuenta(n, admin, cliente=nuevo, momento=_hora(-10 + noche * 2, 23))
        s.agregar_item(c, cer, 1, admin)
        s.cobrar(c, admin, fecha=_hora(-10 + noche * 2, 23, 30))
    bonos = MovimientoPuntos.objects.filter(tipo=MovimientoPuntos.Tipo.BONO)
    assert bonos.filter(cliente=amigo, motivo__startswith="Trajo").count() == 1
    assert bonos.filter(cliente=nuevo, motivo__startswith="Visita n.° 5").count() == 1
    # dos compras la misma noche no cuentan como dos visitas
    c = s.abrir_cuenta(n, admin, cliente=nuevo, momento=_hora(-2, 23))
    s.agregar_item(c, cer, 1, admin)
    s.cobrar(c, admin, fecha=_hora(-1, 1))  # 1 a. m.: misma noche que la anterior
    assert bonos.filter(cliente=nuevo).count() == 1


def test_anular_reversa_el_bono(bar):
    n, admin, _, cer = bar
    n.nocturno.visitas_para_bono = 1
    n.nocturno.save()
    cli = Cliente.objects.create(negocio=n, nombre="Cli", acepta_datos=True)
    c = s.abrir_cuenta(n, admin, cliente=cli)
    s.agregar_item(c, cer, 1, admin)
    venta = s.cobrar(c, admin)
    cli.refresh_from_db()
    assert cli.puntos == 6 + 100
    anular_venta(venta, admin, "prueba")
    cli.refresh_from_db()
    assert cli.puntos == 0


def test_tragos_desde_la_botella_y_rendimiento(bar):
    n, admin, agu, _ = bar
    trago = s.crear_trago(agu, ml_botella=750, ml_trago=30, precio=8000)
    assert trago.tipo == TipoProducto.PREPARADO and trago.receta.get().cantidad == Decimal("0.04")
    c = s.abrir_cuenta(n, admin, nombre="Barra")
    s.agregar_item(c, trago, 10, admin)
    s.cobrar(c, admin)
    agu.refresh_from_db()
    assert agu.stock_actual == Decimal("9.6") and agu.unidad.abreviatura == "bot"
    # conteo: en la barra solo hay 9,3 → faltó 0,3 botellas
    from apps.inventario.services import aprobar_conteo, crear_conteo, enviar_conteo

    conteo = crear_conteo(n, admin, productos=[agu])
    d = conteo.detalles.get()
    d.stock_contado, d.motivo = Decimal("9.3"), "Conteo semanal"
    d.save()
    enviar_conteo(conteo, admin)
    aprobar_conteo(conteo, admin)
    fila = next(f for f in analisis.rendimiento_botellas(n) if f["producto"] == agu)
    assert fila["tragos"] == Decimal("0.4") and fila["faltante"] == Decimal("0.3") and fila["merma_pct"] == 42.9
    pc = analisis.pour_cost(n)
    assert pc["por_categoria"][0]["categoria"] == "Tragos y cócteles"
    assert pc["pct"] == 17.5 and pc["real_pct"] == 30.6  # 14.000 de costo + 10.500 que faltaron ÷ 80.000
    assert any("barra se está tomando" in x["titulo"] for x in analisis.sugerencias(n))


def test_botella_guardada_y_recordatorio(bar):
    n, admin, agu, _ = bar
    cli = Cliente.objects.create(negocio=n, nombre="Carlos", telefono="3001234567", acepta_datos=True,
                                 acepta_ofertas=True)
    b = s.guardar_botella(cli, agu, 40, admin, "Casillero 3")
    b.vence = timezone.localdate() + timedelta(days=5)
    b.save()
    assert any(r["tipo"] == "Botella guardada" and "wa.me/573001234567" in r["url"] for r in recordatorios(n))
    s.retirar_botella(b, admin)
    with pytest.raises(s.ErrorNocturno):
        s.retirar_botella(b, admin)
    b2 = s.guardar_botella(cli, agu, 50, admin)
    b2.vence = timezone.localdate() - timedelta(days=1)
    b2.save()
    assert s.vencer_botellas(n) == 1


def test_cliente_menor_de_edad_no_se_registra(client, bar):
    n, admin, *_ = bar
    client.force_login(admin)
    joven = (timezone.localdate() - timedelta(days=17 * 365)).isoformat()
    r = client.post("/clientes/nuevo.json", {"nombre": "Joven", "telefono": "3009998877", "acepta_datos": "on",
                                             "mayor_edad_verificado": "on", "fecha_nacimiento": joven})
    assert r.status_code == 400 and "menor de edad" in r.json()["error"]
    r = client.post("/clientes/nuevo.json", {"nombre": "Sin cédula", "telefono": "3009998866", "acepta_datos": "on"})
    assert r.status_code == 400


def test_reservas_vencidas_y_no_show(bar):
    n, admin, *_ = bar
    ayer = timezone.localdate() - timedelta(days=3)
    Reserva.objects.create(negocio=n, nombre="A", fecha=ayer, personas=2)
    Reserva.objects.create(negocio=n, nombre="B", fecha=ayer, personas=2, estado="LLEGO")
    assert s.reservas_vencidas(n) == 1
    assert analisis.reservas(n)["no_show_pct"] == 50


def test_aislamiento_entre_negocios(client, bar):
    n, admin, *_ = bar
    otro = Negocio.objects.create(nombre="Otro", giro="BAR")
    ajena = Cuenta.objects.create(negocio=otro, nombre="Ajena", noche=timezone.localdate())
    client.force_login(admin)
    assert client.get(f"/noche/cuentas/{ajena.pk}/").status_code == 404
    assert client.post(f"/noche/cuentas/{ajena.pk}/cobrar/").status_code == 404


def test_menu_solo_para_bares(client, admin, negocio):
    client.force_login(admin)
    assert "La noche" not in client.get("/").content.decode()


def test_paginas_de_la_noche(client, bar):
    n, admin, agu, cer = bar
    mesa = Mesa.objects.create(negocio=n, nombre="VIP 1", zona="VIP", consumo_minimo=300000)
    cli = Cliente.objects.create(negocio=n, nombre="Carlos", acepta_datos=True)
    c = s.abrir_cuenta(n, admin, mesa=mesa, cliente=cli)
    s.agregar_item(c, cer, 2, admin)
    r = Reserva.objects.create(negocio=n, nombre="Grupo", fecha=timezone.localdate(), personas=15)
    BotellaGuardada.objects.create(negocio=n, cliente=cli, producto=agu, restante_pct=30,
                                   vence=timezone.localdate() + timedelta(days=9))
    client.force_login(admin)
    html = client.get("/").content.decode()
    assert "La noche" in html
    for url in ["/noche/", f"/noche/cuentas/{c.pk}/", "/noche/reservas/", f"/noche/reservas/{r.pk}/", "/noche/botellas/",
                "/noche/ajustes/", "/noche/precios/", "/noche/precios/?dia=2", "/noche/analisis/",
                f"/productos/{agu.pk}/", f"/clientes/{cli.pk}/", "/ventas/vender/"]:
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert "{{" not in resp.content.decode(), url
    # flujo por la interfaz: pedir, cobrar
    client.post(f"/noche/cuentas/{c.pk}/pedir/", {"producto": agu.pk, "cantidad": "1"})
    resp = client.post(f"/noche/cuentas/{c.pk}/cobrar/", {"medio_pago": "EFECTIVO", "propina": "0"})
    c.refresh_from_db()
    assert resp.status_code == 302 and c.estado == Cuenta.Estado.COBRADA
    venta = Venta.objects.filter(negocio=n).order_by("-pk").first()
    assert venta.total == 300000  # 12.000 + 90.000 → se completa el consumo mínimo de la mesa VIP


def test_vendedor_no_regala_cortesias(client, bar):
    n, admin, _, cer = bar
    mesero = Usuario.objects.create_user("mesero", password="x", negocio=n, rol=Rol.VENDEDOR)
    c = s.abrir_cuenta(n, admin, nombre="Barra")
    client.force_login(mesero)
    client.post(f"/noche/cuentas/{c.pk}/pedir/", {"producto": cer.pk, "cantidad": "1", "cortesia": "1"})
    assert not c.items.get().cortesia
    assert client.get("/noche/ajustes/").status_code == 403


def test_sugerencia_happy_hour_en_noche_floja(bar):
    n, admin, _, cer = bar
    for semana in range(4):
        for dia, cant in ((3, 1), (4, 20), (5, 30)):  # jueves flojo, viernes y sábado fuertes
            momento = _hora(-7 * (semana + 1) + (dia - timezone.localdate().weekday()), 23)
            c = s.abrir_cuenta(n, admin, nombre="x", momento=momento)
            s.agregar_item(c, cer, cant, admin, momento=momento)
            s.cobrar(c, admin, fecha=momento)
    sug = analisis.sugerencias(n)
    assert any(x.get("dia") == 3 for x in sug)


def test_propina_sugerida_maximo_10_por_ciento(bar):
    """Ley 1935 de 2018: la propina sugerida no pasa del 10 % y nunca se redondea hacia arriba."""
    from django.core.exceptions import ValidationError

    n, admin, _, cer = bar
    conf = n.nocturno
    conf.propina_sugerida_pct = 15
    with pytest.raises(ValidationError):
        conf.full_clean()
    conf.refresh_from_db()
    c = s.abrir_cuenta(n, admin, nombre="Barra")
    s.agregar_item(c, cer, 1, admin)
    s.agregar_item(c, Producto.objects.create(negocio=n, sku="X", nombre="Picada", precio_venta=9500, precio_compra=1), 1,
                   admin)
    assert s.resumen(c)["propina_sugerida"] == 1500  # 10 % de 15.500 = 1.550 → 1.500, no 1.600

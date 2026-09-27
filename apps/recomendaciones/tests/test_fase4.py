from datetime import date, timedelta

from django.utils import timezone

from apps.analitica import algoritmos as alg
from apps.analitica.models import RegistroPronostico, Temporada
from apps.analitica.services import analizar_producto, precision_pronosticos, registrar_y_evaluar_pronosticos
from apps.compras.models import OrdenCompra
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.recomendaciones.models import RecomendacionCompra
from apps.recomendaciones.services import generar_recomendaciones
from apps.ventas.services import registrar_venta


def _historial(producto, admin, por_dia=3, dias=20):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=por_dia * dias + 5,
                         usuario=admin, fecha=timezone.now() - timedelta(days=dias + 1), evaluar_alertas=False)
    for i in range(dias, 0, -1):
        registrar_venta(negocio=producto.negocio, vendedor=admin, fecha=timezone.now() - timedelta(days=i),
                        lineas=[{"producto": producto, "cantidad": por_dia}])


def test_holt_winters_captura_estacionalidad():
    base = [10, 10, 12, 11, 10, 10, 11, 12, 11, 13, 20, 40]  # pico en diciembre
    p = alg.pronostico_holt_winters(base * 2 + base[:11])  # siguiente: diciembre
    assert p.valor > 25


def test_temporada_aumenta_la_demanda(producto, admin):
    _historial(producto, admin)
    config = producto.negocio.config
    config.usa_temporadas = True
    config.save()
    hoy = timezone.localdate()
    Temporada.objects.create(negocio=producto.negocio, nombre="Prima", inicio_mes=hoy.month, inicio_dia=hoy.day,
                             fin_mes=hoy.month, fin_dia=hoy.day, factor=2)
    a = analizar_producto(producto)
    assert a.temporada == "Prima" and abs(a.demanda_diaria - 2 * a.demanda_base) < 1e-6


def test_temporada_que_cruza_fin_de_ano():
    t = Temporada(nombre="Navidad", inicio_mes=12, inicio_dia=15, fin_mes=1, fin_dia=6, factor=1.5)
    assert t.contiene(date(2026, 12, 24)) and t.contiene(date(2027, 1, 3)) and not t.contiene(date(2027, 2, 1))


def test_recomendaciones_a_ordenes_con_cantidad_editada(client, admin, producto):
    _historial(producto, admin)
    generar_recomendaciones(producto.negocio)
    rec = RecomendacionCompra.objects.get()
    client.force_login(admin)
    assert "se recomienda pedir" in client.get("/compras/que-comprar/").content.decode()
    client.post("/compras/que-comprar/procesar/", {"seleccion": [rec.pk], f"cantidad-{rec.pk}": "50", "accion": "ordenar"})
    orden = OrdenCompra.objects.get()
    assert orden.detalles.get().cantidad_pedida == 50
    rec.refresh_from_db()
    assert rec.estado == RecomendacionCompra.Estado.ACEPTADA


def test_descartar_recomendacion(client, admin, producto):
    _historial(producto, admin)
    generar_recomendaciones(producto.negocio)
    rec = RecomendacionCompra.objects.get()
    client.force_login(admin)
    client.post("/compras/que-comprar/procesar/", {"seleccion": [rec.pk], "accion": "descartar", "motivo": "Temporada baja"})
    rec.refresh_from_db()
    assert rec.estado == RecomendacionCompra.Estado.DESCARTADA and rec.motivo_descarte == "Temporada baja"


def test_recomendacion_vieja_se_retira_si_ya_no_hace_falta(admin, producto):
    _historial(producto, admin)
    generar_recomendaciones(producto.negocio)
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_COMPRA, cantidad=500, usuario=admin)
    generar_recomendaciones(producto.negocio)
    assert not RecomendacionCompra.objects.filter(estado=RecomendacionCompra.Estado.PENDIENTE).exists()


def test_precision_de_pronosticos(admin, producto):
    _historial(producto, admin)
    hoy = timezone.localdate()
    registrar_y_evaluar_pronosticos(producto.negocio, hoy=hoy - timedelta(days=15))
    reg = RegistroPronostico.objects.get()
    reg.hasta = hoy - timedelta(days=1)
    reg.save()
    registrar_y_evaluar_pronosticos(producto.negocio, hoy=hoy)
    reg.refresh_from_db()
    assert reg.real is not None
    filas = precision_pronosticos(producto.negocio)
    assert filas and filas[0]["producto"] == producto


def test_agrupador_de_variantes_no_genera_alertas_ni_compras(client, admin, negocio):
    from apps.alertas.models import Alerta
    from apps.alertas.motor import evaluar_negocio
    from apps.catalogo.models import Producto

    padre = Producto.objects.create(negocio=negocio, sku="CAM", nombre="Camisa", stock_minimo=5)
    client.force_login(admin)
    client.post(f"/productos/{padre.pk}/variantes/", {"valores__Variante": "S, M"})
    evaluar_negocio(negocio)
    generar_recomendaciones(negocio)
    assert not Alerta.objects.filter(producto=padre).exists()
    assert not RecomendacionCompra.objects.filter(producto=padre).exists()
    assert Alerta.objects.filter(producto__padre=padre, tipo=Alerta.Tipo.AGOTADO).count() == 2

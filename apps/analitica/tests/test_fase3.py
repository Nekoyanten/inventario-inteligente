from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.analitica.models import DemandaDiaria
from apps.analitica.services import analizar_producto, clasificacion_abc, dias_sin_stock
from apps.catalogo.models import Producto
from apps.inventario.models import Movimiento, TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.ventas.services import registrar_venta


def _ventas(producto, admin, por_dia, dias, inicio_hace):
    for i in range(dias):
        registrar_venta(negocio=producto.negocio, vendedor=admin,
                        fecha=timezone.now() - timedelta(days=inicio_hace - i),
                        lineas=[{"producto": producto, "cantidad": por_dia}])


def test_demanda_censurada_no_subestima_productos_agotados(producto, admin):
    # Vendió 5/día durante 10 días, se agotó y lleva 15 días sin stock
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=50, usuario=admin,
                         fecha=timezone.now() - timedelta(days=27), evaluar_alertas=False)
    _ventas(producto, admin, 5, 10, inicio_hace=25)
    hoy = timezone.localdate()
    assert len(dias_sin_stock(producto, hoy - timedelta(days=10), hoy)) == 11
    analisis = analizar_producto(producto)
    assert 4 <= analisis.demanda_diaria <= 5.5   # sin corrección daría ~1.8


def test_clasificacion_abc(negocio, admin, producto):
    barato = Producto.objects.create(negocio=negocio, sku="B", nombre="Barato", precio_venta=100)
    for p in (producto, barato):
        registrar_movimiento(producto=p, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=100, usuario=admin)
    registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 10},
                                                             {"producto": barato, "cantidad": 1}])
    abc = clasificacion_abc(negocio)
    assert abc[producto.pk] == "A" and abc[barato.pk] == "C"


def test_ajuste_inusual_genera_alerta(producto, admin, django_capture_on_commit_callbacks):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=40, usuario=admin)
    with django_capture_on_commit_callbacks(execute=True):  # las alertas se evalúan al confirmar la transacción
        registrar_movimiento(producto=producto, tipo=TipoMovimiento.SALIDA_AJUSTE, cantidad=25, usuario=admin,
                             motivo="Faltante")
    mov = Movimiento.objects.get(tipo=TipoMovimiento.SALIDA_AJUSTE)
    assert mov.marcado_anomalo
    alerta = Alerta.objects.get(tipo=Alerta.Tipo.ANOMALIA)
    assert "Ajuste inusual" in alerta.mensaje and "Faltante" in alerta.accion_sugerida


def test_ajuste_pequeno_no_alerta(producto, admin, django_capture_on_commit_callbacks):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=40, usuario=admin)
    with django_capture_on_commit_callbacks(execute=True):
        registrar_movimiento(producto=producto, tipo=TipoMovimiento.SALIDA_DANADO, cantidad=1, usuario=admin,
                             motivo="Roto")
    assert not Alerta.objects.filter(tipo=Alerta.Tipo.ANOMALIA).exists()


def test_bandeja_de_alertas_resolver_con_nota(client, producto, admin, django_capture_on_commit_callbacks):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=40, usuario=admin)
    with django_capture_on_commit_callbacks(execute=True):
        registrar_movimiento(producto=producto, tipo=TipoMovimiento.SALIDA_AJUSTE, cantidad=25, usuario=admin,
                             motivo="x")
    client.force_login(admin)
    assert "Ajuste inusual" in client.get("/alertas/").content.decode()
    alerta = Alerta.objects.get(tipo=Alerta.Tipo.ANOMALIA)
    client.post(f"/alertas/{alerta.pk}/estado/", {"estado": "RESUELTA", "nota": "Se rompió una caja"})
    alerta.refresh_from_db()
    assert alerta.estado == Alerta.Estado.RESUELTA and alerta.resuelta_por == admin and alerta.nota


def test_reconstruir_demanda(producto, admin):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=40, usuario=admin)
    registrar_venta(negocio=producto.negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 3}])
    DemandaDiaria.objects.all().delete()
    call_command("reconstruir_demanda", verbosity=0)
    assert DemandaDiaria.objects.get(producto=producto).cantidad == 3


def test_resumen_por_correo(producto, admin):
    admin.email = "dueno@example.com"
    admin.save()
    Alerta.objects.create(negocio=producto.negocio, producto=producto, tipo=Alerta.Tipo.AGOTADO,
                          severidad=Alerta.Severidad.ACTUAR, mensaje="Café agotado")
    call_command("enviar_resumen", verbosity=0)
    assert len(mail.outbox) == 1 and "Café agotado" in mail.outbox[0].body


def test_dashboard_vendedor(client, negocio):
    from apps.usuarios.models import Rol, Usuario

    v = Usuario.objects.create_user("v", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    client.force_login(v)
    html = client.get("/").content.decode()
    assert "Tus ventas de hoy" in html and "Utilidad" not in html

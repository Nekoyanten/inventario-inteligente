"""Cierre de cuenta: borra todos los datos de un negocio (derecho de supresión, Ley 1581 de 2012).

Varias relaciones están protegidas (un movimiento no deja borrar su producto, una venta no deja borrar a su
vendedor) para que nadie pierda historia por accidente. Aquí se borra en el orden correcto, a propósito.
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def _borrar_archivo(campo):
    try:
        if campo and campo.name:
            campo.storage.delete(campo.name)
    except Exception:  # el archivo ya no existe o el almacenamiento no responde: no bloquea el cierre
        logger.warning("No se pudo borrar el archivo %s", getattr(campo, "name", ""))


def eliminar_negocio(negocio) -> dict:
    from apps.alertas.models import Alerta
    from apps.analitica.models import DemandaDiaria, RegistroPronostico
    from apps.catalogo.models import Producto
    from apps.compras.models import OrdenCompra
    from apps.inventario.models import ConteoFisico, Movimiento
    from apps.recomendaciones.models import RecomendacionCompra
    from apps.usuarios.models import Usuario
    from apps.ventas.models import Venta

    nombre, pk = negocio.nombre, negocio.pk
    archivos = [p.imagen for p in Producto.objects.filter(negocio=negocio).exclude(imagen="").only("imagen")]
    archivos += [o.factura_imagen for o in OrdenCompra.objects.filter(negocio=negocio).exclude(factura_imagen="")
                 .only("factura_imagen")]
    conteo = {}
    with transaction.atomic():
        pasos = [
            ("alertas", Alerta.objects.filter(negocio=negocio)),
            ("recomendaciones", RecomendacionCompra.objects.filter(negocio=negocio)),
            ("movimientos", Movimiento.objects.filter(negocio=negocio)),
            ("ventas", Venta.objects.filter(negocio=negocio)),
            ("ordenes", OrdenCompra.objects.filter(negocio=negocio)),
            ("conteos", ConteoFisico.objects.filter(negocio=negocio)),
            ("demanda", DemandaDiaria.objects.filter(producto__negocio=negocio)),
            ("pronosticos", RegistroPronostico.objects.filter(producto__negocio=negocio)),
            ("variantes", Producto.objects.filter(negocio=negocio, padre__isnull=False)),
            ("productos", Producto.objects.filter(negocio=negocio)),
            ("usuarios", Usuario.objects.filter(negocio=negocio, is_superuser=False)),
        ]
        for nombre_paso, qs in pasos:
            conteo[nombre_paso] = qs.count()
            qs.delete()
        # El dueño de la plataforma puede estar asociado a un negocio: se desvincula en vez de borrarlo en cascada
        Usuario.objects.filter(negocio=negocio, is_superuser=True).update(negocio=None)
        negocio.delete()  # el resto (proveedores, categorías, configuración, auditoría…) cae en cascada
    for campo in archivos:
        _borrar_archivo(campo)
    logger.info("Negocio #%s «%s» eliminado a solicitud del titular: %s", pk, nombre, conteo)
    return conteo

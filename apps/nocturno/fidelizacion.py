"""Fidelización para bares y discotecas (además de puntos, niveles y ofertas):

- Bono por visitas: cada N noches distintas en que el cliente compra, gana puntos extra (la frecuencia importa más
  que el gasto en la vida nocturna).
- Referidos: quien trae a un cliente nuevo gana puntos cuando el nuevo hace su primera compra.
- Grupos: quien organiza un grupo grande gana puntos por cada persona que llegó (ver services._bono_grupo).
- Cover gratis por nivel, cumpleaños, botella guardada y recordatorios por WhatsApp.
"""

from datetime import timedelta

from django.utils import timezone

from apps.clientes.models import Cliente, MovimientoPuntos

from .models import noche_de


def noches_con_compra(cliente: Cliente) -> set:
    from apps.ventas.models import Venta

    return {noche_de(f, cliente.negocio) for f in Venta.objects.filter(
        cliente_ref=cliente, estado=Venta.Estado.COMPLETADA).values_list("fecha", flat=True)}


def bonos_por_compra(venta, cliente: Cliente) -> list[MovimientoPuntos]:
    from apps.clientes.services import _asentar

    from .services import configuracion

    conf = configuracion(venta.negocio)
    if not venta.negocio.config.fidelizacion_activa:
        return []
    creados = []
    noche = noche_de(venta.fecha, venta.negocio)
    noches = noches_con_compra(cliente)
    marca_visita = f"Visita n.° {len(noches)} (noche {noche:%d/%m/%Y})"
    # solo la primera compra de la noche cuenta como visita
    if conf.visitas_para_bono and conf.puntos_bono_visita and len(noches) % conf.visitas_para_bono == 0 and \
            not MovimientoPuntos.objects.filter(cliente=cliente, tipo=MovimientoPuntos.Tipo.BONO,
                                                motivo=marca_visita).exists():
        creados.append(_asentar(cliente, MovimientoPuntos.Tipo.BONO, conf.puntos_bono_visita, venta=venta,
                                usuario=venta.vendedor, motivo=marca_visita, fecha=venta.fecha))
    referidor = cliente.referido_por
    if referidor and conf.puntos_por_referido and cliente.n_compras == 1:
        marca = f"Trajo a {cliente.nombre} (cliente #{cliente.pk})"
        if not MovimientoPuntos.objects.filter(cliente=referidor, motivo=marca).exists():
            creados.append(_asentar(referidor, MovimientoPuntos.Tipo.BONO, conf.puntos_por_referido, venta=venta,
                                    usuario=venta.vendedor, motivo=marca, fecha=venta.fecha))
    return creados


def proximos_a_bono(negocio, faltan: int = 1) -> list[tuple[Cliente, int]]:
    """Clientes a los que les falta `faltan` visita(s) para el bono: vale la pena invitarlos."""
    from .services import configuracion

    conf = configuracion(negocio)
    if not conf.visitas_para_bono:
        return []
    salida = []
    for c in Cliente.objects.filter(negocio=negocio, activo=True, n_compras__gt=0):
        n = len(noches_con_compra(c))
        if conf.visitas_para_bono - n % conf.visitas_para_bono == faltan:
            salida.append((c, n))
    return salida


def recordatorios(negocio, hoy=None) -> list[dict]:
    """Mensajes de WhatsApp listos que conviene enviar hoy (sin descuento: son recordatorios personales)."""
    from apps.clientes.services import url_whatsapp

    from .models import BotellaGuardada

    hoy = hoy or timezone.localdate()
    salida = []
    for b in BotellaGuardada.objects.filter(negocio=negocio, estado=BotellaGuardada.Estado.GUARDADA,
                                            vence__lte=hoy + timedelta(days=10)).select_related(
            "cliente", "producto"):
        c = b.cliente
        if c.telefono and c.acepta_ofertas:
            texto = (f"Hola {c.primer_nombre}, en {negocio.nombre} te estamos guardando tu {b.producto.nombre} "
                     f"({b.restante_pct} %). Te esperamos antes del {b.vence:%d/%m}. 🍾")
            salida.append({"tipo": "Botella guardada", "cliente": c, "texto": texto,
                           "url": url_whatsapp(c.telefono, texto)})
    for c, n in proximos_a_bono(negocio):
        if c.telefono and c.acepta_ofertas:
            texto = (f"Hola {c.primer_nombre}, llevas {n} noches con nosotros en {negocio.nombre}. En tu próxima visita "
                     f"ganas un bono de puntos. ¡Te esperamos!")
            salida.append({"tipo": "A una visita del bono", "cliente": c, "texto": texto,
                           "url": url_whatsapp(c.telefono, texto)})
    return salida

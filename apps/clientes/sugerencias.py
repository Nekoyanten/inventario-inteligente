"""Ofertas que el sistema sugiere a partir de los datos: a quién ofrecer qué, y por qué.

El sistema sugiere; el empresario decide (crear la oferta es un clic, pero siempre es su decisión)."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.core.formato import numero as _n

from .models import Oferta, Segmento
from .services import descuento_maximo_pct

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]  # sin depender del idioma del servidor ("%B" daba "September")


def _pct(deseado, producto=None) -> Decimal:
    deseado = Decimal(str(deseado))
    if producto is None:
        return deseado
    tope = descuento_maximo_pct(producto) * Decimal("0.6")  # deja al menos 40 % del margen
    return max(Decimal("0"), min(deseado, tope)).quantize(Decimal("1"), rounding=ROUND_DOWN)


def sugerir(negocio, hoy=None) -> list[dict]:
    from apps.alertas.models import Alerta
    from apps.inventario.models import Lote

    from .analisis import resumen

    hoy = hoy or timezone.localdate()
    existentes = set(Oferta.objects.filter(negocio=negocio, hasta__gte=hoy).exclude(clave_sugerencia="")
                     .values_list("clave_sugerencia", flat=True))
    r = resumen(negocio, hoy)
    seg = {s["clave"]: s for s in r["segmentos"]}
    sugerencias = []

    def agregar(clave, **datos):
        if clave not in existentes:
            sugerencias.append({"clave": clave, **datos})

    if seg["EN_RIESGO"]["cantidad"] + seg["PERDIDO"]["cantidad"]:
        n = seg["EN_RIESGO"]["cantidad"] + seg["PERDIDO"]["cantidad"]
        agregar(f"regreso-{hoy:%Y-%m}", titulo="Te extrañamos", descuento_pct=Decimal("10"),
                segmento=Segmento.EN_RIESGO, dias=15,
                razon=(f"{n} clientes dejaron de venir (compraban ${_n(seg['EN_RIESGO']['monto'] + seg['PERDIDO']['monto'])}"
                       " en 6 meses). Recuperar un cliente cuesta menos que conseguir uno nuevo."),
                mensaje="Hola {nombre}, ¡te extrañamos en {negocio}! Vuelve antes del {hasta} y tienes {descuento}% "
                        "de descuento. Además tienes {puntos} puntos para usar.")

    if r["cumpleanos"]:
        agregar(f"cumple-{hoy:%Y-%m}", titulo=f"Cumpleaños de {MESES[hoy.month - 1]}", descuento_pct=Decimal("15"),
                segmento=Segmento.CUMPLEANOS, dias=30,
                razon=f"{len(r['cumpleanos'])} clientes cumplen años este mes. Un detalle en su día fideliza.",
                mensaje="¡Feliz cumpleaños, {nombre}! En {negocio} te regalamos {descuento}% en tu compra de este mes.")

    if seg["NUEVO"]["cantidad"]:
        agregar(f"segunda-{hoy:%Y-%m}", titulo="Tu segunda visita", descuento_pct=Decimal("5"),
                segmento=Segmento.NUEVOS, dias=20,
                razon=(f"{seg['NUEVO']['cantidad']} clientes compraron por primera vez hace poco. La segunda compra "
                       "es la que convierte a un cliente en habitual."),
                mensaje="Hola {nombre}, gracias por comprar en {negocio}. En tu próxima visita tienes {descuento}% "
                        "de descuento (hasta el {hasta}).")

    # Mercancía que conviene mover: próxima a vencer o quieta
    vencen = (Lote.objects.filter(producto__negocio=negocio, cantidad__gt=0, fecha_vencimiento__gte=hoy,
                                  fecha_vencimiento__lte=hoy + timedelta(days=30), producto__activo=True)
              .values("producto").annotate(u=Sum("cantidad")).order_by("-u")[:3])
    from apps.catalogo.models import Producto

    for fila in vencen:
        p = Producto.objects.get(pk=fila["producto"])
        pct = _pct(20, p)
        if pct >= 5:
            agregar(f"vence-{p.pk}-{hoy:%Y-%m}", titulo=f"{p.nombre} con {pct}% de descuento", descuento_pct=pct,
                    producto=p, segmento=Segmento.COMPRADORES, dias=10,
                    razon=(f"{_n(float(fila['u']))} u. de {p.nombre} vencen en menos de 30 días. Mejor venderlas con "
                           "descuento a quienes ya las compran que botarlas."))
    quietos = (Alerta.objects.filter(negocio=negocio, estado__in=["ABIERTA", "VISTA"],
                                     tipo__in=[Alerta.Tipo.EXCESO, Alerta.Tipo.BAJA_ROTACION])
               .select_related("producto").order_by("-creado")[:50])
    candidatos = sorted(quietos, key=lambda a: -float(a.datos.get("valor_inmovilizado") or
                                                      a.producto.stock_actual * a.producto.precio_compra))[:2]
    for a in candidatos:
        p = a.producto
        pct = _pct(15, p)
        if pct >= 5:
            agregar(f"quieto-{p.pk}-{hoy:%Y-%m}", titulo=f"Oferta en {p.nombre}", descuento_pct=pct, producto=p,
                    segmento=Segmento.COMPRADORES if p.categoria_id else Segmento.TODOS, dias=15,
                    razon=(f"{p.nombre}: {a.mensaje} Ofrecerlo a quienes compran esa categoría libera dinero quieto."),
                    usar_categoria=True)

    if seg["CAMPEON"]["cantidad"]:
        agregar(f"vip-{hoy:%Y-%m}", titulo="Gracias por preferirnos", descuento_pct=Decimal("10"),
                segmento=Segmento.FRECUENTES, dias=15,
                razon=(f"{seg['CAMPEON']['cantidad']} clientes campeones hacen gran parte de tus ventas. Reconocerlos "
                       "evita que se vayan con la competencia."),
                mensaje="{nombre}, eres de nuestros mejores clientes en {negocio}. Por eso tienes {descuento}% de "
                        "descuento hasta el {hasta}. ¡Gracias!")
    return sugerencias


def crear_desde_sugerencia(negocio, clave, usuario, hoy=None) -> Oferta | None:
    hoy = hoy or timezone.localdate()
    for s in sugerir(negocio, hoy):
        if s["clave"] != clave:
            continue
        producto = s.get("producto")
        categoria = producto.categoria if (producto and s.get("usar_categoria") and producto.categoria_id) else None
        return Oferta.objects.create(
            negocio=negocio, titulo=s["titulo"][:120], descuento_pct=s["descuento_pct"],
            producto=None if categoria else producto, categoria=categoria, segmento=s["segmento"],
            desde=hoy, hasta=hoy + timedelta(days=s["dias"]), mensaje=s.get("mensaje", ""), creada_por=usuario,
            origen="SUGERIDA", clave_sugerencia=clave, razon=s["razon"])
    return None

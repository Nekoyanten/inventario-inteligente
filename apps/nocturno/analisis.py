"""Análisis de la noche: cuándo se vende, cuánto cuesta lo que se sirve, qué se pierde en la barra, cómo rinden
las reservas, los grupos, los promotores y la fidelización."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.catalogo.models import Producto

from .models import BotellaGuardada, Cuenta, Ingreso, Reserva, noche_de

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]
CATEGORIAS_BEBIDA = ("Botellas", "Tragos y cócteles", "Cervezas")


def _ventas(negocio, desde):
    from apps.ventas.models import Venta

    return Venta.objects.filter(negocio=negocio, estado=Venta.Estado.COMPLETADA, fecha__date__gte=desde)


def por_dia_semana(negocio, dias=56, hoy=None) -> list[dict]:
    hoy = hoy or timezone.localdate()
    por_noche = defaultdict(Decimal)
    for fecha, total in _ventas(negocio, hoy - timedelta(days=dias)).values_list("fecha", "total"):
        por_noche[noche_de(fecha, negocio)] += total
    acumulado = defaultdict(list)
    for noche, total in por_noche.items():
        acumulado[noche.weekday()].append(total)
    filas = [{"dia": DIAS[d], "indice": d, "noches": len(v), "promedio": sum(v) / len(v)} for d, v in acumulado.items()]
    return sorted(filas, key=lambda f: f["indice"])


def por_hora(negocio, dias=28, hoy=None) -> list[dict]:
    hoy = hoy or timezone.localdate()
    horas = defaultdict(Decimal)
    for fecha, total in _ventas(negocio, hoy - timedelta(days=dias)).values_list("fecha", "total"):
        horas[timezone.localtime(fecha).hour] += total
    orden = sorted(horas, key=lambda h: (h - 12) % 24)  # de la tarde a la madrugada
    return [{"hora": f"{h:02d}:00", "valor": float(horas[h])} for h in orden]


# Referencias internacionales de costo de lo servido (Restaurants Canada, vía Sculpture Hospitality): destilados por
# trago 18–20 %, cerveza 24–28 %. La botella entera se vende con menos margen por diseño: 40 % es orientativo.
REFERENCIA_POUR = {"Tragos y cócteles": 24, "Cervezas": 28, "Botellas": 40}
# Solo se alerta en tragos y cócteles: ahí el dueño controla la medida, la receta y el precio. La cerveza nacional y
# la botella entera tienen márgenes más estrechos en Colombia (el piloto simulado daba ~40 % en los 9 negocios):
# alertar siempre sería ruido, así que se muestran como referencia y nada más.
ALERTA_POUR = ("Tragos y cócteles",)


def pour_cost(negocio, dias=30, hoy=None) -> dict:
    """Costo de lo servido ÷ ventas de bebidas, por categoría y en total.

    «teórico» usa el costo de la receta (lo que DEBERÍA haber salido); «real» le suma lo que faltó en los conteos
    de botellas (sobreservido, cortesías sin registrar, pérdidas). La distancia entre los dos es la merma de barra."""
    from apps.ventas.models import DetalleVenta, Venta

    hoy = hoy or timezone.localdate()
    filas = (DetalleVenta.objects.filter(
        venta__negocio=negocio, venta__estado=Venta.Estado.COMPLETADA, venta__fecha__date__gte=hoy - timedelta(days=dias),
        producto__categoria__nombre__in=CATEGORIAS_BEBIDA)
        .values("producto__categoria__nombre")
        .annotate(ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")),
                  costo=Sum(F("cantidad") * F("costo_unitario"))))
    por_categoria, ingreso, costo = [], Decimal(0), Decimal(0)
    for f in sorted(filas, key=lambda f: CATEGORIAS_BEBIDA.index(f["producto__categoria__nombre"])):
        cat, i, c = f["producto__categoria__nombre"], f["ingreso"] or Decimal(0), f["costo"] or Decimal(0)
        ingreso, costo = ingreso + i, costo + c
        pct = round(float(100 * c / i), 1) if i else None
        ref = REFERENCIA_POUR.get(cat)
        por_categoria.append({"categoria": cat, "ingreso": i, "pct": pct, "referencia": ref,
                              "alto": bool(cat in ALERTA_POUR and pct and ref and pct > ref + 3)})
    faltante = sum((f["valor_faltante"] for f in rendimiento_botellas(negocio, dias=dias, hoy=hoy)), Decimal(0))
    return {"ingreso": ingreso, "costo": costo, "faltante": faltante,
            "pct": round(float(100 * costo / ingreso), 1) if ingreso else None,
            "real_pct": round(float(100 * (costo + faltante) / ingreso), 1) if ingreso else None,
            "por_categoria": por_categoria}


def rendimiento_botellas(negocio, dias=30, hoy=None) -> list[dict]:
    """Por botella: lo vendido entero, lo servido en tragos y lo que faltó en los conteos (merma de barra)."""
    from apps.inventario.models import Movimiento
    from apps.inventario.models import TipoMovimiento as T

    hoy = hoy or timezone.localdate()
    botellas = Producto.objects.filter(negocio=negocio, activo=True).filter(
        Q(unidad__abreviatura="bot") | Q(categoria__nombre="Botellas")).exclude(tipo="PREPARADO")
    movs = (Movimiento.objects.filter(producto__in=botellas, fecha__date__gte=hoy - timedelta(days=dias))
            .values("producto_id", "tipo").annotate(c=Sum("cantidad")))
    datos = defaultdict(lambda: defaultdict(Decimal))
    for m in movs:
        datos[m["producto_id"]][m["tipo"]] += m["c"]
    conteo = (Movimiento.objects.filter(producto__in=botellas, fecha__date__gte=hoy - timedelta(days=dias),
                                        referencia_tipo="conteo").values("producto_id", "tipo").annotate(c=Sum("cantidad")))
    faltas = defaultdict(Decimal)
    for m in conteo:
        faltas[m["producto_id"]] += m["c"] if m["tipo"] == T.SALIDA_AJUSTE else -m["c"]
    filas = []
    for b in botellas:
        d = datos.get(b.pk, {})
        enteras, tragos = d.get(T.SALIDA_VENTA, Decimal(0)), d.get(T.SALIDA_INSUMO, Decimal(0))
        falta = max(Decimal(0), faltas.get(b.pk, Decimal(0)))
        usado = enteras + tragos + falta
        if not usado:
            continue
        filas.append({"producto": b, "enteras": enteras, "tragos": tragos, "faltante": falta,
                      "merma_pct": round(float(100 * falta / usado), 1) if usado else 0.0,
                      "valor_faltante": falta * b.precio_compra})
    return sorted(filas, key=lambda f: -f["valor_faltante"])


def reservas(negocio, dias=60, hoy=None) -> dict:
    hoy = hoy or timezone.localdate()
    qs = Reserva.objects.filter(negocio=negocio, fecha__gte=hoy - timedelta(days=dias), fecha__lt=hoy)
    total = qs.exclude(estado=Reserva.Estado.CANCELADA).count()
    no_show = qs.filter(estado=Reserva.Estado.NO_LLEGO).count()
    conf = getattr(negocio, "nocturno", None)
    minimo = conf.grupo_minimo_personas if conf else 10
    grupos = qs.filter(personas__gte=minimo, estado=Reserva.Estado.LLEGO)
    consumo = _consumo_cuentas(Cuenta.objects.filter(reserva__in=grupos))
    personas = grupos.aggregate(p=Sum("personas"))["p"] or 0
    sin_reserva = _consumo_cuentas(Cuenta.objects.filter(negocio=negocio, reserva__isnull=True,
                                                         estado=Cuenta.Estado.COBRADA, noche__gte=hoy - timedelta(days=dias)))
    personas_sin = Cuenta.objects.filter(negocio=negocio, reserva__isnull=True, estado=Cuenta.Estado.COBRADA,
                                         noche__gte=hoy - timedelta(days=dias)).aggregate(p=Sum("personas"))["p"] or 0
    return {"total": total, "no_show_pct": round(100 * no_show / total) if total else None,
            "grupos": grupos.count(), "personas_grupos": personas,
            "consumo_por_persona_grupo": consumo / personas if personas else None,
            "consumo_por_persona_otros": sin_reserva / personas_sin if personas_sin else None}


def _consumo_cuentas(cuentas) -> Decimal:
    from apps.nocturno.models import ItemCuenta
    from apps.ventas.models import Venta

    ventas = ItemCuenta.objects.filter(cuenta__in=cuentas, venta__isnull=False).values_list("venta", flat=True).distinct()
    return Venta.objects.filter(pk__in=list(ventas), estado=Venta.Estado.COMPLETADA).aggregate(t=Sum("total"))["t"] or 0


def promotores(negocio, dias=60, hoy=None) -> list[dict]:
    hoy = hoy or timezone.localdate()
    filas = []
    for p in (Reserva.objects.filter(negocio=negocio, fecha__gte=hoy - timedelta(days=dias)).exclude(promotor="")
              .values("promotor").annotate(reservas=Count("id"), esperados=Sum("personas"))):
        rs = Reserva.objects.filter(negocio=negocio, promotor=p["promotor"], fecha__gte=hoy - timedelta(days=dias))
        llegaron = sum(r.llegaron or (r.personas if r.estado == Reserva.Estado.LLEGO else 0) for r in rs)
        filas.append({**p, "llegaron": llegaron, "consumo": _consumo_cuentas(Cuenta.objects.filter(reserva__in=rs))})
    return sorted(filas, key=lambda f: -f["consumo"])


def puerta(negocio, dias=30, hoy=None) -> dict:
    hoy = hoy or timezone.localdate()
    qs = Ingreso.objects.filter(negocio=negocio, noche__gte=hoy - timedelta(days=dias))
    agg = qs.aggregate(personas=Sum("personas"), noches=Count("noche", distinct=True))
    cover = sum(i.total for i in qs)
    gratis = dict(qs.filter(personas_gratis__gt=0).values_list("motivo_gratis")
                  .annotate(p=Sum("personas_gratis")).values_list("motivo_gratis", "p"))
    no_cobrado = sum((i.valor_por_persona * i.personas_gratis for i in qs.filter(personas_gratis__gt=0)), Decimal(0))
    return {"personas": agg["personas"] or 0, "noches": agg["noches"] or 0, "cover": cover, "gratis": gratis,
            "no_cobrado": no_cobrado,
            "promedio_noche": (agg["personas"] or 0) / agg["noches"] if agg["noches"] else None}


def fidelizacion(negocio, dias=60, hoy=None) -> dict:
    from apps.clientes.models import Cliente, MovimientoPuntos

    hoy = hoy or timezone.localdate()
    desde = hoy - timedelta(days=dias)
    ventas = _ventas(negocio, desde)
    n = ventas.count()
    identificadas = ventas.filter(cliente_ref__isnull=False).count()
    noches = defaultdict(set)
    for cid, f in ventas.filter(cliente_ref__isnull=False).values_list("cliente_ref", "fecha"):
        noches[cid].add(noche_de(f, negocio))
    bonos = MovimientoPuntos.objects.filter(cliente__negocio=negocio, tipo=MovimientoPuntos.Tipo.BONO,
                                            fecha__date__gte=desde)
    return {
        "ventas_con_cliente_pct": round(100 * identificadas / n) if n else None,
        "clientes": len(noches), "vuelven": sum(1 for s in noches.values() if len(s) >= 2),
        "bonos_visita": bonos.filter(motivo__startswith="Visita").count(),
        "bonos_referido": bonos.filter(motivo__startswith="Trajo").count(),
        "bonos_grupo": bonos.filter(motivo__startswith="Grupo").count(),
        "referidos": Cliente.objects.filter(negocio=negocio, referido_por__isnull=False).count(),
        "botellas": dict(BotellaGuardada.objects.filter(negocio=negocio).values_list("estado")
                         .annotate(n=Count("id")).values_list("estado", "n")),
        "propinas": ventas.aggregate(t=Sum("propina"))["t"] or 0,
        "ventas": ventas.aggregate(t=Sum("total"))["t"] or 0,
        "costo": costo_fidelizacion(negocio, dias=dias, hoy=hoy),
    }


def costo_fidelizacion(negocio, dias=60, hoy=None) -> dict:
    """Lo que la fidelización deja de cobrar: puntos canjeados, descuentos de ofertas y cover gratis por nivel.
    Sirve para compararlo con lo que trae (más visitas) y ajustar los beneficios."""
    from apps.ventas.models import DetalleVenta

    hoy = hoy or timezone.localdate()
    desde = hoy - timedelta(days=dias)
    ventas = _ventas(negocio, desde)
    puntos = ventas.aggregate(t=Sum("descuento_puntos"))["t"] or Decimal(0)
    ofertas = DetalleVenta.objects.filter(venta__in=ventas, oferta__isnull=False).aggregate(t=Sum("descuento"))["t"] \
        or Decimal(0)
    ingresos = Ingreso.objects.filter(negocio=negocio, noche__gte=desde, noche__lt=hoy + timedelta(days=1))
    por_nivel = ingresos.filter(personas_gratis__gt=0, motivo_gratis__startswith="Cliente")
    cover_gratis = sum((i.valor_por_persona * i.personas_gratis for i in por_nivel), Decimal(0))
    cover_cobrado = sum((i.total for i in ingresos), Decimal(0))
    return {"puntos": puntos, "ofertas": ofertas, "cover_gratis": cover_gratis, "total": puntos + ofertas + cover_gratis,
            "cover_gratis_pct": round(float(100 * cover_gratis / (cover_gratis + cover_cobrado)), 1)
            if cover_gratis + cover_cobrado else None}


def sugerencias(negocio, hoy=None) -> list[dict]:
    """Ideas concretas a partir de los datos (el dueño decide)."""
    from .models import PrecioEspecial

    hoy = hoy or timezone.localdate()
    salida = []
    dias = [d for d in por_dia_semana(negocio, hoy=hoy) if d["noches"] >= 3]
    if len(dias) >= 3:
        floja = min(dias, key=lambda d: d["promedio"])
        fuerte = max(dias, key=lambda d: d["promedio"])
        ya = any(floja["indice"] in (p.dias or []) for p in PrecioEspecial.objects.filter(negocio=negocio, activa=True))
        if not ya and floja["promedio"] < fuerte["promedio"] / 2:
            debil, bueno = DIAS_PLURAL[floja["indice"]], DIAS_PLURAL[fuerte["indice"]]
            salida.append({"clave": f"happy-{floja['indice']}", "titulo": f"Happy hour los {debil}",
                           "razon": (f"Los {debil} vendes en promedio ${floja['promedio']:,.0f} por noche; "
                                     f"los {bueno}, ${fuerte['promedio']:,.0f}. Un 2×1 temprano "
                                     "(7 a 9 p. m.) llena la noche floja y trae gente que luego consume a precio normal."
                                     ).replace(",", "."),
                           "dia": floja["indice"]})
    pc = pour_cost(negocio, hoy=hoy)
    for f in (f for f in pc["por_categoria"] if f["alto"]):
        salida.append({"clave": "", "titulo": f"{f['categoria']}: el costo de lo servido está alto",
                       "razon": f"Cuesta el {f['pct']} % de lo que cobras (referencia: {f['referencia']} %). Revisa "
                                "precios, la medida al servir y el costo de compra."})
    if pc["pct"] and pc["real_pct"] and pc["real_pct"] - pc["pct"] >= 2:
        salida.append({"clave": "", "titulo": "La barra se está tomando parte de la ganancia",
                       "razon": f"Según las recetas, lo servido debería costar el {pc['pct']} % de las ventas; con lo que "
                                f"faltó en los conteos, cuesta el {pc['real_pct']} %. Usa medidor (jigger) y registra "
                                "las cortesías."})
    malas = [f for f in rendimiento_botellas(negocio, hoy=hoy) if f["merma_pct"] >= 8]
    if malas:
        nombres = ", ".join(f["producto"].nombre for f in malas[:3])
        salida.append({"clave": "", "titulo": "Botellas que rinden menos de lo que deberían",
                       "razon": f"{nombres}: falta más del 8 % según los conteos. Usa medidor (jigger) y cuenta las "
                                "botellas abiertas cada semana."})
    costo = costo_fidelizacion(negocio, hoy=hoy)
    if costo["cover_gratis_pct"] and costo["cover_gratis_pct"] >= 10:
        salida.append({"clave": "", "titulo": "El cover gratis por nivel pesa en la puerta",
                       "razon": f"El {costo['cover_gratis_pct']} % del cover de la puerta se regaló a clientes por su nivel "
                                f"(${costo['cover_gratis']:,.0f}). Prueba dar el beneficio en consumo (cover consumible o "
                                "un trago de bienvenida), menos acompañantes gratis o solo en las noches flojas."
                                .replace(",", ".")})
    r = reservas(negocio, hoy=hoy)
    if r["no_show_pct"] and r["no_show_pct"] >= 25:
        salida.append({"clave": "", "titulo": "Muchas reservas no llegan",
                       "razon": f"El {r['no_show_pct']} % de las reservas no llegó. Pide un anticipo (se descuenta de "
                                "la cuenta) y confirma por WhatsApp la tarde anterior."})
    return salida

"""Demostración: 5 negocios ficticios (bar, discoteca, bar-discoteca, ropa y vapeadores) con proveedores y productos de
marcas reales, más de 100 clientes cada uno, historial de ventas y cada uno en un plan distinto.

Los negocios, dueños y clientes son INVENTADOS. Las marcas y productos existen; los precios son aproximados
(Colombia, 2026) y no son una cotización de esas marcas. La conducta de los clientes es un supuesto del simulador.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from django.utils import timezone

from .perfiles_nocturnos import PERFILES_NOCTURNOS

CLAVE_DEMO = "Demo2026!"
# La pone aplicar_plan al final (y así quedaron las demos ya cargadas): si falta, la carga se cortó a medias.
MARCA_COMPLETO = "Negocio de demostración (datos simulados)."

# ---------------------------------------------------------------------------------------------------------- nocturnos
_BASE = {p["clave"]: p for p in PERFILES_NOCTURNOS}

CERVEZAS_BAVARIA = [  # nombre, costo, precio
    ("Águila 330 ml", 2600, 6000), ("Águila Light 330 ml", 2600, 6000), ("Poker 330 ml", 2500, 5500),
    ("Club Colombia Dorada 330 ml", 3100, 7000), ("Club Colombia Roja 330 ml", 3100, 7000),
    ("Costeña 330 ml", 2400, 5500), ("Pilsen 330 ml", 2500, 5500), ("Corona Extra 355 ml", 4600, 11000),
    ("Stella Artois 330 ml", 4200, 10000), ("Budweiser 355 ml", 3000, 7000), ("BBC Cajicá Miel 330 ml", 5200, 12000),
    ("Redd's 269 ml", 2800, 6500),
]
BOTELLAS_LOCALES = [  # nombre, ml, costo, precio botella, precio trago
    ("Aguardiente Antioqueño", 750, 36000, 95000, 8000), ("Aguardiente Antioqueño", 375, 19000, 52000, 8000),
    ("Ron Medellín Añejo 3 años", 750, 38000, 100000, 9000), ("Tequila José Cuervo Especial", 750, 72000, 175000, 15000),
    ("Whisky Old Parr 12 años", 750, 125000, 300000, 26000), ("Whisky Buchanan's Deluxe 12 años", 750, 135000, 320000,
                                                                   28000),
]
BOTELLAS_DIAGEO = [
    ("Whisky Buchanan's Deluxe 12 años", 750, 135000, 320000, 28000),
    ("Whisky Buchanan's Master", 750, 165000, 390000, 34000),
    ("Whisky Old Parr 12 años", 750, 125000, 300000, 26000),
    ("Whisky Johnnie Walker Red Label", 700, 72000, 175000, 16000),
    ("Whisky Johnnie Walker Black Label 12 años", 750, 140000, 330000, 28000),
    ("Whisky Black & White", 700, 48000, 120000, 11000),
    ("Vodka Smirnoff No. 21", 700, 42000, 110000, 10000),
    ("Ginebra Tanqueray London Dry", 700, 85000, 200000, 17000),
    ("Crema Baileys Original", 750, 70000, 170000, 15000),
    ("Tequila Don Julio Blanco", 750, 190000, 450000, 38000),
    ("Aguardiente Antioqueño", 750, 36000, 95000, 8000),  # lo trae el distribuidor local
    ("Aguardiente Antioqueño", 375, 19000, 52000, 8000),
]
BOTELLAS_ILC = [
    ("Aguardiente Cristal", 750, 33000, 85000, 7000), ("Aguardiente Cristal", 375, 18000, 48000, 7000),
    ("Aguardiente Cristal sin azúcar", 750, 34000, 88000, 7500), ("Aguardiente Cristal Tapa Azul", 750, 34000, 88000,
                                                                   7500),
    ("Aguardiente Amarillo de Manzanares", 750, 36000, 92000, 8000),
    ("Ron Viejo de Caldas 5 años", 750, 42000, 110000, 10000), ("Ron Viejo de Caldas 8 años", 700, 70000, 170000, 14000),
    ("Ron Viejo de Caldas 15 años", 700, 120000, 280000, 24000),
    ("Whisky Old Parr 12 años", 750, 125000, 300000, 26000),  # lo trae el distribuidor local
    ("Whisky Buchanan's Deluxe 12 años", 750, 135000, 320000, 28000),
]
COCTELES_DIAGEO = [
    ("Gin tonic Tanqueray", "Tanqueray", 60, [("Limón", 0.02), ("Soda para cócteles", 1), ("Hielo", 0.2)], 28000),
    ("Destornillador", "Smirnoff", 60, [("Zumo de naranja", 0.15), ("Hielo", 0.2)], 22000),
    ("Whisky sour", "Black & White", 60, [("Limón", 0.05), ("Azúcar", 0.02), ("Hielo", 0.2)], 24000),
    ("Margarita Don Julio", "Don Julio", 60, [("Limón", 0.05), ("Azúcar", 0.01), ("Hielo", 0.2)], 34000),
    ("Baileys en las rocas", "Baileys", 60, [("Hielo", 0.2)], 20000),
]
COCTELES_ILC = [
    ("Mojito de Ron Viejo", "Ron Viejo de Caldas 5", 60,
     [("Limón", 0.04), ("Hierbabuena", 0.01), ("Azúcar", 0.02), ("Soda para cócteles", 1), ("Hielo", 0.2)], 22000),
    ("Cuba libre", "Ron Viejo de Caldas 5", 60, [("Limón", 0.02), ("Hielo", 0.2)], 20000),
    ("Aguardiente sour", "Cristal", 60, [("Limón", 0.05), ("Azúcar", 0.02), ("Hielo", 0.2)], 18000),
    ("Canelazo de Cristal", "Cristal", 45, [("Azúcar", 0.03), ("Zumo de naranja", 0.05)], 12000),
]
COCTELES_BAR = [
    ("Cuba libre", "Ron Medellín", 60, [("Limón", 0.02), ("Hielo", 0.2)], 18000),
    ("Margarita", "Cuervo", 60, [("Limón", 0.05), ("Azúcar", 0.01), ("Hielo", 0.2)], 22000),
    ("Aguardiente sour", "Aguardiente", 60, [("Limón", 0.05), ("Azúcar", 0.02), ("Hielo", 0.2)], 16000),
]
LOCAL = ("Distribuidora de Licores del Sur (local)", 2)

NOCTURNOS_DEMO = [
    {**_BASE["bar-la-pola"], "clave": "demo-bar", "usuario": "bar.lacuadra", "negocio": "Bar La Cuadra",
     "dueno": "Camilo Andrés Erazo", "lugar": "Calle 18, Centro, Pasto", "plan": "EMPRENDEDOR", "meseros": 2,
     "pool": 1000, "adopcion": 0.6,
     "proveedores": {"Cervezas": ("Bavaria & Cía. S.C.A.", 2), "_": LOCAL},
     "catalogo": {"cervezas": CERVEZAS_BAVARIA, "botellas": BOTELLAS_LOCALES, "cocteles": COCTELES_BAR},
     "marca_principal": "Bavaria (AB InBev)", "satisfaccion": 4.4,
     "tecnicas": "Puntos, bono cada 5 visitas, botella guardada y 2×1 de cerveza de martes a jueves (17:00–19:30)."},
    {**_BASE["disco-galeras"], "clave": "demo-disco", "usuario": "disco.kalima", "negocio": "Kalima Club",
     "dueno": "Valentina Ortega Guerrero", "lugar": "Zona rosa, Pasto", "plan": "NEGOCIO", "meseros": 3,
     "adopcion": 0.5,
     "proveedores": {"marca:Aguardiente": LOCAL, "Botellas": ("Diageo Colombia S.A.", 3), "_": LOCAL},
     "catalogo": {"botellas": BOTELLAS_DIAGEO, "cocteles": COCTELES_DIAGEO},
     "marca_principal": "Diageo (Buchanan's, Old Parr, Johnnie Walker, Smirnoff, Tanqueray, Baileys, Don Julio)",
     "satisfaccion": 4.1,
     "tecnicas": "Cover consumible, VIP entra gratis con un acompañante, reservas con promotores, botella guardada y "
                 "recordatorios por WhatsApp."},
    {**_BASE["bardisco-crossover"], "clave": "demo-bardisco", "usuario": "bardisco.mirador",
     "negocio": "Mirador 360 Bar & Disco", "dueno": "Jhon Fredy Bastidas", "lugar": "Av. Panamericana, Pasto",
     "plan": "NEGOCIO", "meseros": 3, "adopcion": 0.55,
     "happy_hour": [(2, 3), "19:00", "21:00", "PORCENTAJE", "Tragos y cócteles"],
     "proveedores": {"marca:Old Parr": LOCAL, "marca:Buchanan": LOCAL, "Botellas": ("Industria Licorera de Caldas", 3),
                     "_": LOCAL},
     "catalogo": {"botellas": BOTELLAS_ILC, "cocteles": COCTELES_ILC},
     "marca_principal": "Industria Licorera de Caldas (Aguardiente Cristal, Ron Viejo de Caldas)", "satisfaccion": 4.3,
     "tecnicas": "Grupos de 10 o más con descuento y puntos al organizador, referidos, happy hour de cócteles "
                 "miércoles y jueves, ofertas de regreso por WhatsApp."},
]

# ---------------------------------------------------------------------------------------------------------- tiendas
TALLAS_H, TALLAS_M, TALLAS_S = ["28", "30", "32", "34", "36"], ["26", "27", "28", "29", "30"], ["S", "M", "L", "XL"]


def _combos(tallas, colores):
    return [{"Talla": t, "Color": c} for t in tallas for c in colores]


LEVIS = "Levi's"
ROPA_CATALOGO = [
    dict(sku="LV-501", nombre="Jean Levi's 501 Original", categoria="Pantalones", costo=150000, precio=299900,
         para="hombre", variantes=_combos(TALLAS_H, ["Azul medio", "Azul oscuro"]), stock=(2, 5)),
    dict(sku="LV-505", nombre="Jean Levi's 505 Regular", categoria="Pantalones", costo=140000, precio=279900,
         para="hombre", variantes=_combos(TALLAS_H, ["Azul medio", "Negro"]), stock=(1, 4)),
    dict(sku="LV-511", nombre="Jean Levi's 511 Slim", categoria="Pantalones", costo=145000, precio=289900,
         para="hombre", variantes=_combos(TALLAS_H, ["Azul oscuro", "Negro"]), stock=(2, 5)),
    dict(sku="LV-541", nombre="Jean Levi's 541 Athletic Taper", categoria="Pantalones", costo=145000, precio=289900,
         para="hombre", variantes=_combos(TALLAS_H, ["Azul medio", "Azul claro"]), stock=(1, 3)),
    dict(sku="LV-721", nombre="Jean Levi's 721 High Rise Skinny", categoria="Pantalones", costo=140000, precio=279900,
         para="mujer", variantes=_combos(TALLAS_M, ["Azul oscuro", "Negro"]), stock=(2, 5)),
    dict(sku="LV-724", nombre="Jean Levi's 724 High Rise Straight", categoria="Pantalones", costo=140000, precio=279900,
         para="mujer", variantes=_combos(TALLAS_M, ["Azul medio", "Azul claro"]), stock=(2, 4)),
    dict(sku="LV-RIB", nombre="Jean Levi's Ribcage Straight Ankle", categoria="Pantalones", costo=160000, precio=319900,
         para="mujer", variantes=_combos(TALLAS_M, ["Azul medio", "Azul claro"]), stock=(1, 3)),
    dict(sku="LV-HM", nombre="Camiseta Levi's Housemark Logo", categoria="Camisas", costo=45000, precio=89900,
         para="todos", variantes=_combos(TALLAS_S, ["Blanco", "Negro", "Rojo"]), stock=(3, 7)),
    dict(sku="LV-BW", nombre="Camiseta Levi's Batwing Clásica", categoria="Camisas", costo=50000, precio=99900,
         para="todos", variantes=_combos(TALLAS_S, ["Blanco", "Gris"]), stock=(3, 6)),
    dict(sku="LV-TRK", nombre="Chaqueta Levi's Trucker", categoria="Chaquetas", costo=190000, precio=389900,
         para="todos", variantes=_combos(TALLAS_S, ["Azul medio", "Negro"]), stock=(1, 3)),
    dict(sku="LV-CIN", nombre="Cinturón Levi's de cuero", categoria="Accesorios", costo=45000, precio=99900,
         para="todos", variantes=[{"Color": "Café"}, {"Color": "Negro"}], stock=(3, 6)),
    dict(sku="LV-BIL", nombre="Billetera Levi's de cuero", categoria="Accesorios", costo=40000, precio=89900,
         para="todos", stock=(3, 6)),
]
for _it in ROPA_CATALOGO:
    _it.update(marca=LEVIS, proveedor="levis", minimo=1)

VAPORESSO, NASTY = "Vaporesso", "Nasty Juice"
SABORES = ["Bad Blood", "Cushman", "Slow Blow", "Asap Grape", "Trap Queen", "Fat Boy"]
VAPE_CATALOGO = [
    # 0–4 equipos
    dict(sku="VP-XR4", nombre="Vaporesso XROS 4", categoria="Dispositivos (pods)", costo=90000, precio=169900, stock=(3, 6)),
    dict(sku="VP-XR4M", nombre="Vaporesso XROS 4 Mini", categoria="Dispositivos (pods)", costo=65000, precio=124900,
         stock=(3, 6)),
    dict(sku="VP-XR5M", nombre="Vaporesso XROS 5 Mini", categoria="Dispositivos (pods)", costo=70000, precio=134900,
         stock=(2, 5)),
    dict(sku="VP-XRPRO", nombre="Vaporesso XROS Pro", categoria="Dispositivos (pods)", costo=100000, precio=189900,
         stock=(2, 4)),
    dict(sku="VP-LXR", nombre="Vaporesso LUXE XR Max", categoria="Dispositivos (pods)", costo=130000, precio=239900,
         stock=(1, 3)),
    # 5–10 repuestos
    dict(sku="VP-C06", nombre="Cartucho Vaporesso XROS 0.6 Ω (x4)", categoria="Cartuchos y resistencias", costo=30000,
         precio=59900, stock=(10, 20)),
    dict(sku="VP-C08", nombre="Cartucho Vaporesso XROS 0.8 Ω (x4)", categoria="Cartuchos y resistencias", costo=30000,
         precio=59900, stock=(12, 24)),
    dict(sku="VP-C10", nombre="Cartucho Vaporesso XROS 1.0 Ω (x4)", categoria="Cartuchos y resistencias", costo=30000,
         precio=59900, stock=(10, 20)),
    dict(sku="VP-C12", nombre="Cartucho Vaporesso XROS 1.2 Ω (x4)", categoria="Cartuchos y resistencias", costo=30000,
         precio=59900, stock=(6, 12)),
    dict(sku="VP-GTX2", nombre="Resistencia Vaporesso GTX 0.2 Ω (x5)", categoria="Cartuchos y resistencias", costo=32000,
         precio=64900, stock=(4, 8)),
    dict(sku="VP-GTX4", nombre="Resistencia Vaporesso GTX 0.4 Ω (x5)", categoria="Cartuchos y resistencias", costo=32000,
         precio=64900, stock=(4, 8)),
]
for _i, _s in enumerate(SABORES):  # 11–16 sales de nicotina (20 y 35 mg)
    VAPE_CATALOGO.append(dict(sku=f"NJ-S{_i}", nombre=f"Nasty Salt {_s} 30 ml", categoria="Líquidos y sales de nicotina",
                              costo=32000, precio=59900, vida=365, stock=(3, 6), marca=NASTY, proveedor="liquidos",
                              variantes=[{"Nicotina (mg)": "20"}, {"Nicotina (mg)": "35"}]))
VAPE_CATALOGO += [  # 17–18 líquido libre para el LUXE XR Max; 19–21 accesorios
    dict(sku="NJ-60CU", nombre="Nasty Juice Cushman 60 ml 3 mg", categoria="Líquidos y sales de nicotina", costo=45000,
         precio=84900, vida=365, stock=(2, 5), marca=NASTY, proveedor="liquidos"),
    dict(sku="NJ-60SB", nombre="Nasty Juice Slow Blow 60 ml 3 mg", categoria="Líquidos y sales de nicotina", costo=45000,
         precio=84900, vida=365, stock=(2, 5), marca=NASTY, proveedor="liquidos"),
    dict(sku="VP-COR", nombre="Cordón Vaporesso", categoria="Accesorios", costo=8000, precio=19900, stock=(4, 8)),
    dict(sku="VP-USB", nombre="Cable USB-C Vaporesso", categoria="Accesorios", costo=10000, precio=24900, stock=(4, 8)),
    dict(sku="VP-EST", nombre="Estuche de silicona para pod", categoria="Accesorios", costo=12000, precio=29900,
         stock=(3, 6)),
]
for _it in VAPE_CATALOGO:
    _it.setdefault("marca", VAPORESSO)
    _it.setdefault("proveedor", "vaporesso")

TIENDAS_DEMO = [
    dict(clave="demo-ropa", giro="ROPA", usuario="ropa.denim", negocio="Denim Store Pasto",
         dueno="Luisa Fernanda Rosero", lugar="C. C. Unicentro, Pasto", plan="EMPRENDEDOR", vendedores=2, prefijo="21",
         proveedores={"levis": ("Levi Strauss Colombia (distribuidor autorizado)", 5, "")},
         marca_principal="Levi's", catalogo=ROPA_CATALOGO, pool=700, lealtad=(2.2, 3.0), sensibilidad=[35, 40, 25],
         ritmo=(0.12, 0.7), adopcion=0.65, acepta_ofertas=0.65, anonimos=3, horario=(9.5, 20.5),
         dias_semana=[0.8, 0.8, 0.9, 0.9, 1.2, 1.6, 1.0], revisa_ofertas=0.8,
         ofertas_que_usa=["cumple", "segunda", "regreso", "vip", "quieto"], satisfaccion=4.5,
         tecnicas="Puntos y niveles, ofertas sugeridas por WhatsApp (cumpleaños, segunda compra, te extrañamos, "
                  "clientes VIP y prendas quietas) y encuesta en el comprobante."),
    dict(clave="demo-vape", giro="VAPE", usuario="vape.nube", negocio="Nube Vape Shop", dueno="Sebastián Muñoz Delgado",
         lugar="Av. de los Estudiantes, Pasto", plan="GRATIS", vendedores=0, prefijo="22",
         proveedores={"vaporesso": ("Vaporesso (distribuidor oficial)", 7, ""),
                      "liquidos": ("Distribuidora de líquidos Nasty Juice", 5, "")},
         marca_principal="Vaporesso (y líquidos Nasty Juice)", catalogo=VAPE_CATALOGO, pool=190, lealtad=(4.0, 2.0),
         sensibilidad=[30, 45, 25], ritmo=(7, 18), adopcion=0.7, acepta_ofertas=0.55, anonimos=2, horario=(10, 21),
         cierra=(6,), dias_semana=[0.9, 0.9, 1.0, 1.0, 1.3, 1.4, 1.0], revisa_ofertas=0.6,
         ofertas_que_usa=["regreso", "segunda"], satisfaccion=4.2,
         equipos=[(0, 30, [5, 6, 7]), (1, 25, [6, 7, 8]), (2, 20, [6, 7]), (3, 10, [5, 6]), (4, 15, [9, 10])],
         liquidos=[11, 12, 13, 14, 15, 16], accesorios=[19, 20, 21],
         tecnicas="Puntos y ofertas de regreso solo a clientes mayores de edad verificados (Ley 2354): la recompra de "
                  "cartuchos y líquidos es la que fideliza."),
]

for _d in NOCTURNOS_DEMO + TIENDAS_DEMO:
    _d["clave_acceso"] = CLAVE_DEMO
for _d in NOCTURNOS_DEMO:
    _d.update(cumpleanos=True, ofertas_que_usa=["regreso", "segunda", "cumple", "vip"])

NOMBRES = ["Andrea", "Juan", "Camila", "Santiago", "Valentina", "Sebastián", "Daniela", "Mateo", "Laura", "Nicolás",
           "Sofía", "Alejandro", "María José", "David", "Natalia", "Felipe", "Paula", "Andrés", "Juliana", "Carlos",
           "Mariana", "Diego", "Carolina", "Jorge", "Isabella", "Miguel", "Gabriela", "Óscar", "Luisa", "Esteban",
           "Ximena", "Kevin", "Angie", "Brayan", "Yuliana", "Cristian", "Lorena", "Fabián", "Tatiana", "Jhon"]
APELLIDOS = ["Rosero", "Benavides", "Guerrero", "Muñoz", "Ortiz", "Burbano", "Erazo", "Delgado", "Chamorro", "Bastidas",
             "Insuasty", "Villota", "Pantoja", "Ceballos", "Obando", "Narváez", "Cabrera", "Enríquez", "Zambrano",
             "Paz", "Arteaga", "López", "Martínez", "Gómez", "Rodríguez", "Jurado", "Mora", "Riascos", "Santacruz",
             "Portilla"]
COMENTARIOS = {
    "BUENO": ["Muy buena atención", "Todo excelente", "Volveré pronto", "Me atendieron rápido", "Buenos precios"],
    "MALO": ["No tenían lo que buscaba", "Se demoraron mucho", "Estaba muy lleno", "El precio subió"],
}


def personalizar(negocio, semilla: int, satisfaccion: float, hoy: date | None = None) -> dict:
    """Da nombres y cumpleaños creíbles a los clientes simulados y responde algunas encuestas (datos inventados)."""
    from apps.clientes.models import Cliente, Encuesta
    from apps.ventas.models import Venta

    rng = random.Random(f"demo-{semilla}-{negocio.pk}")
    hoy = hoy or timezone.localdate()
    edad_max = 40 if negocio.giro == "VAPE" else 58
    clientes = list(Cliente.objects.filter(negocio=negocio).order_by("pk"))
    for c in clientes:
        c.nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        if c.fecha_nacimiento is None and rng.random() < 0.3:
            c.fecha_nacimiento = date(hoy.year - rng.randint(19, edad_max), rng.randint(1, 12), rng.randint(1, 28))
        if c.primera_compra:
            c.creado = c.primera_compra
    Cliente.objects.bulk_update(clientes, ["nombre", "fecha_nacimiento", "creado"], batch_size=500)
    # encuesta en el comprobante: se entrega en ~40 % de las compras con cliente y responde ~1 de cada 3
    encuestas = []
    ventas = Venta.objects.filter(negocio=negocio, estado="COMPLETADA", cliente_ref__isnull=False).only("pk", "fecha",
                                                                                                         "cliente_ref")
    for v in ventas:
        if rng.random() >= 0.4:
            continue
        e = Encuesta(negocio=negocio, venta=v, cliente_id=v.cliente_ref_id)
        if rng.random() < 0.33:
            nota = max(1, min(5, round(rng.gauss(satisfaccion, 0.8))))
            e.calificacion, e.respondida = nota, v.fecha + timedelta(hours=rng.randint(1, 30))
            if rng.random() < 0.3:
                e.comentario = rng.choice(COMENTARIOS["BUENO" if nota >= 4 else "MALO"])
        encuestas.append(e)
    creadas = Encuesta.objects.bulk_create(encuestas, batch_size=500)
    for e in creadas:  # la encuesta nace con la venta
        Encuesta.objects.filter(pk=e.pk).update(creada=e.venta.fecha)
    return {"clientes": len(clientes), "encuestas": len(creadas),
            "respondidas": sum(1 for e in creadas if e.respondida)}


def aplicar_plan(negocio, plan: str, hoy: date | None = None):
    """Deja el negocio en su plan (sin prueba gratis, al día en el pago si es de pago)."""
    hoy = hoy or timezone.localdate()
    s = negocio.suscripcion
    s.plan, s.prueba_hasta = plan, None
    s.pagado_hasta = None if plan == "GRATIS" else hoy + timedelta(days=30)
    s.notas = MARCA_COMPLETO
    s.save()


def usuarios_demo() -> list[str]:
    tiendas = [t["usuario"] for t in TIENDAS_DEMO]
    return [n["usuario"] for n in NOCTURNOS_DEMO] + tiendas


def negocios_demo() -> list[str]:
    return [n["negocio"] for n in NOCTURNOS_DEMO] + [t["negocio"] for t in TIENDAS_DEMO]

"""Plantillas de giro: el corazón del sistema adaptativo.

Cada plantilla define banderas de configuración, categorías iniciales y atributos
personalizados por categoría. Agregar un nuevo tipo de negocio = agregar un dict aquí.
"""

from .models import Giro

NOCTURNO_CATEGORIAS = {
    "Botellas": ["Presentación (ml)"],
    "Tragos y cócteles": [],
    "Cervezas": [],
    "Bebidas sin alcohol": [],
    "Comida y pasabocas": [],
    "Entradas y cover": [],
    "Insumos de barra": [],
}
GIROS_NOCTURNOS = {"BAR", "DISCOTECA", "BAR_DISCOTECA"}
# Negocios que no pueden venderle a menores de edad: al registrar un cliente se verifica su cédula.
GIROS_SOLO_ADULTOS = GIROS_NOCTURNOS | {"VAPE"}
LEY_MENORES = {"VAPE": "Ley 2354 de 2024: prohibida la venta de vapeadores a menores de 18 años.",
               "_": "Ley 124 de 1994: prohibida la venta de bebidas alcohólicas a menores de edad."}
AVISO_OFERTAS = {
    "VAPE": ("Ley 2354 de 2024: la publicidad de vapeadores está prohibida en medios masivos y redes sociales y no puede "
             "dirigirse a menores. Las ofertas solo se envían a clientes mayores de edad verificados que las autorizaron, "
             "por mensaje personal. Ante dudas, consulta con un abogado."),
}


def solo_adultos(negocio) -> bool:
    return getattr(negocio, "giro", "") in GIROS_SOLO_ADULTOS


def exige_verificar_edad(negocio) -> bool:
    """Vapeadores: siempre (lo exige la ley). Bares y discotecas: según su configuración nocturna."""
    if negocio.giro == "VAPE":
        return True
    if negocio.giro in GIROS_NOCTURNOS:
        conf = getattr(negocio, "nocturno", None)
        return bool(conf is None or conf.exigir_mayoria_edad)
    return False

PLANTILLAS = {
    Giro.MINIMERCADO: {
        "icono": "🛒",
        "descripcion": "Alimentos, bebidas y aseo. Controla vencimientos y permite vender por kilo o litro.",
        "config": dict(
            usa_vencimientos=True,
            usa_lotes=True,
            permite_fracciones=True,
            dias_vencimiento_rojo=7,
            dias_vencimiento_amarillo=30,
        ),
        "categorias": {
            "Abarrotes": [],
            "Bebidas": [],
            "Lácteos": [],
            "Aseo": [],
            "Snacks": [],
        },
    },
    Giro.ROPA: {
        "icono": "👕",
        "descripcion": "Prendas y calzado por talla y color, con temporadas.",
        "config": dict(usa_variantes=True, usa_temporadas=True, dias_sin_movimiento=60, nivel_vip_monto=1500000,
                       nivel_frecuente_compras=3),
        "categorias": {
            "Camisas": ["Talla", "Color"],
            "Pantalones": ["Talla", "Color"],
            "Calzado": ["Talla", "Color"],
            "Accesorios": ["Color"],
        },
    },
    Giro.BELLEZA: {
        "icono": "💄",
        "descripcion": "Cosméticos por tono o tipo de piel, con control de vencimientos.",
        "config": dict(
            usa_vencimientos=True,
            usa_lotes=True,
            usa_variantes=True,
            dias_vencimiento_rojo=15,
            dias_vencimiento_amarillo=60,
        ),
        "categorias": {
            "Maquillaje": ["Tono"],
            "Cuidado de la piel": ["Tipo de piel"],
            "Cabello": [],
            "Uñas": ["Color"],
            "Fragancias": ["Presentación (ml)"],
            "Servicios": [],
            "Insumos de salón": [],
        },
    },
    Giro.FARMACIA: {
        "icono": "💊",
        "descripcion": "Medicamentos por lote, con alertas de vencimiento anticipadas.",
        "config": dict(usa_vencimientos=True, usa_lotes=True, dias_vencimiento_rojo=30, dias_vencimiento_amarillo=90,
                       permite_venta_sin_stock=False),  # medicamentos: cada unidad debe tener lote
        "categorias": {
            "Medicamentos": ["Principio activo", "Registro INVIMA"],
            "Cuidado personal": [],
            "Primeros auxilios": [],
        },
    },
    Giro.RESTAURANTE: {
        "icono": "🍽️",
        "descripcion": "Insumos perecederos: vencimientos cortos y compras frecuentes.",
        "config": dict(
            usa_vencimientos=True,
            usa_lotes=True,
            permite_fracciones=True,
            dias_vencimiento_rojo=3,
            dias_vencimiento_amarillo=7,
            horizonte_compra_dias=3,
        ),
        "categorias": {"Platos": [], "Carnes": [], "Verduras": [], "Granos": [], "Bebidas": [], "Desechables": []},
    },
    Giro.BAR: {
        "icono": "🍺",
        "descripcion": "Cuentas por mesa, botellas y tragos, happy hour, reservas y clientes frecuentes.",
        "config": dict(permite_fracciones=True, horizonte_compra_dias=7, dias_sin_movimiento=30, nivel_vip_monto=800000),
        "categorias": NOCTURNO_CATEGORIAS,
    },
    Giro.DISCOTECA: {
        "icono": "🪩",
        "descripcion": "Cover y aforo, mesas VIP con consumo mínimo, listas y grupos, botellas y tragos.",
        "config": dict(permite_fracciones=True, horizonte_compra_dias=7, dias_sin_movimiento=30, nivel_vip_monto=1500000),
        "categorias": NOCTURNO_CATEGORIAS,
    },
    Giro.BAR_DISCOTECA: {
        "icono": "🍸",
        "descripcion": "Bar temprano y discoteca en la noche: cuentas, cover, happy hour, VIP y grupos.",
        "config": dict(permite_fracciones=True, horizonte_compra_dias=7, dias_sin_movimiento=30, nivel_vip_monto=1200000),
        "categorias": NOCTURNO_CATEGORIAS,
    },
    Giro.VAPE: {
        "icono": "💨",
        "descripcion": "Pods, cartuchos, líquidos y desechables. Solo clientes mayores de edad (Ley 2354 de 2024).",
        "config": dict(usa_vencimientos=True, usa_variantes=True, dias_vencimiento_rojo=30, dias_vencimiento_amarillo=90,
                       dias_sin_movimiento=60, horizonte_compra_dias=14),
        "categorias": {
            "Dispositivos (pods)": ["Color"],
            "Cartuchos y resistencias": ["Resistencia (Ω)"],
            "Líquidos y sales de nicotina": ["Nicotina (mg)", "Sabor"],
            "Desechables": ["Sabor"],
            "Accesorios": [],
        },
    },
    Giro.GENERICO: {
        "icono": "📦",
        "descripcion": "Configuración básica; activa funciones cuando las necesites.",
        "config": {},
        "categorias": {"General": []},
    },
}


def aplicar_plantilla(negocio):
    """Crea la configuración y categorías iniciales de un negocio según su giro."""
    from apps.catalogo.models import AtributoPersonalizado, Categoria

    from .models import ConfiguracionNegocio

    plantilla = PLANTILLAS.get(negocio.giro, PLANTILLAS[Giro.GENERICO])
    config, _ = ConfiguracionNegocio.objects.update_or_create(negocio=negocio, defaults=plantilla["config"])
    if negocio.giro in GIROS_NOCTURNOS:
        from apps.nocturno.models import ConfiguracionNocturna

        ConfiguracionNocturna.objects.get_or_create(negocio=negocio, defaults=ConfiguracionNocturna.valores_para(
            negocio.giro))
    for nombre_cat, atributos in plantilla["categorias"].items():
        categoria, _ = Categoria.objects.get_or_create(negocio=negocio, nombre=nombre_cat)
        for atributo in atributos:
            AtributoPersonalizado.objects.get_or_create(categoria=categoria, nombre=atributo)
    return config


FUNCIONES = {
    "usa_vencimientos": "Control de vencimientos",
    "usa_lotes": "Lotes con salida FEFO (primero en vencer, primero en salir)",
    "usa_variantes": "Variantes (talla, color, tono…)",
    "permite_fracciones": "Ventas fraccionadas (kg, litros)",
    "usa_temporadas": "Temporadas",
}


def opciones_giro():
    """Lista para el selector del asistente de registro."""
    return [
        {"valor": giro.value, "nombre": giro.label, "icono": p["icono"], "descripcion": p["descripcion"]}
        for giro, p in PLANTILLAS.items()
    ]


def funciones_activas(config):
    return [texto for campo, texto in FUNCIONES.items() if getattr(config, campo)]

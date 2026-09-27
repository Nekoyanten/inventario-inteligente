"""Plantillas de giro: el corazón del sistema adaptativo.

Cada plantilla define banderas de configuración, categorías iniciales y atributos
personalizados por categoría. Agregar un nuevo tipo de negocio = agregar un dict aquí.
"""

from .models import Giro

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
        "config": dict(usa_variantes=True, usa_temporadas=True, dias_sin_movimiento=60),
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
        },
    },
    Giro.FARMACIA: {
        "icono": "💊",
        "descripcion": "Medicamentos por lote, con alertas de vencimiento anticipadas.",
        "config": dict(usa_vencimientos=True, usa_lotes=True, dias_vencimiento_rojo=30, dias_vencimiento_amarillo=90),
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
        "categorias": {"Carnes": [], "Verduras": [], "Granos": [], "Bebidas": [], "Desechables": []},
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

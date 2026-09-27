"""Catálogos de productos realistas por tipo de negocio para el piloto simulado.

Cada artículo base se combina con presentaciones y marcas para llegar al tamaño deseado.
Formato de artículo: (nombre, categoría, costo_min, costo_max, vida_util_dias | None, unidad)
"""

import random

MINIMERCADO = {
    "articulos": [
        ("Arroz", "Abarrotes", 2800, 5200, None, "und"), ("Azúcar", "Abarrotes", 2500, 4800, None, "und"),
        ("Aceite", "Abarrotes", 6500, 14000, None, "und"), ("Panela", "Abarrotes", 1800, 3200, None, "und"),
        ("Lenteja", "Abarrotes", 3000, 5200, None, "und"), ("Fríjol", "Abarrotes", 4200, 7600, None, "und"),
        ("Pasta", "Abarrotes", 1800, 3600, None, "und"), ("Sal", "Abarrotes", 900, 1800, None, "und"),
        ("Café molido", "Abarrotes", 6500, 16000, None, "und"), ("Chocolate de mesa", "Abarrotes", 4500, 9000, None, "und"),
        ("Atún en lata", "Abarrotes", 4200, 7800, 540, "und"), ("Harina de maíz", "Abarrotes", 2600, 4200, None, "und"),
        ("Gaseosa", "Bebidas", 1800, 6200, 180, "und"), ("Agua", "Bebidas", 900, 2600, 365, "und"),
        ("Jugo en caja", "Bebidas", 1500, 4800, 120, "und"), ("Cerveza", "Bebidas", 2100, 3600, 180, "und"),
        ("Bebida energizante", "Bebidas", 2600, 4600, 270, "und"),
        ("Leche", "Lácteos", 2700, 4300, 12, "und"), ("Yogur", "Lácteos", 1600, 5800, 21, "und"),
        ("Queso campesino", "Lácteos", 6200, 13000, 15, "und"), ("Mantequilla", "Lácteos", 3800, 7600, 60, "und"),
        ("Kumis", "Lácteos", 2400, 5200, 18, "und"),
        ("Jabón de baño", "Aseo", 1800, 5200, None, "und"), ("Detergente", "Aseo", 3800, 18000, None, "und"),
        ("Papel higiénico", "Aseo", 3200, 16000, None, "und"), ("Crema dental", "Aseo", 2800, 7600, 730, "und"),
        ("Desinfectante", "Aseo", 3200, 9800, None, "und"), ("Lavaloza", "Aseo", 2900, 7200, None, "und"),
        ("Papas fritas", "Snacks", 1100, 4200, 120, "und"), ("Galletas", "Snacks", 900, 5200, 180, "und"),
        ("Chocolatina", "Snacks", 700, 3200, 240, "und"), ("Maní", "Snacks", 900, 3800, 180, "und"),
        ("Pan tajado", "Snacks", 3200, 6200, 8, "und"),
    ],
    "presentaciones": ["250 g", "500 g", "1 kg", "x3", "x6", "personal", "familiar", "1.5 L", "400 ml"],
    "marcas": ["Diana", "Roa", "Doria", "Colanta", "Alpina", "Postobón", "Nestlé", "Frito Lay", "Familia", "Fab",
               "Colgate", "Noel", "Bavaria", "Premier", "Zenú"],
}

ROPA = {
    "articulos": [
        ("Camiseta básica", "Camisas", 12000, 22000, None, "und"), ("Camisa manga larga", "Camisas", 25000, 48000, None, "und"),
        ("Blusa", "Camisas", 18000, 42000, None, "und"), ("Polo", "Camisas", 22000, 38000, None, "und"),
        ("Jean", "Pantalones", 35000, 72000, None, "und"), ("Pantalón drill", "Pantalones", 30000, 55000, None, "und"),
        ("Sudadera", "Pantalones", 22000, 42000, None, "und"), ("Short", "Pantalones", 15000, 30000, None, "und"),
        ("Tenis", "Calzado", 45000, 120000, None, "par"), ("Sandalias", "Calzado", 18000, 45000, None, "par"),
        ("Botas", "Calzado", 60000, 140000, None, "par"),
        ("Gorra", "Accesorios", 9000, 25000, None, "und"), ("Correa", "Accesorios", 12000, 32000, None, "und"),
        ("Medias x3", "Accesorios", 7000, 15000, None, "und"), ("Bolso", "Accesorios", 30000, 85000, None, "und"),
    ],
    "tallas_ropa": ["S", "M", "L", "XL"], "tallas_calzado": ["36", "37", "38", "39", "40", "41", "42"],
    "colores": ["Negro", "Blanco", "Azul", "Gris", "Rojo", "Beige"],
    "lineas": ["Urbano", "Clásico", "Sport", "Casual", "Premium", "Básico", "Andino"],
}

BELLEZA = {
    "articulos": [
        ("Base líquida", "Maquillaje", 18000, 48000, 720, "und"), ("Labial", "Maquillaje", 9000, 32000, 900, "und"),
        ("Pestañina", "Maquillaje", 12000, 38000, 365, "und"), ("Polvo compacto", "Maquillaje", 14000, 36000, 900, "und"),
        ("Delineador", "Maquillaje", 8000, 24000, 720, "und"), ("Rubor", "Maquillaje", 11000, 30000, 900, "und"),
        ("Crema hidratante", "Cuidado de la piel", 15000, 55000, 540, "und"),
        ("Protector solar", "Cuidado de la piel", 22000, 65000, 540, "und"),
        ("Limpiador facial", "Cuidado de la piel", 14000, 42000, 540, "und"),
        ("Sérum", "Cuidado de la piel", 28000, 85000, 365, "und"),
        ("Champú", "Cabello", 9000, 38000, 900, "und"), ("Acondicionador", "Cabello", 9000, 36000, 900, "und"),
        ("Tinte", "Cabello", 12000, 28000, 720, "und"), ("Tratamiento capilar", "Cabello", 16000, 52000, 540, "und"),
        ("Esmalte", "Uñas", 3500, 14000, 900, "und"), ("Removedor", "Uñas", 4000, 9000, None, "und"),
        ("Perfume", "Fragancias", 45000, 180000, None, "und"), ("Body splash", "Fragancias", 18000, 45000, 730, "und"),
    ],
    "tonos": ["Claro", "Medio", "Canela", "Oscuro"], "presentaciones": ["30 ml", "60 ml", "120 ml", "250 ml", "400 ml"],
    "marcas": ["Vogue", "Maybelline", "L'Oréal", "Nivea", "Esika", "Cyzone", "Pantene", "Masglo", "Yanbal", "Eucerin",
               "Sedal", "Konzil"],
}

FARMACIA = {
    "articulos": [
        ("Acetaminofén", "Medicamentos", 1200, 6500, 540, "caja"), ("Ibuprofeno", "Medicamentos", 1800, 9000, 540, "caja"),
        ("Loratadina", "Medicamentos", 2500, 9500, 540, "caja"), ("Omeprazol", "Medicamentos", 3500, 14000, 540, "caja"),
        ("Amoxicilina", "Medicamentos", 6500, 18000, 365, "caja"), ("Suero oral", "Medicamentos", 2800, 6000, 365, "und"),
        ("Jarabe para la tos", "Medicamentos", 7500, 22000, 365, "und"), ("Vitamina C", "Medicamentos", 5500, 24000, 540, "caja"),
        ("Antiácido", "Medicamentos", 3200, 12000, 540, "caja"), ("Naproxeno", "Medicamentos", 2800, 11000, 540, "caja"),
        ("Losartán", "Medicamentos", 4200, 16000, 540, "caja"), ("Metformina", "Medicamentos", 3800, 14000, 540, "caja"),
        ("Crema antipañalitis", "Cuidado personal", 6500, 18000, 720, "und"),
        ("Pañales", "Cuidado personal", 18000, 52000, None, "paq"),
        ("Toallas higiénicas", "Cuidado personal", 3500, 12000, None, "paq"),
        ("Alcohol antiséptico", "Primeros auxilios", 3200, 9800, 1095, "und"),
        ("Gasas", "Primeros auxilios", 1500, 6000, 1095, "paq"), ("Curitas", "Primeros auxilios", 2200, 8000, 1095, "caja"),
        ("Tapabocas", "Primeros auxilios", 3500, 15000, 1095, "caja"),
        ("Termómetro", "Primeros auxilios", 9000, 35000, None, "und"),
    ],
    "presentaciones": ["500 mg x10", "500 mg x20", "250 mg x10", "x30", "120 ml", "60 ml", "pediátrico", "adulto"],
    "marcas": ["Genfar", "MK", "La Santé", "Tecnoquímicas", "Bayer", "Pfizer", "Procaps", "Winny", "Nosotras", "JGB"],
}

RESTAURANTE = {
    "articulos": [
        ("Pechuga de pollo", "Carnes", 13000, 17000, 4, "kg"), ("Carne de res", "Carnes", 22000, 30000, 4, "kg"),
        ("Cerdo", "Carnes", 16000, 22000, 4, "kg"), ("Chorizo", "Carnes", 14000, 20000, 12, "kg"),
        ("Tilapia", "Carnes", 14000, 19000, 3, "kg"), ("Cuy", "Carnes", 28000, 38000, 3, "und"),
        ("Papa pastusa", "Verduras", 1200, 2500, 20, "kg"), ("Tomate", "Verduras", 2200, 4500, 7, "kg"),
        ("Cebolla cabezona", "Verduras", 1800, 3600, 20, "kg"), ("Cebolla larga", "Verduras", 2000, 4200, 7, "kg"),
        ("Zanahoria", "Verduras", 1200, 2600, 15, "kg"), ("Aguacate", "Verduras", 3500, 7000, 6, "kg"),
        ("Limón", "Verduras", 2500, 5000, 12, "kg"), ("Cilantro", "Verduras", 3000, 6000, 5, "kg"),
        ("Arroz", "Granos", 3000, 4200, None, "kg"), ("Fríjol", "Granos", 6500, 8500, None, "kg"),
        ("Maíz", "Granos", 2500, 3800, None, "kg"), ("Lenteja", "Granos", 5000, 6800, None, "kg"),
        ("Gaseosa personal", "Bebidas", 1600, 2400, 180, "und"), ("Jugo natural (pulpa)", "Bebidas", 7000, 11000, 30, "kg"),
        ("Cerveza", "Bebidas", 2200, 3200, 180, "und"), ("Agua", "Bebidas", 800, 1400, 365, "und"),
        ("Contenedor icopor", "Desechables", 180, 450, None, "und"), ("Vaso desechable", "Desechables", 60, 180, None, "und"),
        ("Servilletas", "Desechables", 2500, 6000, None, "paq"), ("Bolsa para domicilio", "Desechables", 80, 250, None, "und"),
    ],
    "presentaciones": ["", "especial", "selección", "orgánico", "x12", "x24", "grande", "mediano"],
    "marcas": ["Plaza del Potrerillo", "Mercado El Tejar", "Avícola Nariño", "Frigorífico Pasto", "Postobón", "Bavaria",
               "Darnel", "Familia"],
}

GENERICO = {  # ferretería / papelería / mascotas: categorías propias
    "articulos": [
        ("Tornillo", "Tornillería", 50, 400, None, "und"), ("Puntilla", "Tornillería", 3000, 9000, None, "caja"),
        ("Chazo", "Tornillería", 80, 350, None, "und"), ("Martillo", "Herramientas", 12000, 38000, None, "und"),
        ("Destornillador", "Herramientas", 5000, 22000, None, "und"), ("Alicate", "Herramientas", 9000, 32000, None, "und"),
        ("Cinta métrica", "Herramientas", 6000, 25000, None, "und"), ("Pintura", "Pinturas", 18000, 95000, 720, "und"),
        ("Brocha", "Pinturas", 2500, 12000, None, "und"), ("Rodillo", "Pinturas", 6000, 18000, None, "und"),
        ("Cable eléctrico", "Eléctricos", 1200, 3800, None, "m"), ("Bombillo LED", "Eléctricos", 3500, 12000, None, "und"),
        ("Tomacorriente", "Eléctricos", 3000, 11000, None, "und"), ("Interruptor", "Eléctricos", 2800, 9000, None, "und"),
        ("Tubo PVC", "Plomería", 6000, 24000, None, "und"), ("Codo PVC", "Plomería", 600, 3200, None, "und"),
        ("Llave de paso", "Plomería", 9000, 28000, None, "und"), ("Silicona", "Plomería", 5000, 14000, 540, "und"),
        ("Cuaderno", "Papelería", 2200, 9000, None, "und"), ("Lapicero", "Papelería", 600, 3200, None, "und"),
    ],
    "presentaciones": ['1/4"', '1/2"', '3/4"', "pequeño", "mediano", "grande", "x10", "x50", "galón", "cuarto"],
    "marcas": ["Stanley", "Truper", "Pintuco", "Pavco", "Sylvania", "Norma", "Bic", "Uyustools", "Luminex"],
}

CATALOGOS = {"MINIMERCADO": MINIMERCADO, "ROPA": ROPA, "BELLEZA": BELLEZA, "FARMACIA": FARMACIA,
             "RESTAURANTE": RESTAURANTE, "GENERICO": GENERICO}


def generar_catalogo(giro: str, cantidad: int, rng: random.Random) -> list[dict]:
    """Devuelve `cantidad` productos únicos. Ropa se genera como familias con variantes talla × color."""
    cat = CATALOGOS[giro]
    productos, vistos = [], set()
    if giro == "ROPA":
        familias = []
        for base, categoria, cmin, cmax, _v, unidad in cat["articulos"]:
            for linea in cat["lineas"]:
                familias.append((f"{base} {linea}", categoria, cmin, cmax, unidad))
        rng.shuffle(familias)
        for nombre, categoria, cmin, cmax, unidad in familias:
            tallas = cat["tallas_calzado"] if categoria == "Calzado" else (
                ["Única"] if categoria == "Accesorios" else cat["tallas_ropa"])
            colores = rng.sample(cat["colores"], k=rng.randint(1, 3))
            costo = rng.randint(cmin, cmax) // 100 * 100
            variantes = [{"Talla": t, "Color": c} for t in tallas for c in colores]
            if len(productos) + len(variantes) > cantidad:
                continue
            productos.append({"familia": nombre, "categoria": categoria, "costo": costo, "variantes": variantes,
                              "vida": None, "unidad": unidad})
            if sum(len(p["variantes"]) for p in productos) >= cantidad - 3:
                break
        return productos
    intentos = 0
    while len(productos) < cantidad and intentos < cantidad * 50:
        intentos += 1
        base, categoria, cmin, cmax, vida, unidad = rng.choice(cat["articulos"])
        marca = rng.choice(cat["marcas"])
        pres = rng.choice(cat.get("presentaciones", [""]))
        extra = rng.choice(cat.get("tonos", [""])) if giro == "BELLEZA" and categoria == "Maquillaje" else ""
        nombre = " ".join(x for x in (base, marca, pres, extra) if x)
        if nombre in vistos:
            continue
        vistos.add(nombre)
        productos.append({"nombre": nombre, "categoria": categoria, "costo": rng.randint(cmin, cmax) // 50 * 50,
                          "vida": vida, "unidad": unidad})
    return productos

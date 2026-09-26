"""Fuente del backlog. Ejecutar para regenerar docs/backlog.json:  python scripts/generar_backlog.py"""

import json
from pathlib import Path

HITOS = [
    ("Fase 0 · Fundaciones", "Repo, Docker, CI, negocio + plantillas de giro, roles."),
    ("Fase 1 · MVP Registrar y Controlar", "Productos, movimientos, ventas, kárdex y semáforo de stock."),
    ("Fase 2 · Proveedores, Compras y Vencimientos", "Proveedores, órdenes de compra, recepción, lotes FEFO, conteo físico."),
    ("Fase 3 · Analizar y Alertar", "Demanda diaria, rotación, anomalías, motor de alertas y dashboard."),
    ("Fase 4 · Predecir y Recomendar", "Pronóstico, punto de reorden y pedido sugerido explicado."),
    ("Fase 5 · Reportes y Móvil", "Reportes con exportación, PWA y API REST."),
    ("Fase 6 · Producción", "Despliegue, backups, seguridad y manual de usuario."),
]

ETIQUETAS = {
    # tipo
    "tipo:historia": ("1d76db", "Funcionalidad visible para el usuario"),
    "tipo:tecnica": ("5319e7", "Tarea técnica / infraestructura"),
    "tipo:bug": ("d73a4a", "Error"),
    "tipo:docs": ("0075ca", "Documentación"),
    # prioridad
    "prioridad:alta": ("b60205", ""),
    "prioridad:media": ("fbca04", ""),
    "prioridad:baja": ("c2e0c6", ""),
    # estado de la base de código
    "base-implementada": ("0e8a16", "El modelo/servicio ya existe en el esqueleto; falta UI, pulir o ampliar"),
    "inteligencia": ("f9a8d4", "Parte del motor inteligente (analítica, alertas, recomendaciones)"),
    "adaptativo": ("a2eeef", "Relacionado con plantillas de giro y configuración"),
}
MODULOS = ["core", "usuarios", "catalogo", "proveedores", "inventario", "ventas", "compras",
           "analitica", "alertas", "recomendaciones", "dashboard", "reportes", "frontend", "infra"]
for m in MODULOS:
    ETIQUETAS[f"modulo:{m}"] = ("ededed", f"apps/{m}" if m not in ("frontend", "infra") else m)


def issue(fase, titulo, modulo, tipo, prioridad, historia, criterios, extra=(), notas=""):
    cuerpo = ""
    if historia:
        cuerpo += f"{historia}\n\n"
    cuerpo += "### Criterios de aceptación\n" + "\n".join(f"- [ ] {c}" for c in criterios) + "\n"
    if notas:
        cuerpo += f"\n### Notas técnicas\n{notas}\n"
    return {
        "titulo": titulo,
        "hito": HITOS[fase][0],
        "etiquetas": [f"modulo:{modulo}", f"tipo:{tipo}", f"prioridad:{prioridad}", *extra],
        "cuerpo": cuerpo,
    }


ISSUES = [
    # ------------------------------------------------------------------ FASE 0
    issue(0, "Configurar entorno local y Docker Compose (Django + PostgreSQL)", "infra", "tecnica", "alta", "",
          ["`docker compose up` levanta web + db", "`.env.example` documentado", "README con pasos de instalación probados"],
          ["base-implementada"]),
    issue(0, "Pipeline de CI: ruff, migraciones y pytest en GitHub Actions", "infra", "tecnica", "alta", "",
          ["CI corre en cada PR y en main", "Falla si faltan migraciones", "Badge de estado en el README"],
          ["base-implementada"]),
    issue(0, "Registro de negocio con asistente de plantilla de giro", "core", "historia", "alta",
          "**Como** emprendedor **quiero** registrar mi negocio eligiendo su tipo **para** que el sistema se configure solo.",
          ["Formulario de 2 pasos: datos del negocio → giro", "Al guardar se aplica `aplicar_plantilla()`",
           "Se crea el usuario administrador del negocio", "Se muestra resumen de funciones activadas"],
          ["base-implementada", "adaptativo"], notas="Ver `apps/core/plantillas.py` y la señal en `apps/core/signals.py`."),
    issue(0, "Pantalla de configuración del negocio (banderas y umbrales)", "core", "historia", "media",
          "**Como** administrador **quiero** activar/desactivar vencimientos, lotes, variantes y fracciones **para** adaptar el sistema a mi negocio.",
          ["Editar todas las banderas de `ConfiguracionNegocio`", "Editar umbrales del semáforo", "Los menús y campos se ocultan según las banderas"],
          ["adaptativo"]),
    issue(0, "Gestión de usuarios y roles (Administrador, Vendedor, Encargado de inventario)", "usuarios", "historia", "alta",
          "**Como** administrador **quiero** crear usuarios con un rol **para** controlar qué puede hacer cada persona.",
          ["CRUD de usuarios limitado al propio negocio", "Asignación de rol", "Vistas protegidas con `@requiere_permiso`",
           "Test: un vendedor no puede registrar ajustes"], ["base-implementada"]),
    issue(0, "Aislamiento multi-negocio en todas las consultas", "core", "tecnica", "alta", "",
          ["Ningún queryset de vistas devuelve datos de otro negocio", "Mixin/helper `del_negocio(request)` reutilizable",
           "Tests de aislamiento entre dos negocios"]),
    issue(0, "Bitácora de auditoría visible para el administrador", "core", "historia", "media",
          "**Como** administrador **quiero** ver quién modificó el inventario **para** tener trazabilidad.",
          ["Listado filtrable por usuario, acción y fecha", "Solo lectura"], ["base-implementada"]),

    # ------------------------------------------------------------------ FASE 1
    issue(1, "CRUD de productos (móvil primero)", "catalogo", "historia", "alta",
          "**Como** administrador **quiero** registrar productos con SKU, precios, stock mínimo, unidad, imagen y estado.",
          ["Crear/editar/desactivar producto", "SKU único por negocio", "Imagen opcional", "`stock_actual` no editable en el formulario",
           "Stock inicial se registra como movimiento ENTRADA_INICIAL"], ["base-implementada"]),
    issue(1, "Atributos personalizados por categoría en el formulario de producto", "catalogo", "historia", "media",
          "**Como** tienda de ropa **quiero** que al elegir 'Camisas' me pida Talla y Color.",
          ["El formulario genera campos dinámicos según `AtributoPersonalizado`", "Valida obligatorios y opciones",
           "Se guardan en `Producto.atributos`"], ["base-implementada", "adaptativo"]),
    issue(1, "Variantes de producto (talla/color/tono) con stock independiente", "catalogo", "historia", "media",
          "**Como** negocio con `usa_variantes` **quiero** manejar 'Camisa azul M' y 'Camisa azul L' por separado.",
          ["Modelo de variantes o producto padre/hijo", "Stock y alertas por variante", "Solo visible si la bandera está activa"],
          ["adaptativo"]),
    issue(1, "Listado de productos con semáforo, búsqueda y filtros", "catalogo", "historia", "alta",
          "**Como** empresario **quiero** ver de un vistazo qué productos están 🟢 🟡 🔴.",
          ["Columnas: producto, stock, mínimo, precio, estado", "Buscar por nombre/SKU/código de barras",
           "Filtrar por categoría y estado", "Paginado, usable en celular"]),
    issue(1, "Categorías, marcas y unidades de medida", "catalogo", "historia", "media", "",
          ["CRUD simple", "Unidades con/ sin decimales según `permite_fracciones`"], ["base-implementada"]),
    issue(1, "Registrar entradas y salidas de inventario con motivo", "inventario", "historia", "alta",
          "**Como** encargado de inventario **quiero** registrar compras, devoluciones, dañados, vencidos y ajustes.",
          ["Formulario rápido: producto + tipo + cantidad + motivo", "Motivo obligatorio en ajustes/dañados/devoluciones",
           "No permite stock negativo", "Usa `registrar_movimiento()`"], ["base-implementada"]),
    issue(1, "Kárdex del producto: '¿por qué tengo solo 8 unidades?'", "inventario", "historia", "alta",
          "**Como** empresario **quiero** ver el historial de movimientos de un producto.",
          ["Tabla con fecha, tipo, cantidad (+/−), saldo, usuario y motivo", "Filtro por rango de fechas", "Exportable a CSV"],
          ["base-implementada"]),
    issue(1, "Punto de venta simple (registrar venta)", "ventas", "historia", "alta",
          "**Como** vendedor **quiero** registrar una venta rápido desde el celular.",
          ["Buscar producto por nombre o código de barras", "Carrito con cantidades y descuento", "Medio de pago",
           "Toda la venta falla si algún producto no tiene stock", "Muestra total y confirma"], ["base-implementada"]),
    issue(1, "Anular venta con reversión de inventario", "ventas", "historia", "media", "",
          ["Solo administrador", "Genera ENTRADA_DEVOLUCION_CLIENTE por cada línea", "Queda en auditoría con motivo"]),
    issue(1, "Consulta rápida de disponibilidad", "catalogo", "historia", "media",
          "**Como** vendedor **quiero** preguntar '¿cuánto tengo de X?' desde el celular.",
          ["Búsqueda instantánea", "Muestra stock, estado y precio de venta (no costo para vendedores)"]),
    issue(1, "Lector de código de barras con la cámara del celular", "frontend", "historia", "baja", "",
          ["Escanear en venta y en entradas", "Fallback a búsqueda manual"]),

    # ------------------------------------------------------------------ FASE 2
    issue(2, "CRUD de proveedores y productos que suministran", "proveedores", "historia", "alta", "",
          ["Datos de contacto y WhatsApp", "Productos con precio, tiempo de entrega y múltiplo de empaque",
           "Proveedor principal por producto"], ["base-implementada"]),
    issue(2, "Desempeño del proveedor: tiempo real de entrega y cumplimiento", "proveedores", "historia", "media",
          "**Como** empresario **quiero** saber que el Proveedor A tarda 3 días y el B 7.",
          ["Tiempo promedio real calculado desde órdenes recibidas", "% de órdenes completas y a tiempo",
           "Historial de compras por proveedor"], ["base-implementada", "inteligencia"]),
    issue(2, "Órdenes de compra: crear, enviar y recibir (total/parcial)", "compras", "historia", "alta",
          "**Como** empresario **quiero** generar una orden, enviarla y registrar lo que llega.",
          ["Estados BORRADOR→ENVIADA→CONFIRMADA→PARCIAL/RECIBIDA", "Recepción crea movimientos ENTRADA_COMPRA y lotes",
           "Calcula días de entrega", "Actualiza último costo"], ["base-implementada"]),
    issue(2, "Enviar orden de compra al proveedor (PDF y enlace de WhatsApp)", "compras", "historia", "media", "",
          ["PDF con logo, productos y cantidades", "Botón 'Enviar por WhatsApp' con mensaje prellenado"]),
    issue(2, "Ingreso rápido de factura de proveedor (sin OCR)", "compras", "historia", "media",
          "**Como** negocio cuyos proveedores entregan facturas a mano **quiero** un formulario rápido para cargar la compra.",
          ["Agregar líneas con autocompletado", "Crear producto nuevo en línea", "Total y costo por línea"]),
    issue(2, "Lotes y fechas de vencimiento con salida FEFO", "inventario", "historia", "alta", "",
          ["Pedir fecha de vencimiento en entradas si `usa_vencimientos`", "Salidas consumen primero el lote que vence antes",
           "Vista de lotes por producto con 🔴🟡🟢"], ["base-implementada", "adaptativo"]),
    issue(2, "Conteo físico vs. inventario del sistema", "inventario", "historia", "alta",
          "**Como** encargado **quiero** registrar lo que cuento físicamente y que el sistema calcule la diferencia.",
          ["Crear conteo (total o por categoría)", "Capturar cantidades en celular", "Motivo obligatorio para cada diferencia",
           "Administrador aprueba → ajustes automáticos"], ["base-implementada"]),

    # ------------------------------------------------------------------ FASE 3
    issue(3, "Agregado de demanda diaria y reconstrucción histórica", "analitica", "tecnica", "alta", "",
          ["`DemandaDiaria` se actualiza en cada venta", "Comando para reconstruir desde movimientos", "Descontar anulaciones"],
          ["base-implementada", "inteligencia"]),
    issue(3, "Demanda censurada: no subestimar productos que estuvieron agotados", "analitica", "tecnica", "media",
          "Un producto agotado no vende, y el sistema cree que su demanda bajó (caso 'Arroz' del demo).",
          ["Excluir del cálculo los días con stock 0", "Test con producto agotado 10 días"], ["inteligencia"]),
    issue(3, "Clasificación de rotación (alta/media/baja) y análisis ABC", "analitica", "historia", "media", "",
          ["Rotación por producto visible en listado", "ABC por ingresos (80/15/5)", "Valor de inventario inmovilizado"],
          ["base-implementada", "inteligencia"]),
    issue(3, "Motor de alertas: bandeja con severidad y acciones", "alertas", "historia", "alta",
          "**Como** empresario **quiero** ver qué debo atender primero.",
          ["Bandeja agrupada 🔴 / 🟡 / 🔵", "Marcar vista / resuelta / descartada", "Enlace a la acción sugerida",
           "Las alertas se autorresuelven cuando la condición desaparece"], ["base-implementada", "inteligencia"]),
    issue(3, "Detección de movimientos anómalos (ventas y ajustes)", "alertas", "historia", "media",
          "El sistema **detecta y solicita revisión, no acusa**.",
          ["Z-score robusto en ventas diarias (hecho)", "Aplicar también a ajustes de inventario",
           "El usuario puede justificar la anomalía"], ["base-implementada", "inteligencia"]),
    issue(3, "Análisis programado nocturno (cron) y tras cada movimiento", "alertas", "tecnica", "media", "",
          ["`manage.py analizar_inventario` en cron", "Evaluación por producto en `on_commit`", "Logs de ejecución"],
          ["base-implementada"]),
    issue(3, "Dashboard '¿Cómo está mi negocio?'", "dashboard", "historia", "alta", "",
          ["Tarjetas: inventario, ventas del mes (+% vs anterior), inmovilizado, alertas", "Carga < 1 s con 5.000 productos",
           "Legible en celular"], ["base-implementada"]),
    issue(3, "Notificaciones de alertas críticas (email / WhatsApp / push)", "alertas", "historia", "baja", "",
          ["Resumen diario configurable", "Solo alertas 🔴"]),

    # ------------------------------------------------------------------ FASE 4
    issue(4, "Pronóstico de demanda por período (Holt) con rango", "analitica", "historia", "alta",
          "**Como** empresario **quiero** saber cuánto venderé el próximo mes, como un rango aproximado.",
          ["Gráfico histórico + pronóstico en la ficha del producto", "Mostrar como rango, no número exacto",
           "Texto explicativo sin tecnicismos"], ["base-implementada", "inteligencia"]),
    issue(4, "Estacionalidad y temporadas (ropa, fechas especiales)", "analitica", "historia", "baja", "",
          ["Holt-Winters cuando hay ≥ 2 años de datos", "Marcar temporadas manualmente (Navidad, regreso a clases)"],
          ["inteligencia", "adaptativo"]),
    issue(4, "Recomendaciones de compra explicadas", "recomendaciones", "historia", "alta",
          "**Como** empresario **quiero** que el sistema me diga cuánto pedir y por qué; yo decido.",
          ["Lista con cantidad sugerida y explicación", "Editar cantidad antes de aceptar", "Descartar con motivo",
           "Considera en tránsito, múltiplo de empaque y tiempo de entrega"], ["base-implementada", "inteligencia"]),
    issue(4, "Convertir recomendaciones en órdenes de compra agrupadas por proveedor", "recomendaciones", "historia", "alta", "",
          ["Seleccionar varias recomendaciones → una orden por proveedor", "Queda en BORRADOR para revisión"],
          ["base-implementada"]),
    issue(4, "Medir la precisión del pronóstico (error MAPE) y ajustar parámetros", "analitica", "tecnica", "baja", "",
          ["Guardar pronóstico vs. real", "Reporte de precisión por producto", "Parámetros α/β por negocio"],
          ["inteligencia"]),

    # ------------------------------------------------------------------ FASE 5
    issue(5, "Reportes: inventario, movimientos, ventas, compras", "reportes", "historia", "alta", "",
          ["Filtros por fecha, categoría y producto", "Vista en pantalla + exportar"], ["base-implementada"]),
    issue(5, "Reportes: más/menos vendidos, por vencer, agotados, valor e utilidad estimada", "reportes", "historia", "media", "",
          ["Cada reporte con exportación", "Utilidad = ventas − costo de lo vendido"]),
    issue(5, "Exportación a PDF", "reportes", "historia", "media", "",
          ["Plantilla PDF con encabezado del negocio", "WeasyPrint o ReportLab"]),
    issue(5, "PWA instalable (manifest, service worker, modo sin conexión para consulta)", "frontend", "historia", "media",
          "**Como** empresario **quiero** consultar mi inventario desde el celular fuera del negocio.",
          ["Instalable en Android/iOS", "Caché de la última consulta"]),
    issue(5, "API REST (Django REST Framework) con autenticación por token", "core", "tecnica", "baja", "",
          ["Endpoints de productos, movimientos, ventas, alertas", "Documentación OpenAPI"]),
    issue(5, "Importar productos desde Excel/CSV", "catalogo", "historia", "media",
          "**Como** negocio que ya tiene una lista en Excel **quiero** cargarla de una vez.",
          ["Plantilla descargable", "Validación con reporte de errores por fila", "Crea stock inicial"]),

    # ------------------------------------------------------------------ FASE 6
    issue(6, "Despliegue en producción (Render / Railway / VPS) con PostgreSQL", "infra", "tecnica", "alta", "",
          ["HTTPS", "Variables de entorno seguras", "Static files con WhiteNoise", "Cron del análisis nocturno"]),
    issue(6, "Backups automáticos de la base de datos", "infra", "tecnica", "alta", "", ["Backup diario", "Prueba de restauración documentada"]),
    issue(6, "Endurecimiento de seguridad (OWASP)", "infra", "tecnica", "alta", "",
          ["`manage.py check --deploy` sin advertencias", "Límite de intentos de login", "Revisión de permisos por rol"]),
    issue(6, "Manual de usuario para el empresario", "core", "docs", "media", "",
          ["Guía con capturas: primeros pasos, vender, comprar, alertas", "Lenguaje sin tecnicismos"]),
    issue(6, "Prueba piloto con los 5 negocios que validaron la idea", "core", "historia", "alta", "",
          ["Onboarding de cada negocio", "Encuesta de satisfacción", "Lista de mejoras priorizadas"]),
]

if __name__ == "__main__":
    salida = Path(__file__).resolve().parent.parent / "docs" / "backlog.json"
    datos = {
        "hitos": [{"titulo": t, "descripcion": d} for t, d in HITOS],
        "etiquetas": [{"nombre": n, "color": c, "descripcion": d} for n, (c, d) in ETIQUETAS.items()],
        "issues": ISSUES,
    }
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(ISSUES)} issues, {len(HITOS)} hitos, {len(ETIQUETAS)} etiquetas → {salida}")

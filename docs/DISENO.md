# Diseño del Sistema — Inventario Inteligente para Pequeños Emprendedores

> **Registrar → Controlar → Analizar → Predecir → Recomendar → Actuar**

Un sistema que no solo dice *"tienes 8 unidades"*, sino *"tienes 8, vendes ~3 por día, tu proveedor tarda 4 días: pide 37 unidades"*.

---

## 1. Principios de diseño

| Principio | Cómo se aplica |
|---|---|
| **Simplicidad** | Semáforo 🟢 Normal · 🟡 Revisar · 🔴 Actuar en todo el sistema. Nada de jerga contable. |
| **Adaptativo** | Un mismo núcleo sirve a una tienda de ropa, un minimercado o una farmacia. El negocio elige una **plantilla de giro** y el sistema activa/oculta funciones (vencimientos, lotes, tallas/colores, fracciones). |
| **Trazabilidad total** | El stock **nunca** se edita a mano: todo cambio es un `Movimiento` con usuario, fecha, tipo y motivo. |
| **El sistema sugiere, el empresario decide** | Alertas y pedidos sugeridos siempre son recomendaciones con explicación; nunca acciones automáticas. |
| **Detecta, no acusa** | Las anomalías piden revisión, no señalan culpables. |
| **Mobile-first** | Todo se puede consultar desde el celular (PWA). |
| **Bajo costo** | Un monolito Django + PostgreSQL corre en un VPS pequeño o un plan gratuito. |
| **Escalable** | Índices y agregados diarios para pasar de 50 a 5.000 productos sin cambiar la arquitectura. |

---

## 2. ¿Cómo es "adaptativo"? — Plantillas de giro

Al registrar el negocio se elige un **giro**. Cada giro es una plantilla que precarga configuración (`ConfiguracionNegocio`) y categorías. El empresario puede cambiar cualquier bandera después.

| Bandera (feature flag) | Minimercado | Ropa | Belleza | Farmacia | Restaurante | Genérico |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `usa_vencimientos` | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| `usa_lotes` | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| `usa_variantes` (talla/color/tono) | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `permite_fracciones` (kg, L) | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `usa_temporadas` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `dias_alerta_vencimiento_rojo` | 7 | – | 15 | 30 | 3 | 7 |
| `dias_alerta_vencimiento_amarillo` | 30 | – | 60 | 90 | 7 | 30 |

Además, cada **categoría** puede definir **atributos personalizados** (`AtributoPersonalizado`) — p. ej. *Talla* y *Color* para ropa, *Tono* para maquillaje, *Principio activo* para farmacia — que se guardan en `Producto.atributos` (JSON). Así el sistema se adapta sin crear tablas nuevas.

---

## 3. Arquitectura

### 3.1 Vista general

```
                     ┌──────────────────────────────┐
  Celular / PC  ───▶ │  Frontend: Django Templates  │   PWA, HTMX, mobile-first
                     │  + API REST (DRF, fase 2)    │
                     └──────────────┬───────────────┘
                                    │
┌───────────────────────────────────┴───────────────────────────────────┐
│                         DJANGO (monolito modular)                     │
│                                                                       │
│   core ─ usuarios ─ catalogo ─ proveedores ─ inventario               │
│                                   │                                   │
│                      ventas ──────┼────── compras                     │
│                                   │                                   │
│            analitica ◀────────────┴────────▶ alertas                  │
│                 │                               │                     │
│                 └────────▶ recomendaciones ◀────┘                     │
│                                   │                                   │
│                        dashboard · reportes                           │
└───────────────────────────────────┬───────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
     PostgreSQL              Tareas programadas          Exportaciones
  (datos + agregados)     (cron → manage.py analizar)   CSV · Excel · PDF
```

### 3.2 Capas dentro de cada app

```
app/
├── models.py      # Datos (entidades)
├── services.py    # Reglas de negocio (ÚNICO lugar que modifica stock)
├── selectors.py   # Consultas de lectura optimizadas
├── views.py       # HTTP → llama services/selectors
├── forms.py
├── admin.py
└── tests/
```

**Regla de oro:** las vistas nunca tocan `Producto.stock_actual`. Solo `inventario.services.registrar_movimiento()` lo hace, dentro de una transacción con bloqueo de fila (`select_for_update`).

### 3.3 Stack

| Capa | Tecnología | Por qué |
|---|---|---|
| Backend | Python 3.12 · Django 5.2 | Admin gratis, ORM, auth y permisos por grupos. |
| Base de datos | PostgreSQL 16 (SQLite en desarrollo) | Transacciones, JSONB para atributos, índices. |
| Frontend | Django Templates + HTMX + CSS propio | Sin build complejo; rápido en celulares modestos. |
| Analítica | Python puro (fase 1) → pandas / statsmodels (fase 3) | Empezar simple y explicable. |
| Tareas | `manage.py analizar_inventario` vía cron (fase 1) → Celery (fase 4) | Bajo costo. |
| Reportes | openpyxl (Excel), csv, WeasyPrint (PDF) | |
| Calidad | pytest-django, ruff, GitHub Actions | |
| Despliegue | Docker Compose (web + db) | Un comando. |

---

## 4. Módulos y responsabilidades

| # | Módulo (app) | Responsabilidad | Entidades principales |
|---|---|---|---|
| 1 | `core` | Negocio, plantilla de giro, configuración, auditoría | `Negocio`, `ConfiguracionNegocio`, `RegistroAuditoria` |
| 2 | `usuarios` | Usuarios y roles | `Usuario` (rol) + Grupos Django |
| 3 | `catalogo` | Productos y su clasificación | `Categoria`, `Marca`, `UnidadMedida`, `Producto`, `AtributoPersonalizado` |
| 4 | `proveedores` | Proveedores y su desempeño | `Proveedor`, `ProductoProveedor` |
| 5 | `inventario` | Stock, movimientos, lotes, conteos | `Lote`, `Movimiento`, `ConteoFisico`, `DetalleConteo` |
| 6 | `ventas` | Registro de ventas | `Venta`, `DetalleVenta` |
| 7 | `compras` | Órdenes de compra y recepción | `OrdenCompra`, `DetalleOrdenCompra` |
| 8 | `analitica` | Demanda, pronóstico, rotación, anomalías | `DemandaDiaria` (agregado), servicios de cálculo |
| 9 | `alertas` | Motor de reglas y bandeja de alertas | `Alerta` |
| 10 | `recomendaciones` | Pedido sugerido explicado | `RecomendacionCompra` |
| 11 | `dashboard` | Pantalla "¿Cómo está mi negocio?" | (solo lectura) |
| 12 | `reportes` | Reportes y exportación | (solo lectura) |

---

## 5. Modelo de datos (ER simplificado)

```
Negocio 1──1 ConfiguracionNegocio
   │
   ├──* Usuario (rol: ADMIN | VENDEDOR | INVENTARIO)
   ├──* Categoria 1──* AtributoPersonalizado
   ├──* Proveedor
   └──* Producto ─────────────┬──* Lote (fecha_vencimiento, cantidad)
          │  sku, nombre,     ├──* Movimiento (tipo, cantidad, usuario, motivo, fecha, lote?)
          │  precio_compra,   ├──* ProductoProveedor (precio, tiempo_entrega) *──1 Proveedor
          │  precio_venta,    ├──* DemandaDiaria (fecha, cantidad_vendida)
          │  stock_actual,    ├──* Alerta
          │  stock_minimo,    └──* RecomendacionCompra
          │  atributos(JSON)
          │
Venta 1──* DetalleVenta *──1 Producto      → genera Movimiento(SALIDA_VENTA)
OrdenCompra 1──* DetalleOrdenCompra        → al recibir genera Movimiento(ENTRADA_COMPRA)
ConteoFisico 1──* DetalleConteo            → al aprobar genera Movimiento(AJUSTE_*)
```

### 5.1 Tipos de movimiento

| Entradas (+) | Salidas (−) |
|---|---|
| `ENTRADA_COMPRA` — compra a proveedor | `SALIDA_VENTA` — venta |
| `ENTRADA_DEVOLUCION_CLIENTE` | `SALIDA_DANADO` — producto dañado |
| `ENTRADA_AJUSTE` — ajuste positivo | `SALIDA_VENCIDO` — producto vencido |
| `ENTRADA_INICIAL` — inventario inicial | `SALIDA_DEVOLUCION_PROVEEDOR` |
| | `SALIDA_AJUSTE` — ajuste negativo |

Cada movimiento guarda: **producto + cantidad + fecha + tipo + usuario + motivo** (+ lote, costo unitario, stock resultante, referencia a venta/compra/conteo). Los movimientos son **inmutables**: un error se corrige con un movimiento inverso, nunca editando.

Esto permite responder *"¿Por qué tengo solo 8 unidades?"* con el kárdex del producto.

---

## 6. La inteligencia: algoritmos (explicables)

Todos los cálculos usan la **demanda diaria** (`DemandaDiaria`) agregada a partir de las ventas.

### 6.1 Estado del stock (semáforo)

| Estado | Regla |
|---|---|
| ⚫ Agotado | `stock == 0` |
| 🔴 Crítico | `stock ≤ stock_minimo / 2` **o** días de cobertura < tiempo de entrega del proveedor |
| 🟡 Bajo | `stock ≤ stock_minimo` |
| 🟢 Normal | resto |
| 🔵 Exceso | días de cobertura > `dias_exceso` (config, por defecto 90) |

### 6.2 Demanda diaria estimada (d)

Suavizado exponencial simple sobre las ventas diarias de los últimos *N* días (configurable, por defecto 28):

```
nivel_t = α · ventas_t + (1 − α) · nivel_(t−1)          α = 0.3
d = nivel final
```

Con menos de 7 días de historia se usa el promedio simple.

### 6.3 Riesgo de agotamiento

```
días_de_cobertura = stock_actual / d
```

> "Según el ritmo de ventas actual, este producto podría agotarse aproximadamente en **2 días**."

### 6.4 Pronóstico por período (fase 3)

Método de Holt (nivel + tendencia) sobre ventas mensuales/semanales:

```
Ene 30 → Feb 35 → Mar 42 → Abr 48 → May 51   ⇒   Jun ≈ 55–57
```

Se muestra como rango, no como número exacto: *"utiliza datos históricos para estimar escenarios futuros"*.

### 6.5 Punto de reorden y pedido sugerido

```
L   = tiempo de entrega del proveedor (días)
σd  = desviación estándar de la demanda diaria
SS  = stock de seguridad = max(stock_minimo, z · σd · √L)      z = 1.65 (95 %)
ROP = punto de reorden   = d · L + SS
H   = horizonte de cobertura deseado (config, por defecto 7 días)

Pedido sugerido = max(0, ⌈d · (L + H) + SS − stock_actual − en_tránsito⌉)
                  redondeado al múltiplo de empaque del proveedor
```

Ejemplo del enunciado: café, stock 8, demanda 35/semana (5/día), SS 10, L 0, H 7 → `35 + 10 − 8 = 37` ✅

Cada recomendación guarda **su explicación** en texto: *"Tienes 5 unidades, vendes aproximadamente 3 por día y tu proveedor tarda 4 días en entregar. Existe riesgo de agotamiento. Se recomienda pedir ~22 unidades."*

### 6.6 Rotación

| Clase | Regla (configurable) |
|---|---|
| 🟢 Alta | vendido en ≥ 50 % de los días del período |
| 🟡 Media | 15 %–50 % |
| 🔴 Baja | < 15 % **o** sin ventas en `dias_sin_movimiento` (por defecto 45) |

**Inventario inmovilizado** = Σ (stock × precio_compra) de productos de baja rotación.

### 6.7 Detección de anomalías

Z-score robusto (resistente a los propios valores atípicos):

```
mediana, MAD = mediana(|x − mediana|)
z = 0.6745 · (x − mediana) / MAD
si |z| > 3.5  → "⚠️ Movimiento inusual detectado"
```

Ejemplo: `10, 12, 9, 11, 10` y luego `47` → z ≫ 3.5 → alerta de revisión (venta excepcional, error de digitación, pérdida…). Se aplica a ventas diarias y a ajustes de inventario.

### 6.8 Vencimientos

Por lote: 🔴 vence en ≤ `dias_rojo`, 🟡 ≤ `dias_amarillo`, 🟢 resto, ⚫ vencido. Las salidas usan **FEFO** (primero en vencer, primero en salir).

---

## 7. Motor de alertas

Las reglas son clases registradas en `alertas/reglas.py`; se ejecutan tras cada movimiento (solo para ese producto) y en lote cada noche (`manage.py analizar_inventario`).

| Regla | Severidad | Mensaje |
|---|---|---|
| `ReglaAgotado` | 🔴 | "X está agotado." |
| `ReglaStockCritico` | 🔴 | "X está en nivel crítico (2 de 8 mínimo)." |
| `ReglaStockBajo` | 🟡 | "X está por debajo del mínimo." |
| `ReglaRiesgoAgotamiento` | 🔴/🟡 | "X podría agotarse en ~2 días; el proveedor tarda 4." |
| `ReglaVencimiento` | 🔴/🟡 | "12 unidades de X vencen el 03/10. Priorice su venta." |
| `ReglaBajaRotacion` | 🟡 | "X no se vende hace 60 días ($120.000 inmovilizados)." |
| `ReglaExceso` | 🔵 | "X tiene inventario para 140 días." |
| `ReglaAnomalia` | ⚠️ | "Movimiento inusual en X: 47 u. (normal ~10)." |

Las alertas se **deduplican** (una abierta por producto+tipo) y tienen estados: `ABIERTA → VISTA → RESUELTA / DESCARTADA`.

---

## 8. Roles y permisos

| Acción | Administrador | Vendedor | Encargado inventario |
|---|:-:|:-:|:-:|
| Configurar negocio y usuarios | ✅ | ❌ | ❌ |
| Crear / editar productos | ✅ | ❌ | ✅ (sin precios) |
| Consultar productos y disponibilidad | ✅ | ✅ | ✅ |
| Registrar ventas | ✅ | ✅ | ❌ |
| Registrar entradas / salidas | ✅ | ❌ | ✅ |
| Conteo físico y ajustes | ✅ (aprueba) | ❌ | ✅ (registra) |
| Órdenes de compra | ✅ | ❌ | ✅ (propone) |
| Reportes, dashboard financiero | ✅ | ❌ | Parcial (sin utilidades) |

Toda acción queda en `RegistroAuditoria`: *"¿Quién modificó este inventario?"*

---

## 9. Flujos principales

### 9.1 Flujo inteligente de una venta

```
1. Vendedor registra venta ──▶ ventas.services.registrar_venta()
2. Por cada línea          ──▶ inventario.services.registrar_movimiento(SALIDA_VENTA)  [FEFO]
3. Se actualiza            ──▶ DemandaDiaria del producto
4. Se evalúan reglas       ──▶ alertas.motor.evaluar_producto()
5. Consulta histórico      ──▶ analitica: d, σd, cobertura, anomalía
6. Considera proveedor     ──▶ tiempo de entrega L
7. Calcula riesgo          ──▶ días de cobertura < L + margen
8. Genera alerta           ──▶ Alerta(RIESGO_AGOTAMIENTO)
9. Sugiere compra          ──▶ RecomendacionCompra(cantidad, explicación)
10. Empresario decide      ──▶ [Crear orden de compra] o [Descartar]
```

### 9.2 Conteo físico vs. sistema

```
Sistema: 50  →  Conteo: 47  →  Diferencia: −3  →  Motivo obligatorio ("Producto dañado")
→ Admin aprueba → Movimiento(SALIDA_AJUSTE, 3, motivo) → Regla de anomalía evalúa el ajuste
```

### 9.3 Orden de compra automática (del stock bajo al inventario)

```
Recomendación ──▶ [Generar orden] ──▶ OrdenCompra(BORRADOR) ──▶ ENVIADA (PDF / WhatsApp al proveedor)
   ──▶ CONFIRMADA ──▶ RECIBIDA (parcial/total) ──▶ Movimientos ENTRADA_COMPRA + Lotes
   ──▶ Se registra tiempo real de entrega ──▶ actualiza desempeño del proveedor
```

---

## 10. Pantallas (mobile-first)

1. **Inicio / Dashboard** — tarjetas: Inventario (productos, bajos, agotados, por vencer) · Ventas del mes (+% vs mes anterior) · Inventario inmovilizado · Alertas 🔴🟡⚠️.
2. **Productos** — lista con semáforo, buscador, filtro por categoría/estado; ficha con kárdex, gráfico de ventas, pronóstico y proveedor.
3. **Vender** — búsqueda rápida / código de barras, carrito, total.
4. **Entradas y salidas** — formulario rápido con tipo + motivo.
5. **Alertas** — bandeja agrupada por severidad con acción sugerida.
6. **Comprar** — recomendaciones → orden de compra.
7. **Conteo físico** — lista por categoría, captura de cantidades, diferencias.
8. **Proveedores** — ficha con tiempos de entrega y cumplimiento.
9. **Reportes** — selector + exportar CSV / Excel / PDF.
10. **Configuración** — giro, banderas, umbrales, usuarios.

---

## 11. Reportes

Inventario actual · Movimientos (kárdex) · Ventas · Compras · Más vendidos · Menos vendidos · Próximos a vencer · Agotados · Valor total del inventario · Utilidad estimada · Historial de ajustes. Exportación: **CSV, Excel, PDF**.

---

## 12. Hoja de ruta (fases = hitos en GitHub)

| Fase | Hito | Estado |
|---|---|:-:|
| 0 | **Fundaciones**: repo, Docker, CI, negocio + plantillas de giro, roles, aislamiento, configuración, auditoría | ✅ |
| 1 | **Registrar y Controlar**: productos, variantes, movimientos, kárdex, punto de venta | ✅ |
| 2 | **Proveedores, Compras y Vencimientos**: órdenes, PDF/WhatsApp, facturas, lotes FEFO, conteo físico | ✅ |
| 3 | **Analizar y Alertar**: demanda censurada, ABC, bandeja de alertas, anomalías en ajustes, panel, resumen por correo | ✅ |
| 4 | **Predecir y Recomendar**: Holt / Holt-Winters, temporadas, «Qué comprar» editable, precisión (MAPE) | ✅ |
| 5 | **Reportes y Móvil**: 14 reportes Excel/PDF/CSV, PWA, API REST, importación | ✅ |
| 6 | **Producción y venta**: planes y prueba gratis, página comercial, seguridad, respaldos, despliegue, manual, piloto | ✅ |

### Siguientes pasos sugeridos (después del piloto)
- Pasarela de pago (Wompi / Mercado Pago) que renueve la suscripción automáticamente.
- Facturación electrónica DIAN (vía proveedor tecnológico autorizado).
- Lectura de facturas de proveedor con OCR para las impresas (las manuscritas siguen por formulario rápido).
- Varias sedes / bodegas por negocio y traslados entre ellas.
- Notificaciones por WhatsApp Business API.

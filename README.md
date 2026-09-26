# 📦 Inventario Inteligente

Sistema de inventarios **inteligente y adaptativo** para pequeños emprendedores: tiendas, minimercados, ropa, belleza, farmacias y restaurantes.

> **Registrar → Controlar → Analizar → Predecir → Recomendar → Actuar**

Un inventario tradicional dice *"tienes 5 unidades"*.
Este dice: *"Tienes 5 unidades, vendes aproximadamente 3 por día y tu proveedor tarda 4 días en entregar. Existe riesgo de agotamiento. Se recomienda revisar el pedido."*

📐 **Diseño completo:** [`docs/DISENO.md`](docs/DISENO.md) · 🗂️ **Backlog:** [`docs/backlog.json`](docs/backlog.json)

---

## ✨ Qué hace

| Módulo | Función |
|---|---|
| Productos | SKU, categoría, marca, proveedor, precios, stock mínimo, unidad, imagen, estado y **atributos personalizados** (talla, color, tono…) |
| Entradas y salidas | Compras, devoluciones, dañados, vencidos, ajustes, **siempre con usuario y motivo** |
| Kárdex | Responde *"¿por qué tengo solo 8 unidades?"* |
| Alertas inteligentes | Agotado, crítico, bajo, **riesgo de agotamiento**, vencimiento, baja rotación, exceso, **anomalías** |
| Pronóstico | Demanda diaria (suavizado exponencial) y mensual (Holt) como rango |
| Recomendaciones | Pedido sugerido **explicado** que considera ventas, proveedor, stock de seguridad y lo que ya viene en camino |
| Proveedores | Tiempo real de entrega calculado desde las órdenes recibidas |
| Vencimientos | Lotes con salida **FEFO** y semáforo 🔴🟡🟢 |
| Conteo físico | Diferencias con motivo obligatorio y aprobación |
| Roles | Administrador · Vendedor · Encargado de inventario |
| Dashboard | *"¿Cómo está mi negocio?"* en una pantalla |
| Reportes | CSV y Excel (PDF en la fase 5) |

### 🧩 ¿Por qué "adaptativo"?

Al crear el negocio se elige su **giro** y el sistema se configura solo (`apps/core/plantillas.py`):

- **Minimercado** → vencimientos, lotes y ventas fraccionadas (kg, L).
- **Ropa** → variantes con talla/color y temporadas.
- **Belleza** → tonos + vencimientos.
- **Farmacia** → lotes, vencimientos con alertas de 30/90 días y principio activo.
- **Restaurante** → vencimientos cortos (3/7 días) y compras cada 3 días.

Agregar un nuevo tipo de negocio = agregar un diccionario. Cada bandera se puede cambiar después.

---

## 🏗️ Estructura

```
inventario-inteligente/
├── config/                  # settings, urls, wsgi
├── apps/
│   ├── core/                # Negocio, ConfiguracionNegocio, plantillas de giro, auditoría
│   ├── usuarios/            # Usuario con rol + matriz de permisos
│   ├── catalogo/            # Producto, Categoría, Marca, Unidad, AtributoPersonalizado
│   ├── proveedores/         # Proveedor, ProductoProveedor (tiempo de entrega, empaque)
│   ├── inventario/          # Movimiento (inmutable), Lote, ConteoFisico  ← ÚNICO que cambia stock
│   ├── ventas/              # Venta, DetalleVenta
│   ├── compras/             # OrdenCompra (borrador → enviada → recibida)
│   ├── analitica/           # algoritmos.py (puros) + DemandaDiaria + análisis por producto
│   ├── alertas/             # reglas.py (una clase por regla) + motor.py + comando nocturno
│   ├── recomendaciones/     # pedido sugerido explicado → órdenes de compra
│   ├── dashboard/           # "¿Cómo está mi negocio?"
│   └── reportes/            # catálogo de reportes + exportadores CSV/Excel
├── templates/ static/       # UI mobile-first
├── docs/                    # DISENO.md, backlog.json
├── scripts/                 # generar_backlog.py, configurar_github.py
├── .github/                 # CI, plantillas de issues y PR
└── docker-compose.yml
```

Cada app sigue la misma convención: `models.py` (datos) · `services.py` (reglas de negocio, escrituras) · `selectors.py` (lecturas) · `views.py` (HTTP) · `tests/`.

---

## 🚀 Empezar

### Opción A — Local (SQLite)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py cargar_demo        # minimercado con 60 días de ventas → admin / admin12345
python manage.py runserver
```

Abre http://127.0.0.1:8000 (dashboard) y http://127.0.0.1:8000/admin.

### Opción B — Docker (PostgreSQL)

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py cargar_demo
```

### Análisis nocturno

```bash
python manage.py analizar_inventario      # programar con cron: 0 2 * * *
```

### Pruebas

```bash
pytest          # 32 pruebas: algoritmos con los ejemplos del enunciado, FEFO, conteo físico, alertas…
ruff check .
```

---

## 🧠 El motor inteligente en 30 segundos

```
d   = demanda diaria (suavizado exponencial, α = 0.3, últimos 28 días)
L   = tiempo de entrega del proveedor
SS  = max(stock_mínimo, 1.65 · σd · √L)
Cobertura       = stock / d                          → "se agota en ~2 días"
Punto de reorden = d · L + SS
Pedido sugerido = ⌈d · (L + H) + SS − stock − en_tránsito⌉   (redondeado al empaque)
Anomalía        = |0.6745 · (x − mediana) / MAD| > 3.5
```

Ejemplo del enunciado → Café: stock 8, 35/semana, SS 10 ⇒ **pedir 37** ✅ (ver `apps/analitica/tests/test_algoritmos.py`).

---

## 🗺️ Hoja de ruta

| Fase | Hito |
|---|---|
| 0 | Fundaciones |
| 1 | MVP Registrar y Controlar |
| 2 | Proveedores, Compras y Vencimientos |
| 3 | Analizar y Alertar |
| 4 | Predecir y Recomendar |
| 5 | Reportes y Móvil |
| 6 | Producción |

Las tareas están como **issues** en GitHub, agrupadas por hito, con etiquetas `modulo:*`, `prioridad:*` y `base-implementada` (el modelo/servicio ya existe y falta la interfaz o ampliarlo).

## 🤝 Flujo de trabajo

1. Toma un issue del tablero → muévelo a *In progress*.
2. Rama: `feat/<n°-issue>-descripcion-corta`.
3. PR que diga `Cierra #<n°>`; el CI debe pasar.
4. **Regla de oro:** el stock solo cambia vía `inventario.services.registrar_movimiento()`.

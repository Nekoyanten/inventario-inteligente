# 📦 Inventario Inteligente

Sistema de inventarios **inteligente y adaptativo** para pequeños emprendedores: tiendas, minimercados, ropa, belleza, droguerías y restaurantes. Listo para venderse como servicio (SaaS).

> **Registrar → Controlar → Analizar → Predecir → Recomendar → Actuar**

Un inventario tradicional dice *"tienes 5 unidades"*.
Este dice: *"Tienes 5 unidades, vendes aproximadamente 3 por día y tu proveedor tarda 4 días. Existe riesgo de agotamiento. Se recomienda pedir 22."*

📐 [Diseño](docs/DISENO.md) · 🩺 [Diagnóstico](docs/DIAGNOSTICO.md) · ▶️ [Puesta en marcha](docs/PUESTA_EN_MARCHA.md) · 🚀 [Despliegue](docs/DESPLIEGUE.md) · 📖 [Manual](docs/MANUAL.md) · 🧪 [Piloto](docs/PILOTO.md) · 🤖 [Piloto simulado](docs/PILOTO_SIMULADO.md) · 🗂️ [Backlog](docs/backlog.json)

---

## ✨ Funciones

| Área | Qué incluye |
|---|---|
| **Adaptativo** | Plantillas por tipo de negocio; vencimientos, lotes, variantes (talla × color), fracciones y temporadas activables; atributos personalizados por categoría |
| **Productos** | Semáforo de stock, búsqueda por nombre/código/marca, variantes, importación desde Excel, margen en vivo |
| **Punto de venta** | Buscador, lector de código de barras (teclado o cámara), cambio, medios de pago, comprobante, anulación con motivo |
| **Inventario** | Entradas y salidas con motivo obligatorio, kárdex, lotes FEFO, vencimientos, conteo físico con aprobación |
| **Compras** | «Qué comprar» con explicación, órdenes por proveedor, PDF y WhatsApp, recepción parcial, facturas sin orden |
| **Proveedores** | Entrega prometida vs. real, % de cumplimiento, productos y precios pactados |
| **Inteligencia** | Demanda con suavizado exponencial y corrección de demanda censurada, Holt / Holt-Winters, temporadas, punto de reorden, stock de seguridad, ABC, rotación, anomalías (ventas y ajustes), precisión de pronósticos (MAPE) |
| **Alertas** | Agotado, crítico, bajo, riesgo de agotamiento, vencimiento, baja rotación, exceso, inusual; bandeja con acciones y resumen diario por correo |
| **Panel** | Ventas vs. mes anterior, utilidad, ticket promedio, inventario inmovilizado, gráfico de 30 días, más vendidos |
| **Reportes** | 14 reportes en pantalla, Excel, PDF y CSV |
| **Usuarios** | Administrador, vendedor y encargado de inventario; auditoría de todo |
| **Plataforma** | App instalable (PWA) con modo sin conexión, API REST con token y documentación OpenAPI |
| **SaaS** | Registro con prueba gratis, planes con límites, página comercial, términos, privacidad (Ley 1581), exportación de datos, comentarios |
| **Producción** | Docker, Render blueprint (web, PostgreSQL, Redis, tareas), imágenes en la nube (S3/R2) optimizadas a WebP, Sentry, `/salud/`, WhiteNoise, HTTPS/HSTS, límite de intentos de ingreso, respaldos, `check --deploy` en CI |
| **Operación** | Panel de la plataforma con salud, lista de chequeo de producción, métricas del piloto por negocio y registro de tareas nocturnas; lista de arranque para cada negocio |

---

## 🚀 Empezar

```bash
python -m venv .venv
source .venv/bin/activate            # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # deja DEBUG=True para desarrollo
python manage.py migrate
python manage.py cargar_demo         # minimercado con 60 días de ventas → admin / admin12345
python manage.py runserver
```

- http://127.0.0.1:8000 → página comercial (sin sesión) o panel (con sesión)
- http://127.0.0.1:8000/registro/ → crear un negocio nuevo
- http://127.0.0.1:8000/api/docs/ → documentación de la API

Con PostgreSQL local: `docker compose up -d db` y en `.env` `DATABASE_URL=postgres://inventario:inventario@localhost:5432/inventario`.

### Tareas programadas

```bash
python manage.py analizar_inventario   # alertas, recomendaciones y pronósticos (cada noche)
python manage.py enviar_resumen        # correo con alertas críticas (cada mañana)
python manage.py reconstruir_demanda   # recalcula la demanda desde las ventas
python manage.py probar_correo tu@correo.com   # verifica la configuración de correo
```

### Pruebas

```bash
pytest                                  # 164 pruebas, 93 % de cobertura
ruff check .
DATABASE_URL=postgres://... pytest      # también contra PostgreSQL (como en CI)
```

---

## 🏗️ Estructura

```
config/                 settings (dev/prod por variables de entorno), urls
apps/
  core/                 negocio, plantillas de giro, suscripciones y límites, auditoría,
                        aislamiento multi-negocio, PWA, páginas públicas, registro
  usuarios/             roles, matriz de permisos, ingreso con límite de intentos
  catalogo/             productos, variantes, categorías, marcas, atributos
  proveedores/          proveedores y desempeño
  inventario/           movimientos (ÚNICO lugar que cambia stock), lotes, conteos, kárdex
  ventas/               punto de venta, anulaciones
  compras/              órdenes, recepción, facturas directas, PDF, WhatsApp
  analitica/            algoritmos puros + demanda diaria, temporadas, pronósticos
  alertas/              reglas, motor, bandeja, comandos nocturnos
  recomendaciones/      pedido sugerido explicado → órdenes
  dashboard/            panel del administrador y del vendedor
  reportes/             catálogo de reportes, exportadores, importación
  api/                  API REST v1
templates/ static/      interfaz mobile-first con modo oscuro
docs/                   diseño, despliegue, manual, piloto, backlog
scripts/                arranque, respaldos, backlog de GitHub
```

Convención por app: `models.py` · `services.py` (escrituras y reglas) · `selectors.py` (lecturas) · `views.py` · `tests/`.

**Reglas de oro**
1. El stock solo cambia vía `inventario.services.registrar_movimiento()` (transacción + bloqueo de fila).
2. Toda consulta desde una vista pasa por `del_negocio()` / `NegocioRequeridoMixin` (un negocio nunca ve datos de otro).
3. El sistema sugiere; el empresario decide. Las alertas detectan, no acusan.

---

## 🤝 Flujo de trabajo

1. Toma un issue del tablero y muévelo a *In progress*.
2. Rama `feat/<n°>-descripcion`, PR con `Cierra #<n°>`; el CI (ruff, migraciones, pytest en PostgreSQL, `check --deploy`) debe pasar.

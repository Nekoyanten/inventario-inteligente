# Diagnóstico del proyecto

Fecha de la revisión: 27/09/2026 · Versión revisada: rama con las fases 0 a 6 + corrección del CI + auditoría.

## 1. Estado general

| Área | Estado | Resumen |
|---|:-:|---|
| Funcionalidad | 🟢 | Los 17 puntos del enunciado están implementados (sección 3). |
| Calidad del código | 🟢 | 139 pruebas, 90 % de cobertura, lint limpio y migraciones al día. |
| Seguridad | 🟢 | Sin vulnerabilidades conocidas en dependencias y sin hallazgos medios o altos en el análisis estático. Se corrigieron 2 redirecciones abiertas. |
| Rendimiento | 🟢 | Con 5.000 productos todas las pantallas responden en menos de 1,2 s (tras las correcciones). |
| Listo para producción | 🟡 | Faltan 3 bloqueantes técnicos (sección 5). |
| Listo para vender | 🔴 | No se ha probado con usuarios reales, el cobro es manual y falta la parte legal y comercial. |

## 2. Qué se verificó

- **Pruebas:** 139 pruebas en SQLite y en PostgreSQL 16, con las mismas variables del CI (`DEBUG=False`).
- **Cobertura:** 90 % (4.776 líneas). Lo menos cubierto: vistas de configuración (48 %) y de catálogo (65 %).
- **Dependencias:** `pip-audit` no encontró vulnerabilidades conocidas.
- **Análisis estático:** `bandit` no encontró hallazgos de severidad media o alta. Revisión manual de redirecciones, escape de HTML, CSRF, SQL crudo, subida de archivos y aislamiento entre negocios.
- **Producción:** `check --deploy` sin advertencias; archivos estáticos con hash y compresión.
- **Recorrido en el navegador:** 33 pantallas × 3 roles en celular, sin errores de JavaScript ni desbordes horizontales.
- **Carga:** un negocio con 5.000 productos, 128 mil días de demanda, 3.000 ventas y 3.000 lotes en PostgreSQL.

### Tiempos con 5.000 productos

| Pantalla | Tiempo | Consultas |
|---|--:|--:|
| Panel principal | 0,34 s | 22 |
| Lista de productos | 0,04 s | 9 |
| Ficha de producto | 0,05 s | 26 |
| Búsqueda del punto de venta | 0,02 s | 5 (antes 45) |
| Vencimientos | 0,63 s | 7 |
| Reporte Rotación y ABC | 0,83 s | 11 (antes 41 s y ~45.000 consultas) |
| Excel del inventario | 1,15 s | 6 (antes 16 s) |
| Análisis nocturno | ~2,3 min por negocio de 5.000 productos | ~24 por producto |

## 3. Cumplimiento del enunciado

| # | Requisito | Estado |
|--:|---|:-:|
| 1 | Gestión de productos (SKU, categoría, marca, proveedor, precios, stock, mínimo, unidad, imagen, estado) | 🟢 La imagen funciona en local; en producción depende del bloqueante B1 |
| 2 | Entradas y salidas con producto, cantidad, fecha, tipo, usuario y motivo | 🟢 |
| 3 | Alertas inteligentes (bajo, crítico, agotado, vencimiento, baja rotación, exceso, variaciones) | 🟢 |
| 4 | Pronóstico de demanda | 🟡 Implementado; su precisión solo se puede medir con ventas reales |
| 5 | Recomendaciones de compra (ej. café → 37) | 🟢 Probado con el ejemplo exacto |
| 6 | Control de proveedores y tiempo de entrega | 🟢 |
| 7 | Control de vencimientos 🔴🟡🟢 | 🟢 |
| 8 | Análisis de rotación | 🟢 |
| 9 | Panel "¿Cómo está mi negocio?" | 🟢 |
| 10 | Detección de anomalías (47 frente a ~10) | 🟢 Ventas y ajustes |
| 11 | Roles: administrador, vendedor, encargado | 🟢 Matriz probada URL por URL |
| 12 | Inventario físico vs. sistema con motivo | 🟢 |
| 13 | Reportes en Excel, CSV y PDF | 🟢 14 reportes |
| 14 | Inteligencia que relaciona stock, ventas, tendencia, proveedor y temporada | 🟢 |
| 15 | Para pequeños empresarios: simple, barato, celular, escalable | 🟢 App instalable; escala verificada a 5.000 productos |
| 16 | Arquitectura en módulos | 🟢 12 módulos + API |
| 17 | Flujo inteligente de 10 pasos | 🟢 |

## 4. Corregido en esta revisión

1. **CI en rojo:** con `DEBUG=False` las pruebas buscaban estáticos procesados (60 pruebas fallaban).
2. **Reporte Rotación y ABC:** tardaba 41 s con 5.000 productos y en producción habría superado el tiempo límite del servidor (60 s).
3. **Exportar a Excel:** tardaba 16 s por un recorrido innecesario de la hoja en cada fila.
4. **Redirecciones abiertas** en comentarios y alertas: se podía redirigir a un sitio externo.
5. **Sin límite de tamaño** para imágenes e importaciones (ahora 5 MB).
6. **Posible bloqueo cruzado** entre dos cajas que venden los mismos productos al mismo tiempo.

## 5. Pendientes, por prioridad

### Bloqueantes para producción

| ID | Problema | Impacto | Solución |
|---|---|---|---|
| B1 | Las imágenes de productos se guardan en el disco del servidor | En Render o Docker el disco se borra en cada despliegue y con `DEBUG=False` las imágenes no se sirven: se pierden | Almacenamiento en la nube (Cloudflare R2, S3 o Cloudinary) con `django-storages` |
| B2 | Correo sin configurar | No funcionan la recuperación de contraseña ni el resumen diario | Configurar `EMAIL_URL` (Gmail con contraseña de aplicación, Brevo, etc.) |
| B3 | Sin monitoreo de errores | Si algo falla con un cliente, no te enteras | Sentry (tiene plan gratuito) + alerta de caída en `/salud/` |

### Importantes (antes de cobrar)

| ID | Problema | Solución |
|---|---|---|
| I1 | Cobro manual (WhatsApp → activar en el admin) | Pasarela colombiana (Wompi / Mercado Pago) con renovación automática |
| I2 | Pronósticos no validados con datos reales | Medirlos en el piloto con el reporte de precisión |
| I3 | El punto de venta necesita internet | Cola de ventas sin conexión que se sincroniza al volver la señal |
| I4 | El límite de intentos de ingreso vive en la memoria de cada proceso | Redis (`CACHE_URL`) al tener más de un servidor |
| I5 | Pruebas débiles en configuración (48 %) y catálogo (65 %) | Subir a más del 80 % |
| I6 | Términos y privacidad sin revisión legal; empresa sin formalizar | Abogado + RUT/NIT |

### Mejoras posteriores (decidir con los datos del piloto)

- Facturación electrónica DIAN (vía proveedor tecnológico autorizado).
- Cargar compras desde facturas con OCR (las facturas impresas; las manuscritas siguen por formulario rápido).
- Varias sedes o bodegas por negocio, con traslados.
- Notificaciones por WhatsApp.
- Análisis nocturno en paralelo (Celery) cuando haya muchos clientes: hoy toma ~2,3 min por negocio grande.

## 6. Siguiente fase recomendada: Fase 7 · Salida a producción y piloto

**Objetivo:** tener el sistema en internet, con los 5 negocios usándolo a diario, y datos para decidir precios y prioridades.

| Semana | Trabajo |
|---|---|
| 1 | Resolver B1, B2 y B3; desplegar en Render con dominio propio; conteo inicial e importación de productos de los 5 negocios |
| 2–4 | Piloto (`docs/PILOTO.md`); corregir lo que reporten; medir uso, precisión y diferencias de inventario |
| 5 | Entrevista de cierre: ¿pagarían?, ¿cuánto?, ¿qué falta? → definir la Fase 8 |

**En paralelo (no técnico):** formalizar la empresa, revisión legal y definición de precios.

**Criterios para cerrar la Fase 7:**
- Los 5 negocios registran sus ventas en el sistema durante 3 semanas seguidas.
- Cero pérdida de datos y ningún error sin atender más de 24 horas.
- Al menos 3 de 5 dicen que pagarían.
- Precisión de pronóstico medida (meta inicial: error promedio ≤ 30 % en los productos de clase A).

**Fase 8 (tentativa, según el piloto):** cobro automático (I1), punto de venta sin conexión (I3) y lo que más pidan los negocios. Facturación DIAN solo si los clientes la exigen.

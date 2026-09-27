# Despliegue en producción

Guía para publicar Inventario Inteligente y venderlo como servicio (SaaS).

## Opción A: Render (la más sencilla)

1. Sube el repositorio a GitHub.
2. En Render: **New → Blueprint** y elige el repositorio. `render.yaml` crea:
   - la base de datos PostgreSQL,
   - el servicio web (Docker, con `/salud/` como verificación),
   - dos tareas programadas: análisis nocturno (2:00 a. m.) y resumen por correo (7:00 a. m.).
3. Completa las variables marcadas como `sync: false`: `EMAIL_URL`, `URL_SITIO`, `CONTACTO_VENTAS`.
4. Crea tu usuario administrador desde la consola del servicio:
   `python manage.py createsuperuser`
5. Con dominio propio: agrégalo en Render y actualiza `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.

> Revisa los planes y precios vigentes de Render. Para empezar con pocos clientes basta con los planes pequeños.

## Opción B: VPS propio (Ubuntu + Docker)

```bash
git clone https://github.com/Nekoyanten/inventario-inteligente.git && cd inventario-inteligente
cp .env.example .env   # completa la sección de Producción: SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL…
docker build -t inventario .
docker run -d --name inventario --env-file .env -p 8000:8000 --restart unless-stopped inventario
```

Delante del contenedor pon un proxy con HTTPS (Caddy o Nginx + Let's Encrypt). Con Caddy basta con:

```
inventario.tudominio.com {
    reverse_proxy localhost:8000
}
```

Tareas programadas (crontab del servidor):

```
0 2 * * *  docker exec inventario python manage.py analizar_inventario
0 7 * * *  docker exec inventario python manage.py enviar_resumen
30 3 * * * DATABASE_URL=... /ruta/inventario-inteligente/scripts/respaldo.sh /respaldos
```

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|:-:|---|
| `SECRET_KEY` | ✅ | Clave larga y aleatoria. Sin ella la app no arranca en producción. |
| `DATABASE_URL` | ✅ | `postgres://usuario:clave@host:5432/base` |
| `ALLOWED_HOSTS` | ✅ | Dominios permitidos, separados por coma. |
| `CSRF_TRUSTED_ORIGINS` | ✅ | `https://tu-dominio` |
| `ADMIN_URL` | Recomendada | Ruta secreta del admin de Django (ej. `panel-8f3a/`). |
| `EMAIL_URL` | Recomendada | SMTP para resúmenes y recuperación de contraseña. |
| `URL_SITIO` | Recomendada | URL pública, usada en los correos. |
| `CACHE_URL` | Con varios servidores | Redis, para que el límite de intentos de ingreso sea compartido. |
| `DIAS_PRUEBA`, `PRECIO_*`, `CONTACTO_VENTAS`, `EMPRESA_*` | Comerciales | Prueba gratis, precios, WhatsApp de ventas y datos legales de tu empresa. |

## Seguridad incluida

- HTTPS obligatorio, cookies seguras, HSTS, `X-Frame-Options: DENY`, `nosniff`.
- `python manage.py check --deploy` sin advertencias (se valida en CI).
- Límite de 5 intentos de ingreso por usuario e IP (bloqueo de 15 minutos).
- Aislamiento de datos entre negocios en todas las consultas (con pruebas).
- Permisos por rol en web y API; matriz de permisos con pruebas.
- Movimientos de inventario inmutables y bitácora de auditoría.
- Contraseñas con los validadores de Django; recuperación por correo.

## Copias de seguridad

`scripts/respaldo.sh` hace `pg_dump` comprimido, verifica el archivo y borra los de más de 30 días.

**Prueba de restauración (hazla una vez al mes):**

```bash
createdb inventario_prueba
gunzip -c respaldos/respaldo-AAAAMMDD-HHMM.sql.gz | psql postgres://.../inventario_prueba
DATABASE_URL=postgres://.../inventario_prueba python manage.py check
```

Guarda una copia fuera del servidor (otro proveedor o almacenamiento en la nube).

Cada cliente puede además descargar todos sus datos desde **Ajustes → Descargar todos mis datos**.

## Cobrar a los clientes

Los planes (Gratis, Emprendedor, Negocio) y sus límites están en `settings.PLANES`. Hoy la activación es manual:

1. El cliente elige un plan en **Mi plan** y te escribe por WhatsApp (`CONTACTO_VENTAS`).
2. Recibes el pago (transferencia, Nequi, pasarela).
3. En el admin → **Suscripciones**: eliges el plan y la fecha `pagado_hasta`.

Siguiente paso sugerido: integrar una pasarela colombiana (por ejemplo Wompi o Mercado Pago) con un webhook que actualice `pagado_hasta` automáticamente.

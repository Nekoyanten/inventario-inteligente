# Puesta en marcha (Fase 7)

Guía paso a paso para publicar Inventario Inteligente en internet y dejarlo listo para el piloto. Pensada para hacerse en una tarde.

> Los proveedores mencionados ofrecen planes gratuitos o de bajo costo, pero sus condiciones cambian: revisa los límites y precios vigentes antes de elegir.

## Qué vas a crear

| Servicio | Para qué | Variable(s) |
|---|---|---|
| Cloudflare R2 (u otro S3) | Guardar las imágenes de productos | `AWS_*` |
| Gmail o Brevo (SMTP) | Bienvenida, recuperar contraseña, resumen diario | `EMAIL_URL`, `DEFAULT_FROM_EMAIL` |
| Sentry | Enterarte cuando algo falla | `SENTRY_DSN` |
| Render | Servidor, base de datos, Redis y tareas nocturnas | `render.yaml` |
| Dominio propio | Confianza de los clientes | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `URL_SITIO` |
| UptimeRobot / Better Stack | Aviso si el sitio se cae | monitor sobre `/salud/` |

---

## 1. Imágenes: Cloudflare R2

1. En Cloudflare → **R2** → *Create bucket* → nombre `inventario-imagenes`. Déjalo **privado** (el sistema genera enlaces firmados).
2. **R2 → Manage API tokens → Create API token** con permiso *Object Read & Write* solo para ese bucket.
3. Anota:
   - `AWS_STORAGE_BUCKET_NAME=inventario-imagenes`
   - `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` (del token)
   - `AWS_S3_ENDPOINT_URL=https://<id-de-cuenta>.r2.cloudflarestorage.com`

Las fotos se reducen a 800 px y se guardan en WebP en `productos/<negocio>/`. Una foto de celular de 4 MB queda en unos 50–100 KB.

## 2. Correo

**Opción A – Gmail (para empezar):**
1. Activa la verificación en dos pasos en la cuenta.
2. Crea una *contraseña de aplicación* (Cuenta de Google → Seguridad → Contraseñas de aplicaciones).
3. `EMAIL_URL=smtp+tls://tucorreo%40gmail.com:CONTRASEÑA_DE_APLICACION@smtp.gmail.com:587`
   (la `@` del usuario se escribe `%40`; los espacios de la contraseña se quitan).
4. `DEFAULT_FROM_EMAIL=Inventario Inteligente <tucorreo@gmail.com>`

**Opción B – Brevo u otro proveedor transaccional (recomendado al crecer):** usa sus datos SMTP en el mismo formato. Con dominio propio, configura SPF y DKIM para no caer en spam.

## 3. Sentry

1. sentry.io → crea un proyecto de tipo **Django**.
2. Copia el DSN → `SENTRY_DSN=https://...ingest.sentry.io/...`
3. En *Alerts*, deja activa la alerta por correo para errores nuevos.

El sistema no envía datos personales de tus clientes a Sentry (`send_default_pii=False`).

## 4. Dominio

Compra el dominio (ej. `tuinventario.co`). Lo conectarás en el paso 7.

## 5. Desplegar en Render

1. Render → **New → Blueprint** → elige el repositorio `inventario-inteligente`.
2. El blueprint crea: base de datos PostgreSQL, Redis (`inventario-cache`), el servicio web y dos tareas programadas.
3. Render te pedirá las variables marcadas `sync: false`. Pega las de los pasos 1 a 3 y además:
   - `URL_SITIO=https://tu-dominio.co`
   - `CONTACTO_VENTAS=57300XXXXXXX` (tu WhatsApp)
   - `EMPRESA_NOMBRE`, `EMPRESA_NIT`, `EMPRESA_CORREO`
4. Espera a que el servicio web quede *Live*. Abre `https://<servicio>.onrender.com/salud/` → debe responder `{"estado": "ok", ...}`.

## 6. Crear tu usuario de dueño de la plataforma

En Render → servicio web → **Shell**:

```bash
python manage.py createsuperuser
python manage.py probar_correo tucorreo@gmail.com
```

Si el correo de prueba llega, el paso 2 quedó bien. Si no, revisa `EMAIL_URL`.

## 7. Conectar el dominio

1. Render → servicio web → *Settings → Custom Domains* → agrega `tu-dominio.co` y `www.tu-dominio.co`.
2. Crea en tu proveedor de dominio los registros DNS que Render indique. El certificado HTTPS se genera solo.
3. Actualiza las variables:
   - `ALLOWED_HOSTS=tu-dominio.co,www.tu-dominio.co,.onrender.com`
   - `CSRF_TRUSTED_ORIGINS=https://tu-dominio.co,https://www.tu-dominio.co`

## 8. Verificar

1. Ingresa con tu superusuario y abre **Plataforma** (enlace arriba a la derecha).
2. En *Puesta en producción* todo debe estar en ✅. Lo que tenga ⚠️ te dice qué variable falta.
3. Crea un negocio de prueba desde la página principal, sube un producto con foto, haz una venta y revisa que:
   - llegó el correo de bienvenida,
   - la foto se ve (y está en el bucket de R2),
   - en Sentry no aparecen errores.
4. Al día siguiente, en *Tareas programadas* debe aparecer el análisis nocturno en 🟢.
5. Crea un monitor en UptimeRobot o Better Stack que revise `https://tu-dominio.co/salud/` cada 5 minutos y te avise por correo o WhatsApp.

## 9. Empezar el piloto

Sigue `docs/PILOTO.md`. Cada lunes revisa **Plataforma → Negocios del piloto**:

- **Días con ventas** (verde = 15 o más de 21): ¿lo están usando?
- **Arranque**: ¿completaron los 6 pasos?
- **Comentarios**: atiéndelos en menos de 24 horas.

Descarga el CSV de métricas al final de cada semana para el informe del piloto.

"""Configuración de Django para Inventario Inteligente.

Las variables sensibles se leen de entorno (.env). Ver .env.example.
"""

import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env("DEBUG")
EN_PRUEBAS = "pytest" in sys.modules or "test" in sys.argv
SECRET_KEY = env("SECRET_KEY", default="dev-inseguro-cambiar-en-produccion" if DEBUG or EN_PRUEBAS else None)
if not SECRET_KEY:
    raise RuntimeError("Define SECRET_KEY en el entorno (obligatorio con DEBUG=False).")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
ADMIN_URL = env("ADMIN_URL", default="admin/")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.core",
    "apps.usuarios",
    "apps.catalogo",
    "apps.proveedores",
    "apps.inventario",
    "apps.ventas",
    "apps.clientes",
    "apps.nocturno",
    "apps.compras",
    "apps.analitica",
    "apps.alertas",
    "apps.recomendaciones",
    "apps.dashboard",
    "apps.reportes",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.NegocioActualMiddleware",
    "apps.core.middleware.SuscripcionMiddleware",
    "apps.core.middleware.ModulosMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.negocio",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL en producción (DATABASE_URL=postgres://...), SQLite por defecto en desarrollo.
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

STATIC_URL = "static/"
# Archivos subidos (imágenes de productos): en la nube si hay bucket S3 compatible (Cloudflare R2, AWS S3,
# Backblaze B2, DigitalOcean Spaces…); si no, en el disco local (solo sirve en un servidor con disco persistente).
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
ALMACENAMIENTO_NUBE = bool(AWS_STORAGE_BUCKET_NAME)
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {
        "bucket_name": AWS_STORAGE_BUCKET_NAME,
        "access_key": env("AWS_ACCESS_KEY_ID", default=""),
        "secret_key": env("AWS_SECRET_ACCESS_KEY", default=""),
        "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),  # R2: https://<cuenta>.r2.cloudflarestorage.com
        "region_name": env("AWS_S3_REGION_NAME", default="auto"),
        "custom_domain": env("AWS_S3_CUSTOM_DOMAIN", default=None),  # dominio público del bucket (opcional)
        "querystring_auth": not env("AWS_S3_CUSTOM_DOMAIN", default=None),  # sin dominio público: URLs firmadas
        "querystring_expire": 60 * 60 * 24,
        "file_overwrite": False,
        "signature_version": "s3v4",  # obligatorio en Cloudflare R2
        "default_acl": None,
        "object_parameters": {"CacheControl": "public, max-age=2592000"},
    }} if ALMACENAMIENTO_NUBE else {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # En producción: archivos con hash y comprimidos (requiere collectstatic). En desarrollo y pruebas: normales.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    if not (DEBUG or EN_PRUEBAS) else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Archivos subidos (imágenes de productos, importación de Excel)
TAMANO_MAX_ARCHIVO_MB = 5
IMAGEN_LADO_MAX = 800  # px; las imágenes se reducen y convierten a WebP al subirlas
SERVIR_MEDIA_LOCAL = env.bool("SERVIR_MEDIA_LOCAL", default=False)  # VPS con disco persistente y sin bucket
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:inicio"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Correo (resumen diario de alertas). Sin EMAIL_URL los correos se imprimen en consola.
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Inventario Inteligente <no-responder@localhost>")
URL_SITIO = env("URL_SITIO", default="http://localhost:8000")
EMAIL_TIMEOUT = 10  # segundos: un servidor de correo caído no debe congelar la aplicación
CORREO_CONFIGURADO = not EMAIL_CONFIG.get("EMAIL_BACKEND", "").endswith("console.EmailBackend")

# Seguridad (producción)
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 horas
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # el POS lee el token CSRF desde JavaScript
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not EN_PRUEBAS)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False  # decisión deliberada: la lista de precarga es difícil de revertir
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Límite de intentos de ingreso (por usuario + IP)
INTENTOS_LOGIN_MAX = 5
BLOQUEO_LOGIN_MINUTOS = 15

CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["consola"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"django.security": {"handlers": ["consola"], "level": "WARNING", "propagate": False}},
}

# Monitoreo de errores (Sentry). Sin SENTRY_DSN no se envía nada.
SENTRY_DSN = env("SENTRY_DSN", default="")
VERSION_APP = env("RENDER_GIT_COMMIT", default=env("VERSION_APP", default="dev"))[:12]
if SENTRY_DSN and not EN_PRUEBAS:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENTORNO", default="produccion"),
        release=VERSION_APP,
        traces_sample_rate=env.float("SENTRY_TRAZAS", default=0.05),  # 5 % de peticiones para medir lentitud
        send_default_pii=False,  # no enviar datos personales de los clientes
    )

# API REST
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "600/min"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Inventario Inteligente API",
    "DESCRIPTION": "Productos, movimientos, ventas y alertas. Autenticación: `Authorization: Token <token>`.",
    "VERSION": "1.0.0",
}

# Planes comerciales. Precios en COP/mes: AJÚSTALOS a tu estrategia comercial.
DIAS_PRUEBA = env.int("DIAS_PRUEBA", default=14)
PLANES = {
    "GRATIS": {"nombre": "Gratis", "precio": 0, "productos": 50, "usuarios": 1, "api": False, "reportes_pdf": False},
    "EMPRENDEDOR": {"nombre": "Emprendedor", "precio": env.int("PRECIO_EMPRENDEDOR", default=39000),
                    "productos": 500, "usuarios": 3, "api": False, "reportes_pdf": True},
    "NEGOCIO": {"nombre": "Negocio", "precio": env.int("PRECIO_NEGOCIO", default=79000),
                "productos": 5000, "usuarios": 10, "api": True, "reportes_pdf": True},
}
CONTACTO_VENTAS = env("CONTACTO_VENTAS", default="")  # WhatsApp comercial, ej. 573001234567

# Datos de la empresa que presta el servicio (aparecen en términos, privacidad y correos)
EMPRESA = {
    "nombre": env("EMPRESA_NOMBRE", default="Inventario Inteligente"),
    "nit": env("EMPRESA_NIT", default=""),
    "correo": env("EMPRESA_CORREO", default="soporte@example.com"),
    "ciudad": env("EMPRESA_CIUDAD", default="San Juan de Pasto, Colombia"),
}

# Parámetros por defecto del motor inteligente (se pueden sobreescribir por negocio).
INVENTARIO_INTELIGENTE = {
    "ALFA_SUAVIZADO": 0.3,
    "DIAS_HISTORIA": 28,
    "Z_NIVEL_SERVICIO": 1.65,  # 95 %
    "UMBRAL_ANOMALIA": 3.5,
}

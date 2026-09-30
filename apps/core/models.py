"""Núcleo: negocio, configuración adaptativa (plantillas de giro) y auditoría."""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from .imagenes import ruta_logo


class ModeloBase(models.Model):
    """Campos de tiempo comunes a todas las entidades."""

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Giro(models.TextChoices):
    MINIMERCADO = "MINIMERCADO", "Tienda / minimercado"
    ROPA = "ROPA", "Ropa y calzado"
    BELLEZA = "BELLEZA", "Belleza y cosméticos"
    FARMACIA = "FARMACIA", "Farmacia / droguería"
    RESTAURANTE = "RESTAURANTE", "Restaurante / comidas"
    BAR = "BAR", "Bar / gastrobar"
    DISCOTECA = "DISCOTECA", "Discoteca"
    BAR_DISCOTECA = "BAR_DISCOTECA", "Bar-discoteca"
    VAPE = "VAPE", "Vapeadores y accesorios"
    GENERICO = "GENERICO", "Otro (genérico)"


class Negocio(ModeloBase):
    nombre = models.CharField(max_length=150)
    nit = models.CharField("NIT / documento", max_length=30, blank=True)
    giro = models.CharField(max_length=20, choices=Giro.choices, default=Giro.GENERICO)
    moneda = models.CharField(max_length=3, default="COP")
    telefono = models.CharField(max_length=30, blank=True)
    direccion = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.nombre


class ConfiguracionNegocio(ModeloBase):
    """Banderas que hacen al sistema adaptativo. Se precargan desde la plantilla de giro."""

    negocio = models.OneToOneField(Negocio, on_delete=models.CASCADE, related_name="config")

    # Funciones activables
    usa_vencimientos = models.BooleanField(default=False)
    usa_lotes = models.BooleanField(default=False)
    usa_variantes = models.BooleanField(default=False, help_text="Talla, color, tono…")
    permite_fracciones = models.BooleanField(default=False, help_text="Vender 0,5 kg, 1,25 L…")
    usa_temporadas = models.BooleanField(default=False)

    # Umbrales (semáforo)
    dias_vencimiento_rojo = models.PositiveIntegerField(default=7)
    dias_vencimiento_amarillo = models.PositiveIntegerField(default=30)
    dias_sin_movimiento = models.PositiveIntegerField(default=45, help_text="Para baja rotación")
    dias_exceso = models.PositiveIntegerField(default=90, help_text="Cobertura que se considera exceso")
    horizonte_compra_dias = models.PositiveIntegerField(default=7, help_text="Días que debe cubrir un pedido")
    tiempo_entrega_defecto = models.PositiveIntegerField(default=3, help_text="Si el producto no tiene proveedor")
    horizonte_automatico = models.BooleanField(
        default=True, help_text="Ajustar el horizonte al ciclo real de compra de cada proveedor (si compras cada 14 días, "
                                "el pedido cubre 14 días)")

    # Punto de venta
    permite_venta_sin_stock = models.BooleanField(
        default=True, help_text="Si el sistema dice 0 pero el producto está en la estantería, se vende igual y queda un "
                                "ajuste para revisar")

    # Clientes y fidelización
    fidelizacion_activa = models.BooleanField(default=True, help_text="Los clientes registrados acumulan puntos")
    pesos_por_punto = models.PositiveIntegerField(default=1000, help_text="Cada cuántos pesos de compra se gana 1 punto")
    valor_punto = models.PositiveIntegerField(default=10, help_text="Cuántos pesos de descuento vale 1 punto al canjear")
    puntos_minimos_canje = models.PositiveIntegerField(default=100)
    nivel_frecuente_compras = models.PositiveIntegerField(
        default=4, help_text="Compras en los últimos 90 días para ser cliente frecuente")
    nivel_vip_monto = models.PositiveIntegerField(
        default=500000, help_text="Compras (en pesos) en los últimos 90 días para ser VIP")
    encuesta_satisfaccion = models.BooleanField(default=True, help_text="Mostrar la encuesta en el comprobante")

    # Apariencia (cada negocio con su color, su modo y su logo)
    class Tema(models.TextChoices):
        AUTO = "AUTO", "Automático (como el celular)"
        CLARO = "CLARO", "Claro"
        OSCURO = "OSCURO", "Oscuro"

    color_principal = models.CharField(max_length=7, default="#1f7a4d", validators=[RegexValidator(
        r"^#[0-9a-fA-F]{6}$", "Usa un color como #1f7a4d.")], help_text="Botones, menú y enlaces")
    tema = models.CharField(max_length=6, choices=Tema.choices, default=Tema.AUTO)
    letra_grande = models.BooleanField(default=False, help_text="Letra más grande en toda la aplicación")
    logo = models.ImageField(upload_to=ruta_logo, null=True, blank=True,
                             help_text="Aparece en la barra de arriba y en el comprobante")

    # Alertas silenciadas: [{"tipo": "BAJA_ROTACION", "categoria": 3 | null}]
    alertas_silenciadas = models.JSONField(default=list, blank=True)

    # Motor inteligente
    alfa_suavizado = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.3,
        help_text="Qué tanto pesan las ventas recientes (0.1 = estable, 0.6 = reacciona rápido)",
    )

    # Notificaciones
    resumen_por_correo = models.BooleanField(
        default=True, help_text="Enviar cada mañana las alertas críticas a los administradores"
    )

    def __str__(self):
        return f"Configuración de {self.negocio}"


class RegistroAuditoria(models.Model):
    """¿Quién hizo qué y cuándo? Solo se inserta, nunca se edita."""

    negocio = models.ForeignKey(Negocio, on_delete=models.CASCADE, related_name="auditoria")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    accion = models.CharField(max_length=50)
    entidad = models.CharField(max_length=50)
    entidad_id = models.CharField(max_length=40)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.usuario} {self.accion} {self.entidad}#{self.entidad_id}"


class Suscripcion(ModeloBase):
    """Plan comercial del negocio. Nunca se bloquean los datos: al vencer, se aplican los límites del plan Gratis."""

    class Plan(models.TextChoices):
        GRATIS = "GRATIS", "Gratis"
        EMPRENDEDOR = "EMPRENDEDOR", "Emprendedor"
        NEGOCIO = "NEGOCIO", "Negocio"

    negocio = models.OneToOneField(Negocio, on_delete=models.CASCADE, related_name="suscripcion")
    plan = models.CharField(max_length=12, choices=Plan.choices, default=Plan.GRATIS)
    prueba_hasta = models.DateField(null=True, blank=True)
    pagado_hasta = models.DateField(null=True, blank=True)
    notas = models.TextField(blank=True, help_text="Pagos recibidos, acuerdos comerciales…")
    # Plan a la medida: lo que el administrador de la plataforma ajusta para este negocio (vacío = lo del plan base)
    limite_productos = models.PositiveIntegerField(null=True, blank=True)
    limite_usuarios = models.PositiveIntegerField(null=True, blank=True)
    reportes_pdf = models.BooleanField(null=True, blank=True)
    api = models.BooleanField(null=True, blank=True)
    modulos_apagados = models.JSONField(default=list, blank=True, help_text="Módulos que este negocio no tiene")

    def __str__(self):
        return f"{self.negocio} · {self.get_plan_display()}"

    def _hoy(self):
        from django.utils import timezone

        return timezone.localdate()

    @property
    def en_prueba(self) -> bool:
        return bool(self.prueba_hasta and self.prueba_hasta >= self._hoy())

    @property
    def al_dia(self) -> bool:
        return bool(self.pagado_hasta and self.pagado_hasta >= self._hoy())

    @property
    def plan_efectivo(self) -> str:
        if self.en_prueba:
            return self.Plan.NEGOCIO  # la prueba incluye todo
        return self.plan if (self.al_dia or self.plan == self.Plan.GRATIS) else self.Plan.GRATIS

    @property
    def vencido(self) -> bool:
        return not self.en_prueba and not self.al_dia and self.plan != self.Plan.GRATIS

    @property
    def a_la_medida(self) -> bool:
        return any(v is not None for v in (self.limite_productos, self.limite_usuarios, self.reportes_pdf, self.api)) \
            or bool(self.modulos_apagados)

    @property
    def limites(self) -> dict:
        """Lo que puede usar: el plan base y, encima, lo que se le ajustó a la medida (si el pago no está vencido)."""
        from django.conf import settings

        lim = dict(settings.PLANES[self.plan_efectivo])
        if self.vencido:
            return lim
        for campo, clave in (("limite_productos", "productos"), ("limite_usuarios", "usuarios"),
                             ("reportes_pdf", "reportes_pdf"), ("api", "api")):
            valor = getattr(self, campo)
            if valor is not None:
                lim[clave] = valor
        if self.a_la_medida and not self.en_prueba:
            lim["nombre"] = f"{lim['nombre']} a la medida"
        return lim

    def tiene_modulo(self, clave: str) -> bool:
        return clave not in (self.modulos_apagados or [])

    @property
    def dias_restantes(self) -> int | None:
        fin = self.prueba_hasta if self.en_prueba else self.pagado_hasta
        return (fin - self._hoy()).days if fin else None


class Comentario(ModeloBase):
    """Comentarios, errores e ideas enviados desde la aplicación (clave durante el piloto)."""

    class Tipo(models.TextChoices):
        IDEA = "IDEA", "Idea o mejora"
        ERROR = "ERROR", "Algo no funciona"
        PREGUNTA = "PREGUNTA", "Pregunta"

    negocio = models.ForeignKey(Negocio, null=True, blank=True, on_delete=models.CASCADE)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.IDEA)
    texto = models.TextField(max_length=2000)
    pagina = models.CharField(max_length=200, blank=True)
    calificacion = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1 a 5")
    atendido = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creado"]


class EjecucionTarea(models.Model):
    """Registro de cada ejecución de las tareas programadas (para saber si el cron está corriendo)."""

    nombre = models.CharField(max_length=60, db_index=True)
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    detalle = models.TextField(blank=True)

    class Meta:
        ordering = ["-inicio"]

    def __str__(self):
        return f"{self.nombre} {self.inicio:%Y-%m-%d %H:%M} {'OK' if self.ok else 'ERROR'}"

    @property
    def duracion_s(self):
        return round((self.fin - self.inicio).total_seconds(), 1) if self.fin else None

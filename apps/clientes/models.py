"""Clientes habituales: fidelización con puntos y niveles, ofertas por WhatsApp y encuestas de satisfacción.

Datos personales de clientes finales: el negocio es el responsable del tratamiento (Ley 1581 de 2012) y la
plataforma es encargada. Por eso se guarda la autorización y, aparte, el permiso para enviar ofertas."""

import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import ModeloBase


class Nivel(models.TextChoices):
    NUEVO = "NUEVO", "Nuevo"
    FRECUENTE = "FRECUENTE", "Frecuente"
    VIP = "VIP", "VIP"


MULTIPLICADOR_NIVEL = {Nivel.NUEVO: 1, Nivel.FRECUENTE: 1.25, Nivel.VIP: 1.5}


class Cliente(ModeloBase):
    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="clientes")
    nombre = models.CharField(max_length=120)
    telefono = models.CharField("Celular / WhatsApp", max_length=20, blank=True)
    email = models.EmailField(blank=True)
    documento = models.CharField(max_length=20, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True, help_text="Para saludarlo en su cumpleaños")
    notas = models.TextField(blank=True, help_text="Preferencias: talla, tono, alergias a ingredientes…")
    referido_por = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referidos",
                                     help_text="Cliente que lo trajo (gana puntos en su primera compra)")
    mayor_edad_verificado = models.BooleanField("Se verificó con cédula que es mayor de edad", default=False)

    acepta_datos = models.BooleanField("Autorizó el tratamiento de sus datos", default=False)
    acepta_ofertas = models.BooleanField("Acepta recibir ofertas por WhatsApp", default=False)
    fecha_autorizacion = models.DateTimeField(null=True, blank=True)

    # Valores en caché (se recalculan con cada venta)
    puntos = models.IntegerField(default=0)
    nivel = models.CharField(max_length=10, choices=Nivel.choices, default=Nivel.NUEVO)
    n_compras = models.PositiveIntegerField(default=0)
    total_compras = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    primera_compra = models.DateTimeField(null=True, blank=True)
    ultima_compra = models.DateTimeField(null=True, blank=True, db_index=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [models.UniqueConstraint(fields=["negocio", "telefono"], condition=~Q(telefono=""),
                                               name="cliente_telefono_unico_por_negocio")]
        indexes = [models.Index(fields=["negocio", "activo"])]

    def __str__(self):
        return self.nombre

    @property
    def primer_nombre(self):
        return (self.nombre or "").split(" ")[0]


class MovimientoPuntos(models.Model):
    """Libro de puntos: inmutable, como el kárdex. El saldo del cliente es la suma."""

    class Tipo(models.TextChoices):
        GANADOS = "GANADOS", "Ganados por compra"
        CANJEADOS = "CANJEADOS", "Canjeados"
        DEVUELTOS = "DEVUELTOS", "Reversados por anulación"
        AJUSTE = "AJUSTE", "Ajuste manual"
        BONO = "BONO", "Bono (visitas, referidos, grupos)"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="movimientos_puntos")
    venta = models.ForeignKey("ventas.Venta", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    puntos = models.IntegerField(help_text="Positivo suma, negativo resta")
    saldo = models.IntegerField()
    fecha = models.DateTimeField(db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    motivo = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Los movimientos de puntos son inmutables; registre un ajuste.")
        super().save(*args, **kwargs)


class Segmento(models.TextChoices):
    TODOS = "TODOS", "Todos (también clientes sin registrar)"
    COMPRADORES = "COMPRADORES", "Quienes han comprado ese producto o categoría"
    VIP = "VIP", "Clientes VIP"
    FRECUENTES = "FRECUENTES", "Clientes frecuentes y VIP"
    EN_RIESGO = "EN_RIESGO", "Clientes que dejaron de venir"
    NUEVOS = "NUEVOS", "Clientes nuevos"
    CUMPLEANOS = "CUMPLEANOS", "Cumpleañeros del mes"


class Oferta(ModeloBase):
    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="ofertas")
    titulo = models.CharField(max_length=120)
    descuento_pct = models.DecimalField("Descuento %", max_digits=5, decimal_places=2)
    producto = models.ForeignKey("catalogo.Producto", null=True, blank=True, on_delete=models.CASCADE,
                                 help_text="Vacío = aplica a toda la compra (o a la categoría)")
    categoria = models.ForeignKey("catalogo.Categoria", null=True, blank=True, on_delete=models.CASCADE)
    segmento = models.CharField(max_length=12, choices=Segmento.choices, default=Segmento.TODOS)
    desde = models.DateField()
    hasta = models.DateField()
    mensaje = models.TextField(
        blank=True, help_text="Mensaje de WhatsApp. Puedes usar {nombre}, {puntos}, {negocio}, {descuento}, {hasta}")
    activa = models.BooleanField(default=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    origen = models.CharField(max_length=10, default="MANUAL")  # MANUAL | SUGERIDA
    clave_sugerencia = models.CharField(max_length=80, blank=True)
    razon = models.TextField(blank=True, help_text="Por qué el sistema la sugirió")

    class Meta:
        ordering = ["-desde", "-id"]

    def __str__(self):
        return self.titulo

    def vigente(self, hoy) -> bool:
        return self.activa and self.desde <= hoy <= self.hasta


class EnvioOferta(models.Model):
    """A quién se le envió cada oferta (para medir si volvió a comprar)."""

    oferta = models.ForeignKey(Oferta, on_delete=models.CASCADE, related_name="envios")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="ofertas_recibidas")
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = ("oferta", "cliente")


def _token():
    return secrets.token_urlsafe(12)


class Encuesta(models.Model):
    """«¿Cómo te atendimos?» — un enlace por venta, sin necesidad de iniciar sesión."""

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="encuestas")
    venta = models.OneToOneField("ventas.Venta", on_delete=models.CASCADE, related_name="encuesta")
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.SET_NULL, related_name="encuestas")
    token = models.CharField(max_length=24, unique=True, default=_token)
    calificacion = models.PositiveSmallIntegerField(null=True, blank=True)
    comentario = models.TextField(blank=True, max_length=1000)
    creada = models.DateTimeField(auto_now_add=True)
    respondida = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-respondida", "-creada"]

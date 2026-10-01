"""Bares y discotecas: mesas y cuentas abiertas, cover y aforo, reservas (VIP, grupos, cumpleaños, listas),
precios por franja horaria (happy hour, noches) y botellas guardadas.

La noche de trabajo no coincide con el día calendario: una venta a las 2 a. m. del sábado es de la noche del
viernes. `noche_de(fecha)` usa la hora de corte del negocio (6 a. m. por defecto)."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import ModeloBase


class ConfiguracionNocturna(ModeloBase):
    class NivelCover(models.TextChoices):
        NINGUNO = "NINGUNO", "Nadie (todos pagan)"
        VIP = "VIP", "Clientes VIP"
        FRECUENTE = "FRECUENTE", "Frecuentes y VIP"

    negocio = models.OneToOneField("core.Negocio", on_delete=models.CASCADE, related_name="nocturno")
    hora_corte = models.PositiveSmallIntegerField(default=6, help_text="Hora en que termina la noche (0 a 12)")
    aforo = models.PositiveIntegerField(default=0, help_text="Capacidad máxima de personas (0 = sin control)")
    cover_valor = models.PositiveIntegerField(default=0, help_text="Valor de la entrada por persona (0 = sin cover)")
    cover_consumible = models.BooleanField(default=True, help_text="El cover se descuenta de lo que consuma")
    cover_gratis_desde = models.CharField(max_length=10, choices=NivelCover.choices, default=NivelCover.VIP)
    acompanantes_gratis = models.PositiveSmallIntegerField(
        default=1, help_text="Acompañantes que entran gratis con el cliente VIP o frecuente (el resto del grupo paga)")
    propina_sugerida_pct = models.PositiveSmallIntegerField(
        default=10, validators=[MaxValueValidator(10)],
        help_text="Propina voluntaria sugerida al cobrar. Ley 1935 de 2018: máximo el 10 % antes de impuestos y el "
                  "cliente decide si la acepta, la cambia o no la da")
    grupo_minimo_personas = models.PositiveSmallIntegerField(default=10, help_text="Desde cuántas personas es grupo")
    grupo_descuento_pct = models.DecimalField(max_digits=5, decimal_places=2, default=10,
                                              help_text="Descuento en la cuenta de un grupo")
    grupo_puntos_por_asistente = models.PositiveIntegerField(
        default=20, help_text="Puntos para quien organiza el grupo por cada persona que llegó")
    visitas_para_bono = models.PositiveSmallIntegerField(default=5, help_text="Cada cuántas noches de visita hay bono")
    puntos_bono_visita = models.PositiveIntegerField(default=100)
    puntos_por_referido = models.PositiveIntegerField(
        default=50, help_text="Para quien trae a un cliente nuevo, cuando este hace su primera compra")
    botella_guardada_dias = models.PositiveSmallIntegerField(default=60, help_text="Días que se guarda una botella")
    exigir_mayoria_edad = models.BooleanField(
        default=True, help_text="Registrar clientes solo si se verificó la cédula (Ley 124 de 1994)")

    def __str__(self):
        return f"Noche de {self.negocio}"

    @staticmethod
    def valores_para(giro) -> dict:
        if giro == "BAR":
            return {"cover_valor": 0, "aforo": 0}
        return {"cover_valor": 20000, "aforo": 300}  # discoteca y bar-discoteca


def noche_de(momento, negocio=None) -> "date":  # noqa: F821
    """Fecha de la noche a la que pertenece un momento (ej.: sábado 2 a. m. → viernes)."""
    corte = 6
    if negocio is not None:
        conf = getattr(negocio, "nocturno", None)
        corte = conf.hora_corte if conf else 6
    local = timezone.localtime(momento)
    return (local - timedelta(hours=corte)).date()


class Mesa(models.Model):
    class Zona(models.TextChoices):
        BARRA = "BARRA", "Barra"
        SALON = "SALON", "Salón"
        VIP = "VIP", "VIP"
        TERRAZA = "TERRAZA", "Terraza"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="mesas")
    nombre = models.CharField(max_length=40)
    zona = models.CharField(max_length=10, choices=Zona.choices, default=Zona.SALON)
    capacidad = models.PositiveSmallIntegerField(default=4)
    consumo_minimo = models.PositiveIntegerField(default=0, help_text="Para mesas VIP (0 = sin mínimo)")
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["zona", "nombre"]
        unique_together = ("negocio", "nombre")

    def __str__(self):
        return self.nombre


class AsignacionMesa(models.Model):
    """Qué mesero atiende cada mesa en una noche (o turno). La arma el dueño o el encargado."""

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="asignaciones_mesa")
    noche = models.DateField(db_index=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE, related_name="asignaciones")
    mesero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mesas_asignadas")

    class Meta:
        unique_together = ("mesa", "noche")
        ordering = ["mesa__zona", "mesa__nombre"]


class Reserva(ModeloBase):
    class Tipo(models.TextChoices):
        MESA = "MESA", "Mesa"
        GRUPO = "GRUPO", "Grupo"
        CUMPLEANOS = "CUMPLEANOS", "Cumpleaños"
        LISTA = "LISTA", "Lista de invitados (promotor)"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        LLEGO = "LLEGO", "Llegó"
        NO_LLEGO = "NO_LLEGO", "No llegó"
        CANCELADA = "CANCELADA", "Cancelada"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="reservas")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.MESA)
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="reservas", help_text="Quien reserva u organiza")
    nombre = models.CharField(max_length=120, help_text="A nombre de quién")
    telefono = models.CharField(max_length=20, blank=True)
    promotor = models.CharField(max_length=80, blank=True, help_text="Relacionista / promotor que la trajo")
    fecha = models.DateField(help_text="Noche de la reserva")
    hora = models.TimeField(null=True, blank=True)
    personas = models.PositiveSmallIntegerField(default=2)
    mesa = models.ForeignKey(Mesa, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservas")
    consumo_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    anticipo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    notas = models.TextField(blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["fecha", "hora", "id"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.nombre} · {self.fecha:%d/%m}"

    @property
    def es_grupo(self) -> bool:
        conf = getattr(self.negocio, "nocturno", None)
        minimo = conf.grupo_minimo_personas if conf else 10
        return self.personas >= minimo

    @property
    def llegaron(self) -> int:
        return self.invitados.filter(llego=True).count()


class Invitado(models.Model):
    """Personas de una reserva de grupo, cumpleaños o lista: al llegar se registran (y pueden volverse clientes)."""

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="invitados")
    nombre = models.CharField(max_length=120)
    telefono = models.CharField(max_length=20, blank=True)
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    llego = models.BooleanField(default=False)
    llegada = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nombre"]


class Ingreso(models.Model):
    """Entrada a la discoteca: cuenta el aforo y cobra el cover (que puede ser consumible)."""

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="ingresos")
    noche = models.DateField(db_index=True)
    fecha = models.DateTimeField(default=timezone.now)
    personas = models.PositiveSmallIntegerField(default=1)
    valor_por_persona = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    personas_gratis = models.PositiveSmallIntegerField(default=0)
    consumible = models.BooleanField(default=True)
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reserva = models.ForeignKey(Reserva, null=True, blank=True, on_delete=models.SET_NULL, related_name="ingresos")
    motivo_gratis = models.CharField(max_length=80, blank=True)
    medio_pago = models.CharField(max_length=15, default="EFECTIVO")
    cuenta = models.ForeignKey("Cuenta", null=True, blank=True, on_delete=models.SET_NULL, related_name="ingresos")
    venta = models.ForeignKey("ventas.Venta", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-fecha"]

    @property
    def total(self) -> Decimal:
        return self.valor_por_persona * max(0, self.personas - self.personas_gratis)


class Cuenta(ModeloBase):
    """Cuenta abierta de una mesa o de la barra: se van sumando rondas y se cobra al final (toda o por partes)."""

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        COBRADA = "COBRADA", "Cobrada"
        ANULADA = "ANULADA", "Anulada"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="cuentas")
    mesa = models.ForeignKey(Mesa, null=True, blank=True, on_delete=models.SET_NULL, related_name="cuentas")
    nombre = models.CharField(max_length=80, blank=True, help_text="Ej.: «Barra – camisa roja»")
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="cuentas")
    reserva = models.ForeignKey(Reserva, null=True, blank=True, on_delete=models.SET_NULL, related_name="cuentas")
    personas = models.PositiveSmallIntegerField(default=1)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA, db_index=True)
    abierta_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    mesero = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="cuentas_atendidas", help_text="Quién atiende la mesa")
    pide_cuenta = models.DateTimeField(null=True, blank=True, help_text="Cuándo el mesero avisó que quieren pagar")
    noche = models.DateField(db_index=True)
    credito = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                  help_text="Cover consumible y anticipos: se descuentan al cobrar")
    credito_usado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    consumo_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    descuento_grupo_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cerrada = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return self.nombre or (str(self.mesa) if self.mesa else f"Cuenta #{self.pk}")

    @property
    def credito_disponible(self) -> Decimal:
        return self.credito - self.credito_usado


class ItemCuenta(models.Model):
    cuenta = models.ForeignKey(Cuenta, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="+")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3)
    agregado = models.DateTimeField(default=timezone.now, help_text="Define si aplica happy hour")
    agregado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    nota = models.CharField(max_length=120, blank=True)
    venta = models.ForeignKey("ventas.Venta", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="Venta con la que se cobró (vacío = pendiente)")
    cortesia = models.BooleanField(default=False, help_text="Invitación de la casa (precio 0, sí descuenta inventario)")

    class Meta:
        ordering = ["agregado", "id"]


class PrecioEspecial(ModeloBase):
    """Happy hour, noche de damas, 2×1…: se aplica solo según el día y la hora del pedido."""

    class Tipo(models.TextChoices):
        PORCENTAJE = "PORCENTAJE", "Descuento %"
        DOS_POR_UNO = "DOS_POR_UNO", "2 × 1"
        PRECIO_FIJO = "PRECIO_FIJO", "Precio fijo"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="precios_especiales")
    nombre = models.CharField(max_length=80, help_text="Ej.: Happy hour, Jueves de rumba")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.PORCENTAJE)
    valor = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                help_text="Porcentaje o precio fijo (no aplica al 2×1)")
    dias = models.JSONField(default=list, help_text="0 = lunes … 6 = domingo")
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(help_text="Puede pasar la medianoche (ej.: 22:00 a 01:00)")
    producto = models.ForeignKey("catalogo.Producto", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    categoria = models.ForeignKey("catalogo.Categoria", null=True, blank=True, on_delete=models.CASCADE,
                                  related_name="+")
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["hora_inicio"]

    def __str__(self):
        return self.nombre

    def vigente_en(self, momento) -> bool:
        local = timezone.localtime(momento)
        hora, dia = local.time(), local.weekday()
        if self.hora_inicio <= self.hora_fin:
            return dia in self.dias and self.hora_inicio <= hora < self.hora_fin
        # cruza la medianoche: después de la medianoche cuenta el día en que empezó
        if hora >= self.hora_inicio:
            return dia in self.dias
        return hora < self.hora_fin and (dia - 1) % 7 in self.dias

    def aplica_a(self, producto) -> bool:
        if self.producto_id:
            return self.producto_id == producto.pk
        if self.categoria_id:
            return self.categoria_id == producto.categoria_id
        return True


class BotellaGuardada(models.Model):
    """«Te la guardamos»: lo que quedó de una botella queda a nombre del cliente para su próxima visita."""

    class Estado(models.TextChoices):
        GUARDADA = "GUARDADA", "Guardada"
        RETIRADA = "RETIRADA", "Retirada"
        VENCIDA = "VENCIDA", "Vencida"

    negocio = models.ForeignKey("core.Negocio", on_delete=models.CASCADE, related_name="botellas_guardadas")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.CASCADE, related_name="botellas_guardadas")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="+")
    restante_pct = models.PositiveSmallIntegerField(help_text="Cuánto quedó (en %)")
    guardada = models.DateTimeField(default=timezone.now)
    vence = models.DateField()
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.GUARDADA)
    ubicacion = models.CharField(max_length=40, blank=True, help_text="Estante / casillero")
    retirada = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["vence"]

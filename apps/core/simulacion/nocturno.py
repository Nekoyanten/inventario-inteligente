"""Simulador de un bar o discoteca usando el sistema durante varias semanas (piloto simulado de la Fase 10).

Como el simulador general, separa el inventario FÍSICO (lo que hay en la barra) del SISTEMA, y todo pasa por los
servicios reales: puerta (cover y aforo), cuentas por mesa, happy hour, reservas y grupos, botellas y tragos,
conteos semanales, compras, clientes, puntos, bonos, botellas guardadas, recordatorios y ofertas.

Supuestos de comportamiento (no medidos; razonables y a la vista para discutirlos):
- Cada persona del «universo» del negocio visita con una probabilidad propia (pocos muy fieles, muchos ocasionales).
- Con la fidelización activa, un cliente registrado vuelve un poco más: +5 % por puntos y niveles, +30 % mientras
  tiene una botella guardada, +15 % durante la semana siguiente a un recordatorio u oferta por WhatsApp y +10 %
  cuando le falta una visita para el bono.
- El bartender sirve de más un porcentaje (sobreservido) y regala algunos tragos sin registrarlos.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, TipoProducto, UnidadMedida
from apps.clientes.models import Cliente
from apps.core.models import Negocio
from apps.inventario.models import TipoMovimiento
from apps.inventario.recetas import guardar_item_receta
from apps.inventario.services import aprobar_conteo, crear_conteo, enviar_conteo, registrar_movimiento, sin_evaluacion_automatica
from apps.nocturno import services as noc
from apps.nocturno.models import BotellaGuardada, Invitado, Mesa, PrecioEspecial, Reserva
from apps.proveedores.models import Proveedor
from apps.usuarios.models import Rol, Usuario

from .tienda import cumpleanos

TZ = timezone.get_current_timezone()

# nombre, ml, costo botella, precio botella, precio trago (30–45 ml)
BOTELLAS = [
    ("Aguardiente Nariño", 750, 32000, 85000, 7000), ("Aguardiente Antioqueño", 750, 36000, 95000, 8000),
    ("Aguardiente Nariño", 375, 17000, 48000, 7000), ("Ron Viejo de Caldas", 750, 38000, 100000, 9000),
    ("Ron Medellín 8 años", 750, 45000, 120000, 10000), ("Ron Medellín", 375, 20000, 55000, 9000),
    ("Whisky Old Parr", 750, 110000, 260000, 22000), ("Whisky Buchanan's", 750, 115000, 270000, 22000),
    ("Whisky Johnnie Walker Red", 750, 75000, 180000, 16000), ("Tequila José Cuervo", 750, 70000, 170000, 15000),
    ("Vodka Absolut", 750, 65000, 160000, 14000), ("Ginebra Tanqueray", 750, 80000, 190000, 16000),
    ("Aguardiente Amarillo", 750, 34000, 90000, 8000), ("Ron Caña Brava", 750, 60000, 150000, 13000),
    ("Tequila Olmeca", 750, 60000, 150000, 13000), ("Whisky Chivas 12", 750, 130000, 300000, 25000),
]
CERVEZAS = [("Poker", 2300, 6000), ("Águila", 2300, 6000), ("Club Colombia", 2800, 7000), ("Corona", 4500, 11000),
            ("Stella Artois", 4200, 10000), ("Heineken", 3200, 8000), ("BBC Cajicá", 5000, 12000),
            ("Pilsen", 2300, 6000), ("Costeña", 2200, 6000), ("Michelada (base)", 2800, 9000)]
OTROS = [("Agua", 1200, 4000), ("Gaseosa", 1500, 4500), ("Soda", 1500, 4500), ("Red Bull", 5500, 12000),
         ("Papas fritas", 2500, 8000), ("Picada para 2", 9000, 28000), ("Alitas x6", 8000, 22000),
         ("Nachos", 6000, 18000), ("Cigarrillos", 9000, 14000), ("Jugo natural", 2500, 8000)]
INSUMOS = [("Limón", "kg", 4000), ("Hielo", "kg", 800), ("Hierbabuena", "kg", 12000), ("Azúcar", "kg", 4000),
           ("Soda para cócteles", "und", 1500), ("Zumo de naranja", "L", 6000)]
COCTELES = [  # nombre, botella base (índice), ml, [(insumo, cantidad)], precio
    ("Mojito", 3, 60,
     [("Limón", 0.04), ("Hierbabuena", 0.01), ("Azúcar", 0.02), ("Soda para cócteles", 1), ("Hielo", 0.2)], 22000),
    ("Cuba libre", 4, 60, [("Limón", 0.02), ("Hielo", 0.2)], 20000),
    ("Margarita", 9, 60, [("Limón", 0.05), ("Azúcar", 0.01), ("Hielo", 0.2)], 24000),
    ("Gin tonic", 11, 60, [("Limón", 0.02), ("Soda para cócteles", 1), ("Hielo", 0.2)], 26000),
    ("Destornillador", 10, 60, [("Zumo de naranja", 0.15), ("Hielo", 0.2)], 20000),
    ("Tequila sunrise", 14, 60, [("Zumo de naranja", 0.15), ("Hielo", 0.2)], 22000),
    ("Aguardiente sour", 0, 60, [("Limón", 0.05), ("Azúcar", 0.02), ("Hielo", 0.2)], 18000),
    ("Whisky en las rocas", 8, 60, [("Hielo", 0.2)], 24000),
]
FACTOR_BOOST = {"base": 0.05, "botella": 0.30, "mensaje": 0.15, "bono": 0.10}


@dataclass
class Metricas:
    noches: int = 0
    grupos: int = 0
    personas: int = 0
    rechazados_aforo: int = 0
    pedidos: int = 0
    perdidos_agotado: int = 0
    registrados_nuevos: int = 0
    visitas_registrados: int = 0
    visitas_totales: int = 0
    botellas_guardadas: int = 0
    botellas_retiradas: int = 0
    recordatorios: int = 0
    ofertas_enviadas: int = 0
    reservas: int = 0
    reservas_no_llegan: int = 0
    grupos_grandes: int = 0
    cortesias_sin_registro: float = 0
    compras_no_registradas: int = 0
    conteos: int = 0
    cuentas_divididas: int = 0
    happy_hour_pedidos: int = 0
    visitas_por_persona: dict = field(default_factory=lambda: defaultdict(int))


class SimuladorNocturno:
    def __init__(self, perfil: dict, inicio: date, dias: int, semilla: int = 7, fidelizacion: bool = True):
        self.p, self.inicio, self.dias, self.fid = perfil, inicio, dias, fidelizacion
        self.rng = random.Random(f"{semilla}-{perfil['clave']}")
        # Números aleatorios comunes para comparar con y sin fidelización: las mismas personas, las mismas reservas y,
        # si una persona viene la misma noche en los dos casos, pide exactamente lo mismo. Solo difiere la fidelización.
        self.semilla = semilla
        self.rng_personas = random.Random(f"{semilla}-{perfil['clave']}-personas")
        self.rng_ops = random.Random(f"{semilla}-{perfil['clave']}-operacion")
        self.g = self.rng_ops
        self.rng_cumple = random.Random(f"{semilla}-{perfil['clave']}-cumple")  # aparte: no altera los demás
        self.m = Metricas()
        self.fisico: dict[int, float] = {}
        self.boost_hasta: dict[int, date] = {}      # persona → fecha hasta la que tiene el empujón del mensaje
        self.cliente_de: dict[int, Cliente] = {}    # persona → Cliente registrado
        self.botella_de: dict[int, BotellaGuardada] = {}
        self.llegadas: dict[date, list] = defaultdict(list)

    # ------------------------------------------------------------------ montaje
    def crear(self):
        p = self.p
        with transaction.atomic(), sin_evaluacion_automatica():
            self.negocio = Negocio.objects.create(nombre=p["negocio"], giro=p["giro"], direccion=p["lugar"])
            s = self.negocio.suscripcion
            s.prueba_hasta = self.inicio + timedelta(days=self.dias + 14)
            s.save()
            conf = noc.configuracion(self.negocio)
            conf.cover_valor, conf.aforo = p["cover"], p["aforo"]
            conf.cover_consumible = p.get("consumible", True)
            conf.save()
            cfg = self.negocio.config
            cfg.fidelizacion_activa = self.fid
            cfg.save()
            nombre, *ap = p["dueno"].split()
            clave = p.get("clave_acceso", "PilotoSimulado2026!")
            self.dueno = Usuario.objects.create_user(p.get("usuario", p["clave"]), password=clave, first_name=nombre,
                                                     last_name=" ".join(ap), negocio=self.negocio, rol=Rol.ADMIN)
            self.meseros = [self.dueno] + [Usuario.objects.create_user(
                f"{p.get('usuario', p['clave'])}-mesero{i}", password=clave if "clave_acceso" in p else "x" * 12,
                negocio=self.negocio, rol=Rol.VENDEDOR) for i in range(1, p.get("meseros", 3) + 1)]
            # proveedores: uno para todo, o uno por categoría ({"Cervezas": ("Bavaria", 2), "_": (...)})
            provs = p.get("proveedores") or {"_": ("Distribuidora de Licores del Sur", 2)}
            self.proveedores = {cat: Proveedor.objects.create(negocio=self.negocio, nombre=nom, tiempo_entrega_dias=dias)
                                for cat, (nom, dias) in provs.items()}
            self.proveedor = self.proveedores["_"]
            self._catalogo()
            self._mesas()
            if p["happy_hour"]:
                dias, ini, fin, tipo, cat = p["happy_hour"]
                PrecioEspecial.objects.create(
                    negocio=self.negocio, nombre="Happy hour", tipo=tipo, valor=25 if tipo == "PORCENTAJE" else 0,
                    dias=list(dias), hora_inicio=time.fromisoformat(ini), hora_fin=time.fromisoformat(fin),
                    categoria=Categoria.objects.get(negocio=self.negocio, nombre=cat))
        # universo de personas: pocas muy fieles, muchas ocasionales (lognormal)
        n = p["pool"]
        # «fieles» concentra la frecuencia: más alto = un núcleo de habituales que viene casi cada semana
        sigma = 1.1 + 4 * p["fieles"]
        self.prob = [self.rng_personas.lognormvariate(0, sigma) for _ in range(n)]
        self.escala = 1 / sum(self.prob)
        self.amigos = [self.rng_personas.sample(range(n), 2) for _ in range(n)]
        self.dia_semana_total = sum(p["dias"].values())
        return self

    def _catalogo(self):
        cats = {c.nombre: c for c in Categoria.objects.filter(negocio=self.negocio)}
        bot = UnidadMedida.objects.get(abreviatura="bot")
        und = UnidadMedida.objects.get(abreviatura="und")
        uds = {u.abreviatura: u for u in UnidadMedida.objects.all()}
        self.botellas, self.tragos, self.cervezas, self.otros, self.cocteles = [], [], [], [], []
        self.ml, self.receta_fis = {}, {}
        cat_p = self.p.get("catalogo", {})
        prov = self._proveedor_de
        for i, (nombre, ml, costo, precio, precio_trago) in enumerate(cat_p.get("botellas", BOTELLAS)):
            b = Producto.objects.create(negocio=self.negocio, sku=f"B{i:02d}", nombre=f"{nombre} {ml} ml",
                                        categoria=cats["Botellas"], unidad=bot, precio_compra=costo, precio_venta=precio,
                                        proveedor_principal=prov("Botellas", nombre), stock_minimo=2)
            self.botellas.append(b)
            self.ml[b.pk] = ml
            ml_trago = 30 if "Aguardiente" in nombre else 45
            t = noc.crear_trago(b, ml_botella=ml, ml_trago=ml_trago, precio=precio_trago)
            self.tragos.append(t)
            self.receta_fis[t.pk] = [(b.pk, ml_trago / ml, True)]
        for i, (nombre, costo, precio) in enumerate(cat_p.get("cervezas", CERVEZAS)):
            self.cervezas.append(Producto.objects.create(
                negocio=self.negocio, sku=f"C{i:02d}", nombre=nombre, categoria=cats["Cervezas"], unidad=und,
                precio_compra=costo, precio_venta=precio, proveedor_principal=prov("Cervezas", nombre), stock_minimo=24))
        for i, (nombre, costo, precio) in enumerate(cat_p.get("otros", OTROS)):
            bebida = nombre in ("Agua", "Gaseosa", "Soda", "Red Bull", "Jugo natural")
            cat = cats["Bebidas sin alcohol"] if bebida else cats["Comida y pasabocas"]
            self.otros.append(Producto.objects.create(
                negocio=self.negocio, sku=f"O{i:02d}", nombre=nombre, categoria=cat, unidad=und, precio_compra=costo,
                precio_venta=precio, proveedor_principal=prov("Otros", nombre), stock_minimo=10))
        insumos = {}
        for i, (nombre, u, costo) in enumerate(INSUMOS):
            insumos[nombre] = Producto.objects.create(
                negocio=self.negocio, sku=f"I{i:02d}", nombre=nombre, tipo=TipoProducto.INSUMO,
                categoria=cats["Insumos de barra"], unidad=uds[u], precio_compra=costo,
                proveedor_principal=prov("Insumos", nombre), stock_minimo=2)
        for i, (nombre, base, ml, items, precio) in enumerate(cat_p.get("cocteles", COCTELES)):
            if isinstance(base, str):  # la botella base por nombre ("Ron", "Tanqueray"…)
                b = next((x for x in self.botellas if base.lower() in x.nombre.lower()), None)
                if b is None:
                    continue
            else:
                b = self.botellas[base]
            c = Producto.objects.create(negocio=self.negocio, sku=f"K{i:02d}", nombre=nombre, tipo=TipoProducto.PREPARADO,
                                        categoria=cats["Tragos y cócteles"], precio_venta=precio)
            guardar_item_receta(c, b, Decimal(ml) / Decimal(self.ml[b.pk]))
            fis = [(b.pk, ml / self.ml[b.pk], True)]
            for ins, cant in items:
                guardar_item_receta(c, insumos[ins], Decimal(str(cant)))
                fis.append((insumos[ins].pk, cant, False))
            self.cocteles.append(c)
            self.receta_fis[c.pk] = fis
        self.insumos = list(insumos.values())
        # stock inicial: 2 a 3 semanas de consumo aproximado
        fecha = timezone.make_aware(datetime.combine(self.inicio - timedelta(days=1), time(12)), TZ)
        for prod in self.botellas + self.cervezas + self.otros + self.insumos:
            cant = {"B": self.rng_ops.randint(6, 14), "C": self.rng_ops.randint(96, 240), "O": self.rng_ops.randint(24, 60),
                    "I": self.rng_ops.randint(5, 15)}[prod.sku[0]]
            registrar_movimiento(producto=prod, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=cant, usuario=self.dueno,
                                 fecha=fecha, evaluar_alertas=False)
            self.fisico[prod.pk] = float(cant)
        self.por_pk = {x.pk: x for x in self.botellas + self.tragos + self.cervezas + self.otros + self.cocteles
                       + self.insumos}

    def _proveedor_de(self, categoria, nombre=""):
        """El proveedor de un producto: por marca (si la clave aparece en el nombre), por categoría o el general."""
        for clave, prov in self.proveedores.items():
            if clave.startswith("marca:") and clave[6:].lower() in nombre.lower():
                return prov
        return self.proveedores.get(categoria, self.proveedor)

    def _mesas(self):
        n = max(6, int(self.p["aforo"] / 12) if self.p["aforo"] else 12)
        self.mesas = [Mesa.objects.create(negocio=self.negocio, nombre=f"M{i + 1}", capacidad=4) for i in range(n)]
        if self.p["giro"] != "BAR":
            self.mesas += [Mesa.objects.create(negocio=self.negocio, nombre=f"VIP {i + 1}", zona="VIP", capacidad=10,
                                               consumo_minimo=400000) for i in range(4)]

    # ------------------------------------------------------------------ utilidades
    def _momento(self, noche: date, hora: float) -> datetime:
        dia = noche + timedelta(days=1) if hora >= 24 else noche
        h = hora % 24
        return timezone.make_aware(datetime.combine(dia, time(int(h), int((h % 1) * 60))), TZ)

    def _boost(self, persona: int, noche: date) -> float:
        c = self.cliente_de.get(persona)
        if not (self.fid and c):
            return 0.0
        b = FACTOR_BOOST["base"]
        if persona in self.botella_de:
            b += FACTOR_BOOST["botella"]
        if self.boost_hasta.get(persona, date.min) >= noche:
            b += FACTOR_BOOST["mensaje"]
        conf = self.negocio.nocturno
        if conf.visitas_para_bono and (c.n_compras + 1) % conf.visitas_para_bono == 0:
            b += FACTOR_BOOST["bono"]
        return b

    def _servir(self, prod: Producto, cant: float) -> bool:
        """Saca del inventario físico lo que realmente se sirve (con el sobreservido). False si no alcanza."""
        if prod.pk in self.receta_fis:
            necesita = [(pid, q * cant * ((1 + self.p["sobreservido"] * self.g.uniform(0.5, 1.5)) if es_licor else 1))
                        for pid, q, es_licor in self.receta_fis[prod.pk]]
        else:
            necesita = [(prod.pk, cant)]
        if any(self.fisico[pid] < q for pid, q in necesita if self.por_pk[pid].sku[0] == "B" or q >= 1):
            return False
        for pid, q in necesita:
            self.fisico[pid] = max(0.0, self.fisico[pid] - q)
        return True

    def _elegir(self, cat):
        if cat == "cerveza":
            return self.g.choice(self.cervezas[:6] * 3 + self.cervezas)
        if cat == "trago":
            return self.g.choice(self.tragos[:4] * 3 + self.tragos)
        if cat == "coctel" and self.cocteles:
            return self.g.choice(self.cocteles)
        return self.g.choice(self.otros)

    # ------------------------------------------------------------------ una noche
    def simular_noche(self, n: int):
        noche = self.inicio + timedelta(days=n)
        dow = noche.weekday()
        self._llegan_compras(noche)
        if dow not in self.p["dias"]:
            if dow == 0:
                self._semana(noche)
            return
        self.m.noches += 1
        with sin_evaluacion_automatica(), transaction.atomic():
            grupos = self._grupos_de_la_noche(noche, dow)
            for g in grupos:
                self._atender(noche, g)
        self._reservas_futuras(noche)

    def _grupos_de_la_noche(self, noche, dow):
        """Quién viene esta noche: cada persona del universo decide según su frecuencia y la fidelización."""
        esperado = self.p["dias"][dow]
        lideres = []
        for persona, prob in enumerate(self.prob):
            pr = min(0.9, prob * self.escala * esperado * (1 + self._boost(persona, noche)))
            if self.rng_personas.random() < pr:
                lideres.append(persona)
        if len(lideres) > esperado * 1.6:  # la gente no cabe: los que llegan tarde se van a otro lado
            self.rng_ops.shuffle(lideres)
            lideres = lideres[: int(esperado * 1.6)]
        grupos = [{"lider": x, "tam": max(1, round(self._rng_de(noche, x, "tam").gammavariate(2.2, self.p["tam_grupo"] / 2.2))),
                   "reserva": None} for x in lideres]
        for r in Reserva.objects.filter(negocio=self.negocio, fecha=noche, estado__in=["PENDIENTE", "CONFIRMADA"]):
            llega = self.rng_ops.random() > (0.12 if r.anticipo else 0.3)
            if not llega:
                r.estado = Reserva.Estado.NO_LLEGO
                r.save(update_fields=["estado"])
                self.m.reservas_no_llegan += 1
                continue
            grupos.append({"lider": int(r.notas or 0), "tam": r.personas, "reserva": r})
        return grupos

    def _registrar(self, persona, noche, lider=None) -> Cliente | None:
        if not self.fid:
            return None
        c = self.cliente_de.get(persona)
        if c or self.rng.random() >= self.p["adopcion"]:
            return c
        ref = self.cliente_de.get(lider) if lider is not None else None
        c = Cliente.objects.create(
            negocio=self.negocio, nombre=f"Cliente {persona}", telefono=f"3{sum(map(ord, self.p['clave'])) % 10}{persona:08d}",
            acepta_datos=True, acepta_ofertas=self.rng.random() < 0.6, mayor_edad_verificado=True,
            fecha_nacimiento=cumpleanos(self.rng_cumple, noche, "BAR") if self.p.get("cumpleanos") else None,
            fecha_autorizacion=timezone.now(), referido_por=ref)
        self.cliente_de[persona] = c
        self.m.registrados_nuevos += 1
        return c

    def _rng_de(self, noche, persona, que):
        return random.Random(f"{self.semilla}-{self.p['clave']}-{noche}-{persona}-{que}")

    def _atender(self, noche, g):
        p = self.p
        self.g = self._rng_de(noche, g["lider"], "consumo")
        persona, tam, reserva = g["lider"], g["tam"], g["reserva"]
        cierre_h = p["cierre"] + 24 if p["cierre"] < 12 else p["cierre"]
        hora = self.g.uniform(p["apertura"], cierre_h - 1.5)
        llega = self._momento(noche, hora)
        fin = self._momento(noche, cierre_h)  # a la hora de cierre se deja de servir y se cobra
        mesero = self.g.choice(self.meseros)
        cliente = self._registrar(persona, noche)
        self.m.visitas_totales += 1
        self.m.visitas_por_persona[persona] += 1
        if cliente:
            self.m.visitas_registrados += 1
            cliente.refresh_from_db()
        cuenta = None
        try:
            if p["cover"] or p["aforo"]:
                ing = noc.registrar_ingreso(self.negocio, mesero, personas=tam, cliente=cliente, reserva=reserva,
                                            momento=llega)
                cuenta = ing.cuenta
            self.m.grupos += 1
            self.m.personas += tam
        except noc.ErrorNocturno:
            self.m.rechazados_aforo += tam
            return
        if reserva is not None:
            for inv in reserva.invitados.all()[: tam - 1]:
                amigo = self.amigos[persona][0] if self.rng.random() < 0.3 else None
                registrar = self.fid and self.rng.random() < p["adopcion"] and amigo is not None and \
                    amigo not in self.cliente_de
                try:
                    noc.llegada_invitado(inv, mesero, registrar_cliente=registrar, mayor_edad=True,
                                         acepta_ofertas=self.rng.random() < 0.6)
                except noc.ErrorNocturno:
                    pass
                if registrar and inv.cliente:
                    self.cliente_de[amigo] = inv.cliente
                    self.m.registrados_nuevos += 1
            mesa = next((m for m in self.mesas if m.zona == "VIP" and not m.cuentas.filter(estado="ABIERTA").exists()),
                        None) if reserva.consumo_minimo else None
            try:
                c2 = noc.marcar_llegada(reserva, mesero, mesa=mesa, momento=llega)
            except noc.ErrorNocturno:
                c2 = noc.abrir_cuenta(self.negocio, mesero, nombre=f"Reserva {reserva.pk}", personas=tam,
                                      reserva=reserva, momento=llega)
            if cuenta is not None and cuenta.credito:  # el cover consumible pasa a la cuenta de la reserva
                c2.credito += cuenta.credito
                c2.save(update_fields=["credito"])
                noc.anular_cuenta(cuenta, mesero, "Unida a la reserva")
            cuenta = c2
        elif cuenta is None:
            libre = next((m for m in self.mesas if m.zona != "VIP" and not m.cuentas.filter(estado="ABIERTA").exists()),
                         None) if tam >= 2 else None
            cuenta = noc.abrir_cuenta(self.negocio, mesero, mesa=libre, nombre="" if libre else f"Barra {persona}",
                                      personas=tam, cliente=cliente, momento=llega)
        elif cliente and not cuenta.cliente_id:
            cuenta.cliente = cliente
            cuenta.save(update_fields=["cliente"])
        if reserva is None and tam >= 2 and cliente and self.rng.random() < 0.3:  # «regístrate, te invité yo»
            self._registrar(self.amigos[persona][0], noche, lider=persona)
        # botella guardada: si tiene una, la pide
        guardada = self.botella_de.pop(persona, None)
        if guardada is not None:
            try:
                noc.retirar_botella(guardada, mesero)
                self.m.botellas_retiradas += 1
            except noc.ErrorNocturno:
                pass
        # rondas
        rondas = max(1, round(self.g.gammavariate(2.5, 1.2 if p["giro"] == "BAR" else 1.0)))
        botella_pedida = None
        if tam >= 3 and self.g.random() < p["botella"] * (1.5 if reserva else 1):
            botella_pedida = self.g.choice(self.botellas[:6] * 2 + self.botellas)
            self._pedir(cuenta, botella_pedida, max(1, tam // 6), llega, mesero)  # una botella por cada ~6 personas
            self._pedir(cuenta, self.otros[1], max(1, tam // 2), llega, mesero)  # gaseosas para mezclar
        for r in range(rondas):
            momento = llega + timedelta(minutes=r * self.g.uniform(35, 70))
            if momento >= fin:
                break
            for _ in range(tam if not botella_pedida else max(0, tam // 3)):
                cat = self.g.choices(list(p["mezcla"]), weights=list(p["mezcla"].values()))[0]
                self._pedir(cuenta, self._elegir(cat), 1, momento, mesero)
            if self.g.random() < p["cortesias"]:  # trago regalado sin registrar
                t = self.g.choice(self.tragos[:4])
                if self._servir(t, 1):
                    self.m.cortesias_sin_registro += 1
        # cobrar
        cierre = min(llega + timedelta(minutes=rondas * 55 + 20), fin + timedelta(minutes=20))
        pendientes = list(cuenta.items.filter(venta__isnull=True).values_list("pk", flat=True))
        if not pendientes:
            try:
                noc.anular_cuenta(cuenta, mesero, "Se fueron sin consumir")
            except noc.ErrorNocturno:
                pass
            return
        propina = 0
        try:
            if tam >= 4 and len(pendientes) > 3 and self.g.random() < 0.3:  # dividir la cuenta
                noc.cobrar(cuenta, mesero, items_ids=pendientes[: len(pendientes) // 2], fecha=cierre)
                self.m.cuentas_divididas += 1
            r = noc.resumen(cuenta)
            if self.g.random() < 0.55:
                propina = r["propina_sugerida"]
            puntos = 0
            if cuenta.cliente and self.fid:
                cuenta.cliente.refresh_from_db()
                if cuenta.cliente.puntos >= 300 and self.rng.random() < 0.4:
                    puntos = cuenta.cliente.puntos
            noc.cobrar(cuenta, mesero, propina=propina, puntos=puntos, fecha=cierre)
        except Exception:  # noqa: BLE001 — puntos que ya no alcanzan, etc.: se cobra sin canje
            cuenta.refresh_from_db()
            if cuenta.estado == "ABIERTA":
                noc.cobrar(cuenta, mesero, fecha=cierre)
        # ¿sobró licor de la botella?
        if botella_pedida and self.fid and cuenta.cliente and self.rng.random() < 0.55:
            restante = self.rng.randint(15, 60)
            if self.rng.random() < 0.75:
                self.botella_de[persona] = noc.guardar_botella(cuenta.cliente, botella_pedida, restante, mesero)
                self.m.botellas_guardadas += 1

    def _pedir(self, cuenta, producto, cant, momento, mesero):
        if not self._servir(producto, cant):
            self.m.perdidos_agotado += 1
            return
        noc.agregar_item(cuenta, producto, cant, mesero, momento=momento)
        self.m.pedidos += 1

    # ------------------------------------------------------------------ reservas
    def _reservas_futuras(self, noche):
        """Se hacen reservas para la próxima semana (grupos, cumpleaños, listas de promotores)."""
        p = self.p
        for dow in p["dias"]:
            fecha = noche + timedelta(days=(dow - noche.weekday()) % 7 or 7)
            if fecha >= self.inicio + timedelta(days=self.dias):
                continue
            if self.rng_ops.random() < p["reservas"] * 2:
                grande = self.rng_ops.random() < p["grupo_grande"]
                personas = self.rng_ops.randint(10, 22) if grande else self.rng_ops.randint(2, 8)
                lider = self.rng_ops.randrange(len(self.prob))
                cliente = self.cliente_de.get(lider) if self.fid else None
                vip = p["giro"] != "BAR" and (grande or self.rng_ops.random() < 0.4)
                promotor = self.rng_ops.choice(p["promotores"]) if p["promotores"] and self.rng_ops.random() < 0.6 else ""
                tipo = Reserva.Tipo.GRUPO if grande else (Reserva.Tipo.LISTA if promotor else Reserva.Tipo.MESA)
                if self.rng_ops.random() < 0.2:
                    tipo = Reserva.Tipo.CUMPLEANOS
                r = Reserva.objects.create(
                    negocio=self.negocio, tipo=tipo, nombre=f"Reserva de {lider}", cliente=cliente, fecha=fecha,
                    personas=personas, promotor=promotor, consumo_minimo=400000 if vip else 0,
                    anticipo=100000 if (vip and self.rng_ops.random() < 0.5) else 0, notas=str(lider),
                    creada_por=self.dueno)
                for i in range(personas - 1):
                    Invitado.objects.create(reserva=r, nombre=f"Invitado {i}", telefono=f"31{r.pk:04d}{i:04d}")
                self.m.reservas += 1
                self.m.grupos_grandes += grande

    # ------------------------------------------------------------------ la semana: compras, conteo, mensajes
    def _semana(self, lunes):
        from apps.compras.services import enviar_orden
        from apps.recomendaciones.models import RecomendacionCompra
        from apps.recomendaciones.services import crear_ordenes_desde_recomendaciones, generar_recomendaciones

        with sin_evaluacion_automatica(), transaction.atomic():
            if self.p["conteo_semanal"] and self.rng_ops.random() < self.p["disciplina"]:
                self._conteo_botellas(lunes)
            generar_recomendaciones(self.negocio, hoy=lunes)
            recs = list(RecomendacionCompra.objects.filter(negocio=self.negocio, estado="PENDIENTE"))
            for orden in crear_ordenes_desde_recomendaciones(recs, self.dueno):
                enviar_orden(orden, self.dueno, fecha=self._momento(lunes, 10))
                self.llegadas[lunes + timedelta(days=self.rng_ops.randint(1, 3))].append(orden.pk)
        if self.fid and self.rng.random() < self.p["revisa"]:
            self._mensajes(lunes)

    def _llegan_compras(self, dia):
        from apps.compras.models import OrdenCompra
        from apps.compras.services import recibir_todo

        for pk in self.llegadas.pop(dia, []):
            orden = OrdenCompra.objects.get(pk=pk)
            for d in orden.detalles.all():
                self.fisico[d.producto_id] += float(d.cantidad_pedida)
            if self.rng_ops.random() < self.p["disciplina"] + (1 - self.p["disciplina"]) * 0.4:
                with sin_evaluacion_automatica():
                    recibir_todo(orden, self.dueno, fecha=self._momento(dia, 14))
            else:
                self.m.compras_no_registradas += 1

    def _conteo_botellas(self, dia):
        conteo = crear_conteo(self.negocio, self.dueno, productos=self.botellas + self.insumos)
        for d in conteo.detalles.select_related("producto"):
            real = round(self.fisico[d.producto_id], 1)  # método de décimos
            if abs(real - float(d.stock_sistema)) >= 0.1:
                d.stock_contado, d.motivo = Decimal(str(real)), "Conteo semanal de botellas"
                d.save(update_fields=["stock_contado", "motivo"])
        enviar_conteo(conteo, self.dueno)
        aprobar_conteo(conteo, self.dueno, fecha=self._momento(dia, 12))
        self.m.conteos += 1

    def _mensajes(self, lunes):
        """El dueño envía los recordatorios (botellas por vencer, a una visita del bono) y una oferta de regreso."""
        from apps.clientes.models import EnvioOferta
        from apps.clientes.services import destinatarios, registrar_envio
        from apps.clientes.sugerencias import crear_desde_sugerencia, sugerir
        from apps.nocturno.fidelizacion import recordatorios

        inverso = {c.pk: persona for persona, c in self.cliente_de.items()}
        for r in recordatorios(self.negocio, hoy=lunes):
            persona = inverso.get(r["cliente"].pk)
            if persona is not None:
                self.boost_hasta[persona] = lunes + timedelta(days=7)
                self.m.recordatorios += 1
        for s in sugerir(self.negocio, hoy=lunes):
            if s["clave"].startswith(tuple(self.p.get("ofertas_que_usa", ["regreso"]))):
                oferta = crear_desde_sugerencia(self.negocio, s["clave"], self.dueno, hoy=lunes)
                if oferta is None:
                    continue
                for c in destinatarios(oferta, hoy=lunes)[:60]:
                    registrar_envio(oferta, c, self.dueno)
                    EnvioOferta.objects.filter(oferta=oferta, cliente=c).update(fecha=self._momento(lunes, 11))
                    persona = inverso.get(c.pk)
                    if persona is not None:
                        self.boost_hasta[persona] = lunes + timedelta(days=10)
                        self.m.ofertas_enviadas += 1

    # ------------------------------------------------------------------ cierre
    def cerrar(self):
        noc.vencer_botellas(self.negocio, hoy=self.inicio + timedelta(days=self.dias))
        noc.reservas_vencidas(self.negocio, hoy=self.inicio + timedelta(days=self.dias))
        return self

    def resumen(self) -> dict:
        from django.db.models import F, Sum

        from apps.clientes.models import MovimientoPuntos
        from apps.nocturno import analisis
        from apps.ventas.models import DetalleVenta, Venta

        hoy = self.inicio + timedelta(days=self.dias)
        ventas = Venta.objects.filter(negocio=self.negocio, estado="COMPLETADA")
        agg = DetalleVenta.objects.filter(venta__in=ventas).aggregate(
            ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")), costo=Sum(F("cantidad") * F("costo_unitario")))
        ingreso, costo = float(agg["ingreso"] or 0), float(agg["costo"] or 0)
        # licor que salió sin cobrarse: diferencia entre lo físico y lo que el sistema cree que salió
        merma_valor = sum(max(0.0, float(b.stock_actual) - self.fisico[b.pk]) * float(b.precio_compra)
                          for b in Producto.objects.filter(pk__in=[x.pk for x in self.botellas]))
        detectada = sum(float(f["valor_faltante"]) for f in analisis.rendimiento_botellas(self.negocio, dias=self.dias,
                                                                                            hoy=hoy))
        m = self.m
        visitas = list(m.visitas_por_persona.values())
        bonos = MovimientoPuntos.objects.filter(cliente__negocio=self.negocio, tipo="BONO")
        rs = analisis.reservas(self.negocio, dias=self.dias, hoy=hoy)
        pc = analisis.pour_cost(self.negocio, dias=self.dias, hoy=hoy)
        return {
            "clave": self.p["clave"], "negocio": self.p["negocio"], "giro": self.p["giro"], "dueno": self.p["dueno"],
            "fidelizacion": self.fid, "productos": len(self.por_pk), "noches": m.noches, "grupos": m.grupos,
            "personas": m.personas, "rechazados_aforo": m.rechazados_aforo,
            "ventas": round(ingreso), "utilidad": round(ingreso - costo),
            "utilidad_neta_merma": round(ingreso - costo - merma_valor - detectada),
            "propinas": float(ventas.aggregate(t=Sum("propina"))["t"] or 0),
            "ticket_persona": round(ingreso / m.personas) if m.personas else 0,
            "pour_cost": pc["pct"], "pour_cost_real": pc["real_pct"],
            "pour_categorias": {f["categoria"]: f["pct"] for f in pc["por_categoria"]},
            "sugerencias": [x["titulo"] for x in analisis.sugerencias(self.negocio, hoy=hoy)],
            "merma_no_detectada": round(merma_valor), "merma_detectada_conteos": round(detectada),
            "cortesias_sin_registro": m.cortesias_sin_registro, "perdidos_agotado": m.perdidos_agotado,
            "pedidos": m.pedidos, "happy_hour_lineas": DetalleVenta.objects.filter(venta__in=ventas,
                                                                                  promocion="Happy hour").count(),
            "cuentas_divididas": m.cuentas_divididas,
            "reservas": m.reservas, "no_show_pct": rs["no_show_pct"], "grupos_grandes": m.grupos_grandes,
            "consumo_persona_grupo": float(rs["consumo_por_persona_grupo"] or 0),
            "consumo_persona_otros": float(rs["consumo_por_persona_otros"] or 0),
            "clientes_registrados": len(self.cliente_de),
            "ventas_con_cliente_pct": round(100 * ventas.filter(cliente_ref__isnull=False).count() / max(1, ventas.count())),
            "personas_distintas": len(visitas),
            "vuelven_pct": round(100 * sum(1 for v in visitas if v >= 2) / max(1, len(visitas))),
            "visitas_por_cliente": round(sum(visitas) / max(1, len(visitas)), 2),
            "bonos_visita": bonos.filter(motivo__startswith="Visita").count(),
            "bonos_referido": bonos.filter(motivo__startswith="Trajo").count(),
            "bonos_grupo": bonos.filter(motivo__startswith="Grupo").count(),
            "botellas_guardadas": m.botellas_guardadas, "botellas_retiradas": m.botellas_retiradas,
            "recordatorios": m.recordatorios, "ofertas_enviadas": m.ofertas_enviadas,
            "compras_no_registradas": m.compras_no_registradas, "conteos": m.conteos,
            "costo_fidelizacion": {k: float(v or 0) for k, v in analisis.costo_fidelizacion(self.negocio, dias=self.dias,
                                                                                          hoy=hoy).items()},
            "cover_cobrado": float(sum(i.total for i in self.negocio.ingresos.all())),
        }


def ejecutar(perfil, dias=60, semilla=7, fidelizacion=True) -> dict:
    inicio = timezone.localdate() - timedelta(days=dias)
    sim = SimuladorNocturno(perfil, inicio, dias, semilla, fidelizacion).crear()
    for n in range(dias):
        sim.simular_noche(n)
    return sim.cerrar().resumen()

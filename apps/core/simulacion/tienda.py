"""Simulador de una tienda con clientes habituales (ropa, vapeadores…): quién compra, cada cuánto y si la fidelización
lo hace volver. Todo pasa por los servicios reales (ventas, puntos, ofertas, compras, alertas).

La conducta de los clientes es un SUPUESTO:
- cada persona tiene una "lealtad" (qué parte de sus compras hace aquí y no en la competencia);
- una "sensibilidad" a la fidelización: a unos les mueven los puntos y las ofertas, a otros nada;
- en productos que se acaban (cartuchos, líquidos) la persona vuelve cuando se le acaban; en ropa, de vez en cuando
  y más en quincena.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Categoria, Marca, Producto
from apps.catalogo.services import generar_variantes
from apps.clientes.models import Cliente, EnvioOferta
from apps.clientes.services import ErrorClientes, destinatarios, registrar_envio
from apps.clientes.sugerencias import crear_desde_sugerencia, sugerir
from apps.core.models import Negocio
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento, sin_evaluacion_automatica
from apps.proveedores.models import ProductoProveedor, Proveedor
from apps.usuarios.models import Rol, Usuario
from apps.ventas.services import registrar_venta

TZ = timezone.get_current_timezone()


def cumpleanos(rng: random.Random, hoy: date, giro: str) -> date | None:
    """Fecha de nacimiento que da el cliente al registrarse (7 de cada 10 la dan); siempre mayor de edad."""
    if rng.random() >= 0.7:
        return None
    edad = rng.randint(19, 40 if giro == "VAPE" else 58)
    return date(hoy.year - edad, rng.randint(1, 12), rng.randint(1, 28))
# Supuestos: cuánto sube la probabilidad de comprar aquí (y no en otro lado) según la sensibilidad de la persona
EMPUJE = {"puntos": 0.06, "oferta": 0.25, "nivel": 0.05}


@dataclass
class Persona:
    lealtad: float          # parte de sus compras que hace aquí
    sensibilidad: float     # 0 = la fidelización no le mueve nada
    ritmo: float            # ropa: compras por mes; vape: días que le dura un cartucho/líquido
    talla: dict = field(default_factory=dict)
    equipo: int | None = None       # vape: qué pod usa (índice)
    proxima: date | None = None     # vape: cuándo se le acaba
    ofertas_hasta: date = date.min
    registrado: Cliente | None = None


@dataclass
class Metricas:
    ventas: int = 0
    anonimas: int = 0
    perdidas_competencia: int = 0
    perdidas_agotado: int = 0
    ofertas_enviadas: int = 0
    canjes: int = 0
    registrados: int = 0


class SimuladorTienda:
    def __init__(self, perfil: dict, inicio: date, dias: int, semilla: int = 7):
        self.p, self.inicio, self.dias = perfil, inicio, dias
        self.rng = random.Random(f"{semilla}-{perfil['clave']}")
        self.m = Metricas()
        self.llegadas: dict[date, list] = defaultdict(list)

    # ------------------------------------------------------------------ montaje
    def crear(self):
        p = self.p
        with transaction.atomic(), sin_evaluacion_automatica():
            self.negocio = Negocio.objects.create(nombre=p["negocio"], giro=p["giro"], direccion=p["lugar"],
                                                  telefono=p.get("telefono", ""))
            nombre, *ap = p["dueno"].split()
            self.dueno = Usuario.objects.create_user(p["usuario"], password=p["clave_acceso"], first_name=nombre,
                                                     last_name=" ".join(ap), negocio=self.negocio, rol=Rol.ADMIN)
            self.vendedores = [self.dueno] + [
                Usuario.objects.create_user(f"{p['usuario']}-vendedor{i}", password=p["clave_acceso"],
                                            negocio=self.negocio, rol=Rol.VENDEDOR) for i in range(1, p.get("vendedores", 0) + 1)]
            self.proveedores = {clave: Proveedor.objects.create(negocio=self.negocio, nombre=nom, tiempo_entrega_dias=dias,
                                                                telefono=tel)
                                for clave, (nom, dias, tel) in p["proveedores"].items()}
            self._catalogo()
        self._personas()
        return self

    def _catalogo(self):
        cats = {c.nombre: c for c in Categoria.objects.filter(negocio=self.negocio)}
        for it in self.p["catalogo"]:
            if it["categoria"] not in cats:
                cats[it["categoria"]] = Categoria.objects.create(negocio=self.negocio, nombre=it["categoria"])
        fecha = self._momento(self.inicio - timedelta(days=1), 9)
        self.productos: list[Producto] = []
        self.info: dict[int, dict] = {}
        for i, it in enumerate(self.p["catalogo"]):
            marca, _ = Marca.objects.get_or_create(negocio=self.negocio, nombre=it["marca"])
            base = Producto.objects.create(
                negocio=self.negocio, sku=it["sku"], nombre=it["nombre"], categoria=cats[it["categoria"]], marca=marca,
                precio_compra=it["costo"], precio_venta=it["precio"], proveedor_principal=self.proveedores[it["proveedor"]],
                stock_minimo=it.get("minimo", 2), vida_util_dias=it.get("vida"), descripcion=it.get("descripcion", ""))
            variantes = [base]
            if it.get("variantes"):
                variantes = generar_variantes(base, it["variantes"], self.dueno)
            for v in variantes:
                ProductoProveedor.objects.create(proveedor=self.proveedores[it["proveedor"]], producto=v,
                                                 precio_compra=it["costo"], multiplo_empaque=it.get("empaque", 1))
                cant = self.rng.randint(*it["stock"])
                vence = self.inicio + timedelta(days=it["vida"]) if it.get("vida") else None
                registrar_movimiento(producto=v, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=cant, usuario=self.dueno,
                                     fecha=fecha, motivo="Inventario inicial", fecha_vencimiento=vence, evaluar_alertas=False)
                self.productos.append(v)
                self.info[v.pk] = {**it, "indice": i, "atributos": v.atributos}
        self.por_indice = defaultdict(list)
        for v in self.productos:
            self.por_indice[self.info[v.pk]["indice"]].append(v)

    def _personas(self):
        p, r = self.p, self.rng
        self.personas = []
        for _ in range(p["pool"]):
            per = Persona(lealtad=min(0.95, max(0.15, r.betavariate(*p["lealtad"]))),
                          sensibilidad=r.choices([0.0, 0.6, 1.6], weights=p["sensibilidad"])[0],
                          ritmo=r.uniform(*p["ritmo"]))
            if p["giro"] == "ROPA":
                per.talla = {"hombre": r.choice(["28", "30", "32", "34", "36"]), "mujer": r.choice(["26", "27", "28",
                                                                                                   "29", "30"]),
                             "camiseta": r.choice(["S", "M", "M", "L", "L", "XL"]), "genero": r.choice(["hombre", "mujer"])}
            else:
                per.equipo = r.choices(range(len(p["equipos"])), weights=[e[1] for e in p["equipos"]])[0]
                per.proxima = self.inicio + timedelta(days=r.randint(0, int(per.ritmo)))
            self.personas.append(per)

    # ------------------------------------------------------------------ utilidades
    def _momento(self, dia: date, hora: float) -> datetime:
        return timezone.make_aware(datetime.combine(dia, time(int(hora), int((hora % 1) * 60))), TZ)

    def _empuje(self, per: Persona, hoy: date) -> float:
        c = per.registrado
        if not c:
            return 0.0
        e = EMPUJE["puntos"] + (EMPUJE["nivel"] if c.nivel != "NUEVO" else 0)
        if per.ofertas_hasta >= hoy:
            e += EMPUJE["oferta"]
        return e * per.sensibilidad

    def _disponible(self, prod: Producto) -> bool:
        return Producto.objects.filter(pk=prod.pk, stock_actual__gt=0).exists()

    # ------------------------------------------------------------------ un día
    def simular_dia(self, n: int):
        dia = self.inicio + timedelta(days=n)
        self._llegan_compras(dia)
        if dia.weekday() == 0:
            self._semana(dia)
        if dia.weekday() in self.p.get("cierra", ()):
            return
        factor = self.p["dias_semana"][dia.weekday()]
        if self.p["giro"] == "ROPA" and (dia.day in (14, 15, 16, 29, 30, 31, 1)):
            factor *= 1.8  # quincena
        with sin_evaluacion_automatica(), transaction.atomic():
            for per in self.personas:
                self._decidir(per, dia, factor)
            for _ in range(round(self.p["anonimos"] * factor * self.rng.uniform(0.6, 1.4))):
                self._comprar(None, dia)

    def _decidir(self, per: Persona, dia: date, factor: float):
        r = self.rng
        if self.p["giro"] == "ROPA":
            if r.random() >= per.ritmo / 30 * factor / 1.3:
                return
        else:
            if dia < per.proxima:
                return
            per.proxima = dia + timedelta(days=max(2, round(per.ritmo * r.uniform(0.8, 1.2))))
        aqui = min(0.98, per.lealtad * (1 + self._empuje(per, dia)))
        if r.random() >= aqui:
            self.m.perdidas_competencia += 1
            return
        self._comprar(per, dia)

    def _canasta(self, per: Persona | None) -> list[Producto]:
        r, p = self.rng, self.p
        if p["giro"] == "ROPA":
            genero = per.talla["genero"] if per else r.choice(["hombre", "mujer"])
            opciones = [i for i, it in enumerate(p["catalogo"]) if it.get("para") in (genero, "todos")]
            elegidos = r.sample(opciones, k=min(len(opciones), r.choices([1, 2, 3], weights=[60, 30, 10])[0]))
            canasta = []
            for i in elegidos:
                variantes = self.por_indice[i]
                if per and variantes[0].atributos.get("Talla"):
                    clave = "camiseta" if p["catalogo"][i]["categoria"] in ("Camisas", "Chaquetas", "Accesorios") \
                        else genero
                    variantes = [v for v in variantes if v.atributos.get("Talla") == per.talla.get(clave)] or variantes
                canasta.append(r.choice(variantes))
            return canasta
        # vapeador: cartuchos de su equipo + líquido; a veces un equipo nuevo o un accesorio
        equipo = per.equipo if per else r.choices(range(len(p["equipos"])), weights=[e[1] for e in p["equipos"]])[0]
        _, _, repuesto = p["equipos"][equipo]
        canasta = [r.choice(self.por_indice[r.choice(repuesto)])]
        if r.random() < 0.8:
            canasta.append(r.choice(self.por_indice[r.choice(p["liquidos"])]))
        if r.random() < (0.06 if per else 0.25):
            canasta.append(self.por_indice[p["equipos"][equipo][0]][0])
        if r.random() < 0.05:
            canasta.append(r.choice(self.por_indice[r.choice(p["accesorios"])]))
        return canasta

    def _comprar(self, per: Persona | None, dia: date):
        r = self.rng
        lineas = []
        for prod in self._canasta(per):
            if self._disponible(prod):
                lineas.append({"producto": prod, "cantidad": 1})
                continue
            # agotado: en ropa prueba otro color de la misma talla; si no hay, se pierde esa prenda
            hermanos = [v for v in self.por_indice[self.info[prod.pk]["indice"]] if v.pk != prod.pk and
                        v.atributos.get("Talla") == prod.atributos.get("Talla") and self._disponible(v)]
            if hermanos and r.random() < 0.5:
                lineas.append({"producto": r.choice(hermanos), "cantidad": 1})
            else:
                self.m.perdidas_agotado += 1
        if not lineas:
            return
        cliente = self._registrar(per, dia) if per else None
        puntos = 0
        if cliente and cliente.puntos >= self.negocio.config.puntos_minimos_canje and r.random() < 0.3 * (
                1 + per.sensibilidad):
            puntos = cliente.puntos
        hora = r.uniform(*self.p["horario"])
        try:
            registrar_venta(negocio=self.negocio, vendedor=r.choice(self.vendedores), lineas=lineas,
                            medio_pago=r.choices(["EFECTIVO", "TARJETA", "TRANSFERENCIA"], weights=[45, 25, 30])[0],
                            fecha=self._momento(dia, hora), cliente_ref=cliente, puntos_canjear=puntos,
                            evaluar_alertas=False)
        except ErrorInventario:
            self.m.perdidas_agotado += 1
            return
        self.m.ventas += 1
        self.m.canjes += bool(puntos)
        if not cliente:
            self.m.anonimas += 1
        else:
            cliente.refresh_from_db()

    def _registrar(self, per: Persona, dia: date) -> Cliente | None:
        if per.registrado:
            return per.registrado
        if self.rng.random() >= self.p["adopcion"]:
            return None
        n = len([x for x in self.personas if x.registrado]) + 1
        c = Cliente.objects.create(
            negocio=self.negocio, nombre=f"Cliente {n}", telefono=f"31{self.p['prefijo']}{n:06d}", acepta_datos=True,
            acepta_ofertas=self.rng.random() < self.p["acepta_ofertas"], fecha_autorizacion=self._momento(dia, 10),
            mayor_edad_verificado=self.p["giro"] == "VAPE", fecha_nacimiento=cumpleanos(self.rng, dia, self.p["giro"]))
        Cliente.objects.filter(pk=c.pk).update(creado=self._momento(dia, 10))
        per.registrado = c
        self.m.registrados += 1
        return c

    # ------------------------------------------------------------------ la semana: compras y ofertas
    def _semana(self, lunes):
        from apps.compras.services import enviar_orden
        from apps.recomendaciones.models import RecomendacionCompra
        from apps.recomendaciones.services import crear_ordenes_desde_recomendaciones, generar_recomendaciones

        with sin_evaluacion_automatica(), transaction.atomic():
            generar_recomendaciones(self.negocio, hoy=lunes)
            recs = list(RecomendacionCompra.objects.filter(negocio=self.negocio, estado="PENDIENTE"))
            for orden in crear_ordenes_desde_recomendaciones(recs, self.dueno):
                enviar_orden(orden, self.dueno, fecha=self._momento(lunes, 10))
                self.llegadas[lunes + timedelta(days=orden.proveedor.tiempo_entrega_dias)].append(orden.pk)
        if self.rng.random() < self.p["revisa_ofertas"]:
            self._ofertas(lunes)

    def _llegan_compras(self, dia):
        from apps.compras.models import OrdenCompra
        from apps.compras.services import recibir_todo

        for pk in self.llegadas.pop(dia, []):
            with sin_evaluacion_automatica():
                recibir_todo(OrdenCompra.objects.get(pk=pk), self.dueno, fecha=self._momento(dia, 11))

    def _ofertas(self, lunes):
        """El dueño revisa las ofertas que le sugiere el sistema y envía las que usa esta tienda por WhatsApp."""
        de = {per.registrado.pk: per for per in self.personas if per.registrado}
        for s in sugerir(self.negocio, hoy=lunes):
            if not s["clave"].startswith(tuple(self.p["ofertas_que_usa"])):
                continue
            oferta = crear_desde_sugerencia(self.negocio, s["clave"], self.dueno, hoy=lunes)
            if oferta is None:
                continue
            for c in destinatarios(oferta, hoy=lunes)[:40]:
                try:
                    registrar_envio(oferta, c, self.dueno)
                except ErrorClientes:
                    continue
                EnvioOferta.objects.filter(oferta=oferta, cliente=c).update(fecha=self._momento(lunes, 11))
                self.m.ofertas_enviadas += 1
                if c.pk in de:
                    de[c.pk].ofertas_hasta = oferta.hasta

    def cerrar(self):
        from apps.alertas.motor import evaluar_negocio

        evaluar_negocio(self.negocio, hoy=self.inicio + timedelta(days=self.dias))
        return self

    def resumen(self) -> dict:
        m = self.m
        return {"negocio": self.p["negocio"], "ventas": m.ventas, "anonimas": m.anonimas, "registrados": m.registrados,
                "compras_en_competencia": m.perdidas_competencia, "perdidas_agotado": m.perdidas_agotado,
                "ofertas_enviadas": m.ofertas_enviadas, "canjes": m.canjes}


def ejecutar_tienda(perfil, dias=60, semilla=7) -> SimuladorTienda:
    inicio = timezone.localdate() - timedelta(days=dias)
    sim = SimuladorTienda(perfil, inicio, dias, semilla).crear()
    for n in range(dias):
        sim.simular_dia(n)
    return sim.cerrar()

"""Simulador del piloto: un negocio usando el sistema día a día.

Se modelan por separado el stock FÍSICO (lo que realmente hay en la estantería) y el stock del SISTEMA.
Divergen cuando el empresario no registra compras, daños o vencimientos, igual que en la vida real.
Todas las operaciones pasan por los servicios reales de la aplicación (ventas, compras, conteos,
recomendaciones, alertas), así que la simulación también pone a prueba el código.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.alertas.motor import evaluar_ajuste, evaluar_negocio, evaluar_producto
from apps.analitica.services import registrar_y_evaluar_pronosticos
from apps.catalogo.models import Categoria, Producto, UnidadMedida
from apps.compras.models import OrdenCompra
from apps.compras.services import enviar_orden, recibir_orden, registrar_compra_directa
from apps.core.models import Negocio
from apps.inventario.models import ConteoFisico, DetalleConteo, Lote, TipoMovimiento
from apps.inventario.services import (
    ErrorInventario,
    aprobar_conteo,
    crear_conteo,
    registrar_movimiento,
    retirar_lote_vencido,
    sin_evaluacion_automatica,
)
from apps.proveedores.models import ProductoProveedor, Proveedor
from apps.recomendaciones.models import RecomendacionCompra
from apps.recomendaciones.services import crear_ordenes_desde_recomendaciones, generar_recomendaciones
from apps.usuarios.models import Rol, Usuario
from apps.ventas.models import Venta
from apps.ventas.services import anular_venta, registrar_venta

from .catalogos import generar_catalogo

TZ = timezone.get_current_timezone()
FRECUENCIA_COMPRA = {"MINIMERCADO": 3, "ROPA": 14, "BELLEZA": 7, "FARMACIA": 3, "RESTAURANTE": 2, "GENERICO": 7}
FACTOR_DIA = [0.85, 0.9, 0.95, 1.0, 1.2, 1.45, 0.65]  # lunes … domingo
PROVEEDORES = [  # nombre, entrega prometida, entrega real (min, max), cumplimiento (fracción entregada)
    ("Distribuidora Andina", 3, (5, 9), 0.82),   # el "malo": promete 3 días y tarda casi el triple
    ("Mayorista del Sur", 4, (3, 5), 0.95),
    ("Comercializadora Nariño", 2, (2, 3), 0.97),
]
PROVEEDOR_NUEVO = ("Proveedor Confiable S.A.S.", 3, (2, 4), 0.99)


@dataclass
class Metricas:
    tickets: int = 0
    lineas_vendidas: int = 0
    ventas_perdidas_sin_stock: int = 0          # el cliente pidió y no había en la estantería
    ventas_bloqueadas_sistema: int = 0          # había físico pero el sistema decía que no
    bloqueos_resueltos_con_ajuste: int = 0
    ventas_no_registradas: int = 0
    errores_digitacion: int = 0
    errores_detectados: int = 0
    errores_anulados: int = 0
    compras_no_registradas: int = 0
    compras_registradas_tarde: int = 0
    ordenes_por_recomendacion: int = 0
    ordenes_a_ojo: int = 0
    recomendaciones_editadas: int = 0
    unidades_danadas: float = 0
    danos_no_registrados: int = 0
    unidades_vencidas: float = 0
    valor_vencido: float = 0
    lotes_retirados_en_sistema: int = 0
    conteos: int = 0
    valor_diferencia_conteos: list = field(default_factory=list)
    dias_agotado_top: int = 0                   # producto-días sin stock físico en el 20 % más vendido
    dias_top_total: int = 0
    cambio_proveedor: dict = field(default_factory=dict)
    entregas: list = field(default_factory=list)  # (proveedor, prometido, real, cumplimiento)
    fricciones: list = field(default_factory=list)


class SimuladorNegocio:
    def __init__(self, perfil: dict, inicio: date, dias: int, semilla: int = 7):
        self.p = perfil
        self.rng = random.Random(f"{semilla}-{perfil['clave']}")
        self.inicio, self.dias = inicio, dias
        self.m = Metricas()
        self.fisico: dict[int, float] = {}
        self.lotes_fisicos: dict[int, list[list]] = defaultdict(list)  # pid -> [[cantidad, vence]]
        self.peso: dict[int, float] = {}
        self.vida: dict[int, int | None] = {}
        self.llegadas: dict[date, list] = defaultdict(list)
        self.pendientes_registro: dict[date, list] = defaultdict(list)
        self.perfil_prov: dict[int, tuple] = {}

    # ------------------------------------------------------------------ configuración inicial
    def crear(self):
        p = self.p
        with transaction.atomic():
            self.negocio = Negocio.objects.create(nombre=p["negocio"], giro=p["giro"], direccion=p["lugar"])
            s = self.negocio.suscripcion
            s.prueba_hasta = self.inicio + timedelta(days=self.dias + 14)
            s.save()
            nombre, *apellidos = p["dueno"].split()
            self.dueno = Usuario.objects.create_user(
                p["clave"], password="PilotoSimulado2026!", first_name=nombre, last_name=" ".join(apellidos),
                email=f"{p['clave']}@piloto.example", negocio=self.negocio, rol=Rol.ADMIN)
            self.vendedores = [self.dueno] + [
                Usuario.objects.create_user(f"{p['clave']}-emp{i}", password="PilotoSimulado2026!",
                                            first_name=f"Empleado {i}", negocio=self.negocio,
                                            rol=Rol.VENDEDOR if i % 2 else Rol.INVENTARIO)
                for i in range(1, p["empleados"] + 1)]
            self._proveedores()
            self._catalogo()
            self._stock_inicial()
        return self

    def _proveedores(self):
        self.proveedores = []
        for nombre, prometido, real, cumplimiento in PROVEEDORES:
            prov = Proveedor.objects.create(negocio=self.negocio, nombre=nombre, tiempo_entrega_dias=prometido,
                                            contacto="Asesor comercial", whatsapp="573000000000")
            self.perfil_prov[prov.pk] = (prometido, real, cumplimiento)
            self.proveedores.append(prov)

    def _catalogo(self):
        unidades = {u.abreviatura: u for u in UnidadMedida.objects.all()}
        categorias = {c.nombre: c for c in Categoria.objects.filter(negocio=self.negocio)}
        items = generar_catalogo(self.p["giro"], self.p["productos"], self.rng)
        # cada categoría la surte un proveedor; se reparten en orden para que los tres tengan productos
        orden_cat = {c: i for i, c in enumerate(sorted({it["categoria"] for it in items}))}
        self.productos: list[Producto] = []
        for i, it in enumerate(items):
            cat = categorias.get(it["categoria"]) or Categoria.objects.get_or_create(
                negocio=self.negocio, nombre=it["categoria"])[0]
            categorias[cat.nombre] = cat
            prov = self.proveedores[orden_cat[it["categoria"]] % 3]
            margen = self.rng.uniform(1.18, 1.6)
            if "variantes" in it:  # ropa: agrupador + variantes
                padre = Producto.objects.create(
                    negocio=self.negocio, sku=f"F{i:04d}", nombre=it["familia"], categoria=cat, es_agrupador=True,
                    precio_compra=it["costo"], precio_venta=round(it["costo"] * margen, -2), proveedor_principal=prov,
                    unidad=unidades.get(it["unidad"]))
                for j, v in enumerate(it["variantes"]):
                    self.productos.append(Producto(
                        negocio=self.negocio, padre=padre, sku=f"F{i:04d}-{j:02d}",
                        nombre=f"{it['familia']} · {v['Talla']} · {v['Color']}", categoria=cat, atributos=v,
                        precio_compra=it["costo"], precio_venta=padre.precio_venta, stock_minimo=1,
                        proveedor_principal=prov, unidad=unidades.get(it["unidad"])))
                    self.vida[len(self.productos) - 1] = None
                continue
            self.productos.append(Producto(
                negocio=self.negocio, sku=f"P{i:04d}", nombre=it["nombre"], categoria=cat,
                precio_compra=it["costo"], precio_venta=round(it["costo"] * margen, -1), stock_minimo=0,
                proveedor_principal=prov, unidad=unidades.get(it["unidad"])))
            self.vida[len(self.productos) - 1] = it["vida"]
        Producto.objects.bulk_create(self.productos, batch_size=500)
        self.productos = list(Producto.objects.filter(negocio=self.negocio, es_agrupador=False).order_by("sku"))
        vidas = list(self.vida.values())
        self.vida = {p.pk: vidas[i] for i, p in enumerate(self.productos)}
        ProductoProveedor.objects.bulk_create([
            ProductoProveedor(proveedor_id=p.proveedor_principal_id, producto=p, precio_compra=p.precio_compra,
                              multiplo_empaque=6 if p.unidad and p.unidad.abreviatura == "und" and self.rng.random() < .3
                              else 1) for p in self.productos])
        # Popularidad tipo Zipf: pocos productos venden mucho, la mayoría poco
        orden = list(self.productos)
        self.rng.shuffle(orden)
        lineas_dia = self.p["tickets"] * 1.8
        pesos = [1 / (r + 1) ** 0.95 for r in range(len(orden))]
        total = sum(pesos)
        for prod, w in zip(orden, pesos, strict=True):
            self.peso[prod.pk] = w / total * lineas_dia  # unidades por día esperadas
        top = sorted(self.peso, key=self.peso.get, reverse=True)
        self.top = set(top[: max(1, len(top) // 5)])
        self.lista_pids = [p.pk for p in self.productos]
        self.lista_pesos = [self.peso[p.pk] for p in self.productos]
        self.por_pk = {p.pk: p for p in self.productos}

    def _stock_inicial(self):
        fecha = self._momento(self.inicio - timedelta(days=1), 7)
        with sin_evaluacion_automatica():
            for prod in self.productos:
                diario = self.peso[prod.pk]
                cantidad = max(2, math.ceil(diario * self.rng.uniform(8, 25))) if self.p["giro"] != "ROPA" else \
                    self.rng.randint(1, 5)
                if self.vida.get(prod.pk):  # un perecedero no se tiene en estantería más allá de su vida útil
                    cantidad = max(1, min(cantidad, math.ceil(diario * self.vida[prod.pk] * 0.7)))
                prod.stock_minimo = max(1, round(diario * self.rng.uniform(2, 5)))
                Producto.objects.filter(pk=prod.pk).update(stock_minimo=prod.stock_minimo)
                vida = self.vida.get(prod.pk) or 60
                edad = self.rng.randint(0, max(0, min(20, vida // 3)))  # mercancía ya en la estantería
                vence = self._vencimiento(prod.pk, self.inicio - timedelta(days=edad))
                registrar_movimiento(producto=prod, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=cantidad,
                                     usuario=self.dueno, fecha=fecha, motivo="Inventario inicial", fecha_vencimiento=vence,
                                     evaluar_alertas=False)
                self.fisico[prod.pk] = float(cantidad)
                self.lotes_fisicos[prod.pk].append([float(cantidad), vence])

    # ------------------------------------------------------------------ utilidades
    def _momento(self, dia: date, hora: int) -> datetime:
        return timezone.make_aware(datetime(dia.year, dia.month, dia.day, hora, self.rng.randint(0, 59)), TZ)

    def _vencimiento(self, pid, desde: date):
        vida = self.vida.get(pid)
        return desde + timedelta(days=vida) if vida else None

    def _sacar_fisico(self, pid, cantidad):
        self.fisico[pid] = max(0.0, self.fisico[pid] - cantidad)
        restante = cantidad
        for lote in sorted(self.lotes_fisicos[pid], key=lambda x: (x[1] is None, x[1] or date.max)):
            tomar = min(lote[0], restante)
            lote[0] -= tomar
            restante -= tomar
            if restante <= 0:
                break
        self.lotes_fisicos[pid] = [lote for lote in self.lotes_fisicos[pid] if lote[0] > 1e-9]

    def _entero(self, prod, cantidad):
        fraccion = prod.unidad and prod.unidad.permite_decimales and self.negocio.config.permite_fracciones
        return round(cantidad, 1) if fraccion else max(1, round(cantidad))

    # ------------------------------------------------------------------ un día de trabajo
    def simular_dia(self, n: int):
        dia = self.inicio + timedelta(days=n)
        with sin_evaluacion_automatica(), transaction.atomic():
            self._registros_atrasados(dia)
            self._llegadas(dia)
            errores_hoy = self._ventas(dia)
            self._mermas(dia)
            self._vencimientos(dia, revisa=(n % 7 == 6 and self.rng.random() < self.p["revisa_alertas"]))
            if self.p["cambia_proveedor"] == n:
                self._cambiar_proveedor(dia)
            if n % FRECUENCIA_COMPRA[self.p["giro"]] == 0:
                self._comprar(dia)
            if self.p["conteo"] and n in (29, 58):
                self._conteo(dia)
        self._revisar_errores(dia, errores_hoy)
        if n in (14, 45):
            registrar_y_evaluar_pronosticos(self.negocio, hoy=dia)
        for pid in self.top:
            self.m.dias_top_total += 1
            if self.fisico[pid] <= 0:
                self.m.dias_agotado_top += 1

    def _ventas(self, dia):
        esperado = self.p["tickets"] * FACTOR_DIA[dia.weekday()] * self.rng.uniform(0.85, 1.15)
        tickets = max(0, round(self.rng.gauss(esperado, math.sqrt(esperado))))
        errores = []
        for _ in range(tickets):
            n_lineas = self.rng.choices([1, 2, 3, 4], weights=[45, 30, 15, 10])[0]
            elegidos = set(self.rng.choices(self.lista_pids, weights=self.lista_pesos, k=n_lineas))
            lineas_reales, lineas_sistema = [], []
            for pid in elegidos:
                prod = self.por_pk[pid]
                cant = self._entero(prod, self.rng.choice([1, 1, 1, 2, 2, 3]) *
                                    (self.rng.uniform(0.5, 2.5) if prod.unidad and prod.unidad.permite_decimales else 1))
                if self.fisico[pid] < cant:
                    self.m.ventas_perdidas_sin_stock += 1
                    continue
                cant_sistema = cant
                if self.rng.random() < self.p["error_digitacion"]:
                    cant_sistema = cant * 10
                    errores.append(pid)
                lineas_reales.append((pid, cant))
                lineas_sistema.append({"producto": prod, "cantidad": Decimal(str(cant_sistema))})
            if not lineas_reales:
                continue
            self.m.tickets += 1
            for pid, cant in lineas_reales:
                self._sacar_fisico(pid, cant)
                self.m.lineas_vendidas += 1
            vendedor = self.rng.choice(self.vendedores)
            self._registrar_venta(dia, vendedor, lineas_sistema, errores)
        return errores

    def _registrar_venta(self, dia, vendedor, lineas, errores):
        fecha = self._momento(dia, self.rng.randint(8, 20))
        medio = self.rng.choices(list(Venta.MedioPago.values), weights=[55, 30, 10, 5])[0]
        try:
            with transaction.atomic():
                venta = registrar_venta(negocio=self.negocio, vendedor=vendedor, lineas=lineas, fecha=fecha,
                                        medio_pago=medio)
            for linea in lineas:
                if linea["producto"].pk in errores:
                    self._ultima_venta_error = venta
            return
        except ErrorInventario:
            self.m.ventas_bloqueadas_sistema += 1
        # El sistema dice que no hay, pero en la estantería sí hay: ¿qué hace el empresario?
        if self.rng.random() < self.p["disciplina"] * 0.8:
            for linea in lineas:
                prod = Producto.objects.get(pk=linea["producto"].pk)
                faltan = linea["cantidad"] - prod.stock_actual
                if faltan > 0:
                    registrar_movimiento(producto=prod, tipo=TipoMovimiento.ENTRADA_AJUSTE, cantidad=faltan,
                                         usuario=vendedor, fecha=fecha, motivo="Mercancía que no estaba registrada")
            registrar_venta(negocio=self.negocio, vendedor=vendedor, lineas=lineas, fecha=fecha, medio_pago="EFECTIVO")
            self.m.bloqueos_resueltos_con_ajuste += 1
        else:
            self.m.ventas_no_registradas += 1
        for linea in lineas:
            if linea["producto"].pk in errores:
                errores.remove(linea["producto"].pk)  # el error no llegó al sistema

    def _revisar_errores(self, dia, errores):
        """La noche del error: ¿el sistema lo detecta? ¿el empresario lo corrige?"""
        for pid in set(errores):
            self.m.errores_digitacion += 1
            alertas = evaluar_producto(pid, hoy=dia)
            if any(a.tipo == Alerta.Tipo.ANOMALIA for a in alertas):
                self.m.errores_detectados += 1
                if self.rng.random() < self.p["revisa_alertas"]:
                    venta = Venta.objects.filter(negocio=self.negocio, detalles__producto_id=pid,
                                                 fecha__date=dia).order_by("-detalles__cantidad").first()
                    if venta and venta.estado == Venta.Estado.COMPLETADA:
                        with sin_evaluacion_automatica():
                            anular_venta(venta, self.dueno, "Error de digitación en la cantidad",
                                         fecha=self._momento(dia, 21))
                        Alerta.objects.filter(producto_id=pid, tipo=Alerta.Tipo.ANOMALIA).update(
                            estado=Alerta.Estado.RESUELTA, nota="Error de digitación; venta anulada y repetida")
                        self.m.errores_anulados += 1

    def _mermas(self, dia):
        for pid in self.rng.sample(self.lista_pids, k=max(1, len(self.lista_pids) // 25)):
            if self.fisico[pid] > 0 and self.rng.random() < self.p["merma"] * 25:
                prod = self.por_pk[pid]
                cant = self._entero(prod, self.rng.uniform(0.3, 2))
                cant = min(cant, self.fisico[pid])
                if cant <= 0:
                    continue
                self._sacar_fisico(pid, cant)
                self.m.unidades_danadas += cant
                if self.rng.random() < self.p["disciplina"]:
                    try:
                        movs = registrar_movimiento(producto=prod, tipo=TipoMovimiento.SALIDA_DANADO, cantidad=cant,
                                                    usuario=self.dueno, fecha=self._momento(dia, 19),
                                                    motivo=self.rng.choice(["Empaque roto", "Se dañó en bodega",
                                                                            "Devuelto por cliente en mal estado"]))
                        for mov in movs:
                            evaluar_ajuste(mov.pk)
                    except ErrorInventario:
                        self.m.danos_no_registrados += 1
                else:
                    self.m.danos_no_registrados += 1

    def _vencimientos(self, dia, revisa):
        for pid, lotes in self.lotes_fisicos.items():
            for lote in lotes:
                if lote[1] and lote[1] < dia and lote[0] > 0:
                    self.m.unidades_vencidas += lote[0]
                    self.m.valor_vencido += lote[0] * float(self.por_pk[pid].precio_compra)
                    self.fisico[pid] = max(0.0, self.fisico[pid] - lote[0])
                    lote[0] = 0
        if revisa:
            for lote in Lote.objects.filter(producto__negocio=self.negocio, cantidad__gt=0, fecha_vencimiento__lt=dia):
                try:
                    retirar_lote_vencido(lote, self.dueno, fecha=self._momento(dia, 18))
                    self.m.lotes_retirados_en_sistema += 1
                except ErrorInventario:
                    pass

    # ------------------------------------------------------------------ compras
    def _comprar(self, dia):
        if self.rng.random() < self.p["sigue_sistema"]:
            generar_recomendaciones(self.negocio, hoy=dia)
            recs = list(RecomendacionCompra.objects.filter(negocio=self.negocio, estado="PENDIENTE")
                        .select_related("producto", "proveedor"))
            cantidades = {}
            for r in recs:
                if self.rng.random() < 0.25:  # el empresario ajusta algunas cantidades
                    cantidades[r.pk] = max(1, round(r.cantidad_sugerida * self.rng.uniform(0.6, 1.3)))
                    self.m.recomendaciones_editadas += 1
            ordenes = crear_ordenes_desde_recomendaciones(recs, self.dueno, cantidades)
            for orden in ordenes:
                self._enviar(orden, dia)
                self.m.ordenes_por_recomendacion += 1
        else:  # compra "a ojo": mira la estantería y pide lo que ve bajo
            por_proveedor = defaultdict(list)
            for prod in self.productos:
                if self.fisico[prod.pk] <= prod.stock_minimo and self.rng.random() < 0.7:
                    cant = max(1, math.ceil(prod.stock_minimo * self.rng.uniform(1.5, 3)))
                    por_proveedor[prod.proveedor_principal_id].append((prod, cant))
            for prov_id, lineas in por_proveedor.items():
                prometido, (dmin, dmax), cumplimiento = self.perfil_prov[prov_id]
                llegada = dia + timedelta(days=self.rng.randint(dmin, dmax))
                self.llegadas[llegada].append(("directa", prov_id, lineas, cumplimiento))
                self.m.ordenes_a_ojo += 1

    def _enviar(self, orden, dia):
        enviar_orden(orden, self.dueno, fecha=self._momento(dia, 9))
        OrdenCompra.objects.filter(pk=orden.pk).update(creado=self._momento(dia, 8))
        prometido, (dmin, dmax), cumplimiento = self.perfil_prov[orden.proveedor_id]
        llegada = dia + timedelta(days=self.rng.randint(dmin, dmax))
        self.llegadas[llegada].append(("orden", orden.pk, None, cumplimiento))

    def _llegadas(self, dia):
        for tipo, ref, lineas, cumplimiento in self.llegadas.pop(dia, []):
            if tipo == "orden":
                orden = OrdenCompra.objects.get(pk=ref)
                recibido = {}
                for d in orden.detalles.select_related("producto"):
                    cant = d.cantidad_pedida if self.rng.random() < cumplimiento else \
                        (d.cantidad_pedida * Decimal(str(self.rng.uniform(0.3, 0.8)))).quantize(Decimal("1"))
                    if cant > 0:
                        recibido[d.pk] = cant
                        self._entrar_fisico(d.producto_id, float(cant), dia)
                if self.rng.random() < self.p["disciplina"]:
                    self._recibir(orden, recibido, dia)
                elif self.rng.random() < 0.5:
                    self.pendientes_registro[dia + timedelta(days=self.rng.randint(1, 5))].append((orden.pk, recibido))
                else:
                    self.m.compras_no_registradas += 1
            else:
                prov = Proveedor.objects.get(pk=ref)
                reales = []
                for prod, cant in lineas:
                    cant = cant if self.rng.random() < cumplimiento else max(1, round(cant * 0.6))
                    self._entrar_fisico(prod.pk, float(cant), dia)
                    reales.append({"producto": prod, "cantidad": Decimal(str(cant)), "costo": prod.precio_compra,
                                   "vencimiento": self._vencimiento(prod.pk, dia)})
                if self.rng.random() < self.p["disciplina"]:
                    orden = registrar_compra_directa(negocio=self.negocio, proveedor=prov, usuario=self.dueno,
                                                     lineas=reales, numero_factura=f"F-{self.rng.randint(1000, 9999)}")
                    self._fechar_directa(orden, dia)
                else:
                    self.m.compras_no_registradas += 1

    def _entrar_fisico(self, pid, cant, dia):
        self.fisico[pid] += cant
        self.lotes_fisicos[pid].append([cant, self._vencimiento(pid, dia)])

    def _recibir(self, orden, recibido, dia):
        venc = {d.pk: self._vencimiento(d.producto_id, dia) for d in orden.detalles.all()}
        recibir_orden(orden, self.dueno, recibido, numero_factura=f"F-{self.rng.randint(1000, 9999)}",
                      vencimientos=venc, fecha=self._momento(dia, 10))
        orden.refresh_from_db()
        prometido = orden.proveedor.tiempo_entrega_dias
        if orden.estado == OrdenCompra.Estado.RECIBIDA_PARCIAL:
            # el proveedor no completó el pedido: el empresario lo cierra como recibido con lo que llegó
            OrdenCompra.objects.filter(pk=orden.pk).update(
                estado=OrdenCompra.Estado.RECIBIDA, fecha_recepcion=self._momento(dia, 10),
                dias_entrega=(dia - orden.fecha_envio.astimezone(TZ).date()).days)
            orden.refresh_from_db()
        self.m.entregas.append((orden.proveedor.nombre, prometido, orden.dias_entrega,
                                orden.estado == OrdenCompra.Estado.RECIBIDA))

    def _registros_atrasados(self, dia):
        for orden_pk, recibido in self.pendientes_registro.pop(dia, []):
            orden = OrdenCompra.objects.get(pk=orden_pk)
            if orden.estado in (OrdenCompra.Estado.ENVIADA, OrdenCompra.Estado.CONFIRMADA):
                self._recibir(orden, recibido, dia)
                self.m.compras_registradas_tarde += 1

    def _fechar_directa(self, orden, dia):
        OrdenCompra.objects.filter(pk=orden.pk).update(creado=self._momento(dia, 11))

    def _cambiar_proveedor(self, dia):
        malo = self.proveedores[0]
        nombre, prometido, real, cumplimiento = PROVEEDOR_NUEVO
        nuevo = Proveedor.objects.create(negocio=self.negocio, nombre=nombre, tiempo_entrega_dias=prometido,
                                         contacto="Nuevo asesor")
        self.perfil_prov[nuevo.pk] = (prometido, real, cumplimiento)
        productos = [p for p in self.productos if p.proveedor_principal_id == malo.pk]
        for p in productos:
            precio = (p.precio_compra * Decimal(str(self.rng.uniform(0.95, 1.06)))).quantize(Decimal("1"))
            ProductoProveedor.objects.create(proveedor=nuevo, producto=p, precio_compra=precio)
            p.proveedor_principal = nuevo
        Producto.objects.filter(pk__in=[p.pk for p in productos]).update(proveedor_principal=nuevo)
        pendientes = RecomendacionCompra.objects.filter(negocio=self.negocio, estado="PENDIENTE",
                                                        producto__in=productos)
        self.m.cambio_proveedor = {
            "dia": (dia - self.inicio).days, "de": malo.nombre, "a": nuevo.nombre, "productos": len(productos),
            "recomendaciones_con_proveedor_viejo": pendientes.filter(proveedor=malo).count(),
            "ordenes_abiertas_proveedor_viejo": OrdenCompra.objects.filter(
                proveedor=malo, estado__in=["ENVIADA", "CONFIRMADA"]).count(),
            "entrega_real_viejo": float(malo.tiempo_entrega_real()),
        }
        malo.activo = False
        malo.save(update_fields=["activo"])
        self.m.fricciones.append(f"Cambio de proveedor: {len(productos)} productos reasignados uno por uno "
                                 "(no existe cambio masivo en la interfaz)")

    # ------------------------------------------------------------------ conteo físico
    def _conteo(self, dia):
        conteo = crear_conteo(self.negocio, self.dueno)
        diferencia_valor = 0.0
        detalles = list(conteo.detalles.select_related("producto"))
        for d in detalles:
            real = Decimal(str(round(self.fisico[d.producto_id], 3)))
            if real != d.stock_sistema:
                d.stock_contado = real
                d.motivo = "Diferencia encontrada en el conteo mensual"
                diferencia_valor += float((real - d.stock_sistema) * d.producto.precio_compra)
        DetalleConteo.objects.bulk_update(detalles, ["stock_contado", "motivo"])
        ConteoFisico.objects.filter(pk=conteo.pk).update(estado=ConteoFisico.Estado.PENDIENTE_APROBACION)
        conteo.refresh_from_db()
        aprobar_conteo(conteo, self.dueno, fecha=self._momento(dia, 20))
        self.m.conteos += 1
        self.m.valor_diferencia_conteos.append(round(diferencia_valor))

    # ------------------------------------------------------------------ cierre
    def cerrar(self):
        fin = self.inicio + timedelta(days=self.dias - 1)
        registrar_y_evaluar_pronosticos(self.negocio, hoy=fin + timedelta(days=1))
        evaluar_negocio(self.negocio, hoy=fin)
        generar_recomendaciones(self.negocio, hoy=fin)
        self.stock_sistema_vs_fisico = self._divergencia()
        return self

    def _divergencia(self):
        dif, valor = 0, 0.0
        for p in Producto.objects.filter(negocio=self.negocio, es_agrupador=False):
            delta = float(p.stock_actual) - self.fisico[p.pk]
            if abs(delta) > 0.01:
                dif += 1
                valor += abs(delta) * float(p.precio_compra)
        return {"productos_con_diferencia": dif, "valor_diferencia": round(valor)}

    def resumen(self) -> dict:
        from django.db.models import Count, F, Sum

        from apps.analitica.services import precision_pronosticos
        from apps.ventas.models import DetalleVenta

        m = self.m
        det = DetalleVenta.objects.filter(venta__negocio=self.negocio, venta__estado=Venta.Estado.COMPLETADA)
        agg = det.aggregate(ingreso=Sum(F("cantidad") * F("precio_unitario")),
                            costo=Sum(F("cantidad") * F("costo_unitario")))
        ingreso, costo = float(agg["ingreso"] or 0), float(agg["costo"] or 0)
        mapes = [f["mape"] for f in precision_pronosticos(self.negocio)]
        mapes_top = [f["mape"] for f in precision_pronosticos(self.negocio) if f["producto"].pk in self.top]
        alertas = dict(Alerta.objects.filter(negocio=self.negocio, estado=Alerta.Estado.ABIERTA)
                       .values_list("tipo").annotate(n=Count("id")))
        cambio = self.p["cambia_proveedor"]
        entregas = defaultdict(list)
        for nombre, prometido, real, completa in m.entregas:
            entregas[nombre].append((prometido, real, completa))
        proveedores = {
            nombre: {"ordenes": len(v), "prometido": v[0][0],
                     "real_promedio": round(sum(r for _, r, _ in v if r is not None) / max(1, len(v)), 1),
                     "a_tiempo_pct": round(100 * sum(1 for pr, r, _ in v if r is not None and r <= pr) / len(v))}
            for nombre, v in entregas.items()}
        intentos = m.lineas_vendidas + m.ventas_perdidas_sin_stock
        return {
            "clave": self.p["clave"], "negocio": self.p["negocio"], "giro": self.p["giro"], "dueno": self.p["dueno"],
            "productos": len(self.productos), "dias": self.dias,
            "ventas": {"tickets": m.tickets, "ingreso": round(ingreso), "utilidad": round(ingreso - costo),
                       "margen_pct": round(100 * (ingreso - costo) / ingreso, 1) if ingreso else 0},
            "quiebres": {"lineas_perdidas": m.ventas_perdidas_sin_stock,
                         "pct_demanda_perdida": round(100 * m.ventas_perdidas_sin_stock / max(1, intentos), 1),
                         "pct_dias_agotado_top20": round(100 * m.dias_agotado_top / max(1, m.dias_top_total), 1)},
            "exactitud": {"ventas_bloqueadas_por_sistema": m.ventas_bloqueadas_sistema,
                          "resueltas_con_ajuste": m.bloqueos_resueltos_con_ajuste,
                          "ventas_no_registradas": m.ventas_no_registradas,
                          "compras_no_registradas": m.compras_no_registradas,
                          "compras_registradas_tarde": m.compras_registradas_tarde,
                          "danos_no_registrados": m.danos_no_registrados,
                          "conteos": m.conteos, "diferencia_conteos_valor": m.valor_diferencia_conteos,
                          **self.stock_sistema_vs_fisico},
            "errores": {"digitacion": m.errores_digitacion, "detectados": m.errores_detectados,
                        "anulados": m.errores_anulados},
            "compras": {"ordenes_por_recomendacion": m.ordenes_por_recomendacion, "ordenes_a_ojo": m.ordenes_a_ojo,
                        "recomendaciones_editadas": m.recomendaciones_editadas, "proveedores": proveedores},
            "vencimientos": {"unidades": round(m.unidades_vencidas, 1), "valor": round(m.valor_vencido),
                             "lotes_retirados_en_sistema": m.lotes_retirados_en_sistema},
            "mermas": {"unidades": round(m.unidades_danadas, 1)},
            "pronostico": {"productos_evaluados": len(mapes),
                           "mape_mediana": round(sorted(mapes)[len(mapes) // 2], 1) if mapes else None,
                           "mape_mediana_top20": round(sorted(mapes_top)[len(mapes_top) // 2], 1) if mapes_top else None},
            "alertas_abiertas": alertas,
            "recomendaciones_pendientes": RecomendacionCompra.objects.filter(negocio=self.negocio,
                                                                             estado="PENDIENTE").count(),
            "cambio_proveedor": m.cambio_proveedor if cambio is not None else None,
            "fricciones": m.fricciones,
        }

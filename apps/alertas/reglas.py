"""Reglas del motor de alertas. Para agregar una regla: crear la clase y añadirla a REGLAS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from apps.analitica import algoritmos as alg
from apps.analitica.models import DemandaDiaria
from apps.analitica.services import AnalisisProducto
from apps.catalogo.models import EstadoStock
from apps.core.formato import numero as _n

from .models import Alerta

S = Alerta.Severidad


@dataclass
class Hallazgo:
    tipo: str
    severidad: int
    mensaje: str
    accion_sugerida: str = ""
    datos: dict = field(default_factory=dict)




class Regla:
    def evaluar(self, a: AnalisisProducto, hoy: date) -> list[Hallazgo]:
        raise NotImplementedError


class ReglaAgotado(Regla):
    def evaluar(self, a, hoy):
        if a.estado == EstadoStock.AGOTADO:
            return [
                Hallazgo(Alerta.Tipo.AGOTADO, S.ACTUAR, f"{a.producto.nombre} está agotado.", "Reponer de inmediato")
            ]
        return []


class ReglaStockMinimo(Regla):
    def evaluar(self, a, hoy):
        p = a.producto
        if a.stock <= 0 or a.stock > float(p.stock_minimo):
            return []
        if a.stock <= float(p.stock_minimo) / 2:
            return [
                Hallazgo(
                    Alerta.Tipo.STOCK_CRITICO,
                    S.ACTUAR,
                    f"{p.nombre} en nivel crítico ({_n(a.stock)} de {_n(float(p.stock_minimo))} mínimo).",
                    "Revisar pedido sugerido",
                )
            ]
        return [
            Hallazgo(
                Alerta.Tipo.STOCK_BAJO,
                S.REVISAR,
                f"{p.nombre} está por debajo del mínimo ({_n(a.stock)} de {_n(float(p.stock_minimo))}).",
                "Programar reposición",
            )
        ]


class ReglaRiesgoAgotamiento(Regla):
    """La regla 'inteligente': relaciona stock + ritmo de ventas + tiempo de entrega."""

    def evaluar(self, a, hoy):
        if a.cobertura_dias is None or a.stock <= 0:
            return []
        margen = a.tiempo_entrega + 2
        if a.cobertura_dias >= margen:
            return []
        severidad = S.ACTUAR if a.cobertura_dias < a.tiempo_entrega else S.REVISAR
        msg = (
            f"Tienes {_n(a.stock)} unidades de {a.producto.nombre}, vendes aproximadamente "
            f"{_n(a.demanda_diaria)} por día y tu proveedor tarda {_n(a.tiempo_entrega)} días. "
            f"Podría agotarse en ~{_n(a.cobertura_dias)} días."
        )
        return [
            Hallazgo(
                Alerta.Tipo.RIESGO_AGOTAMIENTO,
                severidad,
                msg,
                "Revisar pedido sugerido",
                {"cobertura_dias": round(a.cobertura_dias, 1)},
            )
        ]


class ReglaVencimiento(Regla):
    def evaluar(self, a, hoy):
        config = getattr(a.producto.negocio, "config", None)
        if not config or not config.usa_vencimientos:
            return []
        hallazgos = []
        for lote in a.producto.lotes.filter(cantidad__gt=0, fecha_vencimiento__isnull=False):
            dias = lote.dias_para_vencer(hoy)
            if dias < 0:
                hallazgos.append(
                    Hallazgo(
                        Alerta.Tipo.VENCIDO,
                        S.ACTUAR,
                        f"{_n(float(lote.cantidad))} u. de {a.producto.nombre} vencieron el {lote.fecha_vencimiento:%d/%m}.",
                        "Retirar y registrar salida por vencimiento",
                        {"lote": lote.pk},
                    )
                )
            elif dias <= config.dias_vencimiento_amarillo:
                sev = S.ACTUAR if dias <= config.dias_vencimiento_rojo else S.REVISAR
                hallazgos.append(
                    Hallazgo(
                        Alerta.Tipo.VENCIMIENTO,
                        sev,
                        f"{_n(float(lote.cantidad))} u. de {a.producto.nombre} vencen en {dias} días "
                        f"({lote.fecha_vencimiento:%d/%m}).",
                        "Considere priorizar su venta",
                        {"lote": lote.pk, "dias": dias},
                    )
                )
        return hallazgos


class ReglaBajaRotacion(Regla):
    def evaluar(self, a, hoy):
        if a.rotacion != "BAJA" or a.stock <= 0:
            return []
        valor = a.stock * float(a.producto.precio_compra)
        if a.dias_desde_ultima_venta is None:
            cuando = "no registra ventas"
        elif a.dias_desde_ultima_venta >= 30:
            cuando = f"no se vende hace {a.dias_desde_ultima_venta} días"
        else:
            cuando = "se vende muy poco"
        return [
            Hallazgo(
                Alerta.Tipo.BAJA_ROTACION,
                S.REVISAR,
                f"{a.producto.nombre} {cuando} (${_n(valor)} inmovilizados).",
                "Promoción, combo o dejar de reponer",
                {"valor_inmovilizado": valor},
            )
        ]


class ReglaExceso(Regla):
    def evaluar(self, a, hoy):
        if a.estado == EstadoStock.EXCESO:
            return [
                Hallazgo(
                    Alerta.Tipo.EXCESO,
                    S.INFO,
                    f"{a.producto.nombre} tiene inventario para ~{_n(a.cobertura_dias)} días.",
                    "Evitar nuevas compras por ahora",
                )
            ]
        return []


class ReglaAnomaliaVentas(Regla):
    """Detecta, no acusa: compara las ventas de hoy contra el histórico del producto."""

    def evaluar(self, a, hoy):
        hist = list(
            DemandaDiaria.objects.filter(producto=a.producto, fecha__lt=hoy, cantidad__gt=0)
            .order_by("-fecha")
            .values_list("cantidad", flat=True)[:30]
        )
        hoy_reg = DemandaDiaria.objects.filter(producto=a.producto, fecha=hoy).first()
        if not hoy_reg or len(hist) < 5:
            return []
        valor, historia = float(hoy_reg.cantidad), [float(x) for x in hist]
        if not alg.es_anomalo(valor, historia):
            return []
        normal = sorted(historia)[len(historia) // 2]
        return [
            Hallazgo(
                Alerta.Tipo.ANOMALIA,
                S.REVISAR,
                f"Movimiento inusual en {a.producto.nombre}: {_n(valor)} u. vendidas hoy (lo normal es ~{_n(normal)}).",
                "Verificar: venta excepcional, error de digitación o pérdida",
                {"valor": valor, "normal": normal},
            )
        ]


REGLAS: list[Regla] = [
    ReglaAgotado(),
    ReglaStockMinimo(),
    ReglaRiesgoAgotamiento(),
    ReglaVencimiento(),
    ReglaBajaRotacion(),
    ReglaExceso(),
    ReglaAnomaliaVentas(),
]

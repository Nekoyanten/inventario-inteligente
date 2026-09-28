"""Silenciar alertas por tipo (y opcionalmente por categoría). Guardado en la configuración del negocio."""

from .models import Alerta

SILENCIABLES = {Alerta.Tipo.BAJA_ROTACION, Alerta.Tipo.EXCESO, Alerta.Tipo.STOCK_BAJO, Alerta.Tipo.VENCIMIENTO}


def esta_silenciada(config, tipo: str, categoria_id) -> bool:
    for regla in (getattr(config, "alertas_silenciadas", None) or []):
        if regla.get("tipo") == tipo and regla.get("categoria") in (None, categoria_id):
            return True
    return False


def silenciar(negocio, usuario, tipo: str, categoria_id=None) -> int:
    """Agrega la regla y descarta las alertas abiertas que coinciden. Devuelve cuántas se cerraron."""
    from apps.core.auditoria import auditar

    if tipo not in SILENCIABLES:
        raise ValueError("Este tipo de alerta no se puede silenciar.")
    config = negocio.config
    reglas = [r for r in (config.alertas_silenciadas or []) if not (r.get("tipo") == tipo and
                                                                    r.get("categoria") == categoria_id)]
    reglas.append({"tipo": tipo, "categoria": categoria_id})
    config.alertas_silenciadas = reglas
    config.save(update_fields=["alertas_silenciadas", "actualizado"])
    qs = Alerta.objects.filter(negocio=negocio, tipo=tipo, estado__in=[Alerta.Estado.ABIERTA, Alerta.Estado.VISTA])
    if categoria_id is not None:
        qs = qs.filter(producto__categoria_id=categoria_id)
    n = qs.update(estado=Alerta.Estado.DESCARTADA, resuelta_por=usuario, nota="Silenciada")
    auditar(negocio, usuario, "silenciar_alertas", config, tipo=tipo, categoria=categoria_id)
    return n


def reactivar(negocio, usuario, tipo: str, categoria_id=None):
    from apps.core.auditoria import auditar

    config = negocio.config
    config.alertas_silenciadas = [r for r in (config.alertas_silenciadas or [])
                                  if not (r.get("tipo") == tipo and r.get("categoria") == categoria_id)]
    config.save(update_fields=["alertas_silenciadas", "actualizado"])
    auditar(negocio, usuario, "reactivar_alertas", config, tipo=tipo, categoria=categoria_id)


def describir(negocio) -> list[dict]:
    from apps.catalogo.models import Categoria

    reglas = negocio.config.alertas_silenciadas or []
    nombres = dict(Categoria.objects.filter(negocio=negocio, pk__in=[r["categoria"] for r in reglas if r.get("categoria")])
                   .values_list("pk", "nombre"))
    return [{**r, "etiqueta": Alerta.Tipo(r["tipo"]).label,
             "categoria_nombre": nombres.get(r.get("categoria"), "todas las categorías")} for r in reglas]

from .models import RegistroAuditoria


def auditar(negocio, usuario, accion, instancia, **detalle):
    """Registra una acción en la bitácora de auditoría."""
    return RegistroAuditoria.objects.create(
        negocio=negocio,
        usuario=usuario,
        accion=accion,
        entidad=instancia.__class__.__name__,
        entidad_id=str(instancia.pk),
        detalle=detalle,
    )

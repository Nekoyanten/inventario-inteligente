def negocio(request):
    """Expone el negocio y su configuración a todas las plantillas."""
    neg = getattr(request, "negocio", None)
    return {"negocio": neg, "config_negocio": getattr(neg, "config", None) if neg else None}

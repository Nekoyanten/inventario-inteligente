"""Exportación genérica de reportes a CSV y Excel. (PDF: issue de la fase 5.)"""

import csv
import io

from django.http import HttpResponse


def a_csv(nombre: str, encabezados: list[str], filas) -> HttpResponse:
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{nombre}.csv"'
    resp.write("﻿")  # BOM para que Excel abra bien las tildes
    w = csv.writer(resp)
    w.writerow(encabezados)
    w.writerows(filas)
    return resp


def a_excel(nombre: str, encabezados: list[str], filas) -> HttpResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = nombre[:31]
    ws.append(encabezados)
    for c in ws[1]:
        c.font = Font(bold=True)
    for f in filas:
        ws.append([float(x) if hasattr(x, "as_tuple") else x for x in f])
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(
        buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{nombre}.xlsx"'
    return resp

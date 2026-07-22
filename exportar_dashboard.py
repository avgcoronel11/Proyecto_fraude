"""
Exporta resultados del dashboard a una carpeta estatica.

Uso recomendado:

    .venv/bin/python exportar_dashboard.py

Por defecto toma el rango de fechas mas completo disponible, busca otras
ejecuciones del mismo rango y genera un dashboard consolidado con filtro por
red social. La carpeta resultante se puede abrir sin Python, sin Playwright y
sin servidor local.
"""

import argparse
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import interfaz


BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "dashboard_exportado"

PLATAFORMAS = [
    {"value": "all", "label": "Todas las redes"},
    {"value": "facebook", "label": "Facebook"},
    {"value": "linkedin", "label": "LinkedIn"},
    {"value": "instagram", "label": "Instagram"},
]

TABLE_LABELS = {
    "publicaciones": "Publicaciones",
    "descartadas": "Descartadas",
    "conteo": "Conteo",
    "comparativo": "Comparativo",
    "tiempos": "Tiempos",
}


def resolver_ejecucion(valor):
    """Resuelve una ejecucion explicita o elige automaticamente la mejor disponible."""
    if valor:
        ruta = Path(valor)
        if not ruta.is_absolute():
            ruta = BASE_DIR / ruta
        if ruta.exists() and ruta.is_dir():
            return ruta.resolve()
        return interfaz.obtener_ejecucion(valor)

    return ejecucion_por_defecto()


def ruta_salida_unica(ruta_base):
    if not ruta_base.exists():
        return ruta_base

    contador = 2
    while True:
        candidata = ruta_base.with_name(f"{ruta_base.name}_{contador}")
        if not candidata.exists():
            return candidata
        contador += 1


def plataforma_label(plataforma):
    for item in PLATAFORMAS:
        if item["value"] == plataforma:
            return item["label"]
    return interfaz.plataforma_label(plataforma)


def plataforma_ejecucion(ejecucion):
    metadata = interfaz.leer_metadata_ejecucion(ejecucion)
    return metadata.get("plataforma") or interfaz.inferir_plataforma_ejecucion(ejecucion)


def clave_contexto(metadata):
    inicio = metadata.get("fecha_inicio") or ""
    fin = metadata.get("fecha_fin") or ""
    if inicio or fin:
        return ("fechas", inicio, fin)

    return ("rango", metadata.get("rango_fecha") or "")


def ejecucion_por_defecto():
    """Elige el rango con mas redes disponibles para exportar un consolidado util."""
    candidatas = []
    for ejecucion in interfaz.ejecuciones_disponibles():
        metadata = interfaz.leer_metadata_ejecucion(ejecucion)
        if metadata.get("tiene_archivos_resultado"):
            candidatas.append((ejecucion, metadata))

    if not candidatas:
        raise FileNotFoundError("No hay ejecuciones con archivos de resultado.")

    contextos = {}
    for ejecucion, metadata in candidatas:
        clave = clave_contexto(metadata)
        contexto = contextos.setdefault(
            clave,
            {"ejecuciones": [], "plataformas": set(), "mtime": 0},
        )
        contexto["ejecuciones"].append((ejecucion, metadata))
        contexto["plataformas"].add(
            metadata.get("plataforma") or interfaz.inferir_plataforma_ejecucion(ejecucion)
        )
        contexto["mtime"] = max(
            contexto["mtime"],
            metadata.get("mtime") or ejecucion.stat().st_mtime,
        )

    mejor_contexto = max(
        contextos.values(),
        key=lambda contexto: (len(contexto["plataformas"]), contexto["mtime"]),
    )
    return max(
        mejor_contexto["ejecuciones"],
        key=lambda item: item[1].get("mtime") or item[0].stat().st_mtime,
    )[0]


def ejecuciones_del_contexto(ejecucion_base):
    """Agrupa ejecuciones que comparten el mismo rango de fechas de la base."""
    contexto = interfaz.leer_metadata_ejecucion(ejecucion_base)
    ejecuciones = []

    for ejecucion in interfaz.ejecuciones_disponibles():
        metadata = interfaz.leer_metadata_ejecucion(ejecucion)
        if not metadata.get("tiene_archivos_resultado"):
            continue
        if not interfaz.metadata_coincide_rango(metadata, contexto):
            continue
        ejecuciones.append(ejecucion)

    return ejecuciones or [ejecucion_base]


def copiar_logo(salida, archivos):
    logo_origen = BASE_DIR / "Logo" / "LINDA.png"
    if not logo_origen.exists():
        return

    logo_destino = salida / "assets" / "LINDA.png"
    logo_destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(logo_origen, logo_destino)
    archivos["logo"] = {
        "label": "Logo",
        "path": logo_destino.relative_to(salida).as_posix(),
    }


def copiar_capturas(ejecuciones, salida):
    for ejecucion in ejecuciones:
        origen = ejecucion / "capturas_publicaciones"
        if not origen.exists():
            continue

        destino = salida / "capturas" / ejecucion.name / "capturas_publicaciones"
        shutil.copytree(origen, destino, dirs_exist_ok=True)


def ruta_imagen_exportada(ejecucion, salida, valor):
    if not valor:
        return ""

    try:
        origen = interfaz.ruta_imagen_segura(ejecucion, valor)
    except FileNotFoundError:
        return ""

    try:
        relativa = origen.relative_to(ejecucion)
    except ValueError:
        relativa = Path("capturas_publicaciones") / origen.name

    destino = salida / "capturas" / ejecucion.name / relativa
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)

    return destino.relative_to(salida).as_posix()


def enriquecer_fila(fila, ejecucion, salida, plataforma):
    fila = dict(fila)
    fila["plataforma"] = plataforma
    fila["plataforma_label"] = plataforma_label(plataforma)
    fila["ejecucion"] = ejecucion.name
    fila["imagen_exportada"] = ruta_imagen_exportada(
        ejecucion,
        salida,
        fila.get("imagen_publicacion") or fila.get("archivo_imagen"),
    )
    return fila


def filas_por_ejecucion(ejecuciones, salida):
    publicaciones = []
    descartadas = []
    tiempos = []

    for ejecucion in ejecuciones:
        metadata = interfaz.leer_metadata_ejecucion(ejecucion)
        plataforma = metadata.get("plataforma") or interfaz.inferir_plataforma_ejecucion(ejecucion)

        filas_publicaciones = interfaz.filtrar_publicaciones_validas(
            interfaz.leer_csv(ejecucion / "publicaciones_linkedin.csv"),
            metadata,
        )
        publicaciones.extend(
            enriquecer_fila(fila, ejecucion, salida, plataforma)
            for fila in filas_publicaciones
        )

        descartadas.extend(
            enriquecer_fila(fila, ejecucion, salida, plataforma)
            for fila in interfaz.leer_csv(ejecucion / "publicaciones_descartadas.csv")
        )

        for fila in interfaz.leer_csv(ejecucion / "tiempos_ejecucion.csv"):
            if fila.get("tipo_tiempo") != "busqueda":
                continue
            fila = dict(fila)
            fila["plataforma"] = plataforma
            fila["plataforma_label"] = plataforma_label(plataforma)
            fila["ejecucion"] = ejecucion.name
            tiempos.append(fila)

    return publicaciones, descartadas, tiempos


def filtrar_plataforma(filas, plataforma):
    if plataforma == "all":
        return list(filas)
    return [fila for fila in filas if fila.get("plataforma") == plataforma]


def resumen_vista(publicaciones, descartadas, tiempos, conteo):
    duracion_segundos = round(
        sum(interfaz.numero(fila.get("duracion_segundos")) for fila in tiempos),
        2,
    )
    return {
        "publicaciones": len(publicaciones),
        "descartadas": len(descartadas),
        "bancos_con_resultados": sum(
            1 for fila in conteo if interfaz.numero(fila.get("publicaciones")) > 0
        ),
        "duracion_total_segundos": duracion_segundos,
        "duracion_total_minutos": round(duracion_segundos / 60, 2),
        "total_busquedas": len(tiempos),
    }


def construir_vistas(contexto, publicaciones, descartadas, tiempos):
    """Construye los datos que el HTML usa para cada filtro de red social."""
    vistas = {}

    for item in PLATAFORMAS:
        plataforma = item["value"]
        pubs = filtrar_plataforma(publicaciones, plataforma)
        desc = filtrar_plataforma(descartadas, plataforma)
        times = filtrar_plataforma(tiempos, plataforma)
        conteo = interfaz.resumen_bancos_plataforma(plataforma, contexto=contexto)
        comparativo = interfaz.recalcular_comparativo_publicaciones(
            pubs,
            desc,
            conteo,
            contexto,
        )

        vistas[plataforma] = {
            "label": item["label"],
            "resumen": resumen_vista(pubs, desc, times, conteo),
            "graficas": {
                "conteo": conteo,
                "tiempos_banco": interfaz.resumen_tiempos_plataforma(
                    plataforma,
                    contexto=contexto,
                ),
                "dolor_cliente": interfaz.resumen_modalidad_plataforma(
                    plataforma,
                    contexto=contexto,
                ),
            },
            "tablas": {
                "publicaciones": pubs,
                "descartadas": desc,
                "conteo": conteo,
                "comparativo": comparativo,
                "tiempos": times,
            },
        }

    return vistas


def construir_datos(ejecucion_base, ejecuciones, salida, archivos):
    contexto = interfaz.leer_metadata_ejecucion(ejecucion_base)
    publicaciones, descartadas, tiempos = filas_por_ejecucion(ejecuciones, salida)

    return {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "ejecucion_base": ejecucion_base.name,
        "ejecuciones_incluidas": [
            {
                "name": ejecucion.name,
                "platform": plataforma_ejecucion(ejecucion),
                "platform_label": plataforma_label(plataforma_ejecucion(ejecucion)),
            }
            for ejecucion in ejecuciones
        ],
        "metadata": contexto,
        "platforms": PLATAFORMAS,
        "platform_summary": interfaz.resumen_por_plataforma("all", contexto=contexto),
        "archivos": archivos,
        "views": construir_vistas(contexto, publicaciones, descartadas, tiempos),
    }


EXCEL_COLUMN_LABELS = {
    "red": "Red",
    "plataforma_label": "Red",
    "ejecucion": "Ejecucion",
    "banco": "Banco",
    "autor": "Autor",
    "fecha_publicacion_estimada": "Fecha publicacion",
    "fecha_en_rango": "Fecha en rango",
    "tipo_contenido": "Tipo contenido",
    "dolor_cliente": "Dolor cliente",
    "modalidad_especifica": "Modalidad especifica",
    "comentarios": "Comentarios",
    "interacciones_total": "Interacciones",
    "url": "URL",
    "motivo_relevancia": "Motivo relevancia",
    "publicaciones": "Publicaciones",
    "descartadas": "Descartadas",
    "bancos_con_resultados": "Bancos con resultados",
    "duracion_total_minutos": "Duracion total minutos",
    "total_busquedas": "Total busquedas",
    "ejecuciones": "Ejecuciones",
    "grupo": "Grupo",
    "denuncias_directas": "Denuncias directas",
    "denuncias_descartadas": "Denuncias descartadas",
    "participacion_total_porcentaje": "Participacion total %",
    "diferencia_vs_banco_popular": "Diferencia vs Banco Popular",
    "interacciones_total": "Interacciones total",
    "ranking_denuncias": "Ranking denuncias",
    "duracion_minutos": "Duracion minutos",
    "publicaciones_relevantes": "Publicaciones relevantes",
    "publicaciones_descartadas": "Publicaciones descartadas",
    "estado": "Estado",
    "inicio": "Inicio",
    "fin": "Fin",
    "duracion_segundos": "Duracion segundos",
}

RESUMEN_COLUMNS = [
    "red",
    "publicaciones",
    "descartadas",
    "bancos_con_resultados",
    "duracion_total_minutos",
    "total_busquedas",
    "ejecuciones",
]

RED_COLUMNS = [
    "red",
    "banco",
    "denuncias_directas",
    "denuncias_descartadas",
    "participacion_total_porcentaje",
    "diferencia_vs_banco_popular",
    "interacciones_total",
    "ranking_denuncias",
    "duracion_minutos",
    "total_busquedas",
    "publicaciones_relevantes",
    "publicaciones_descartadas",
]

PUBLICACION_COLUMNS = [
    "plataforma_label",
    "banco",
    "autor",
    "fecha_publicacion_estimada",
    "tipo_contenido",
    "dolor_cliente",
    "modalidad_especifica",
    "comentarios",
    "interacciones_total",
    "url",
    "ejecucion",
]

DESCARTADAS_COLUMNS = [
    "plataforma_label",
    "banco",
    "fecha_publicacion_estimada",
    "fecha_en_rango",
    "tipo_contenido",
    "motivo_relevancia",
    "comentarios",
    "url",
    "ejecucion",
]

TIEMPOS_COLUMNS = [
    "plataforma_label",
    "banco",
    "inicio",
    "fin",
    "duracion_segundos",
    "duracion_minutos",
    "publicaciones_relevantes",
    "publicaciones_descartadas",
    "estado",
    "ejecucion",
]


def limpiar_texto_excel(valor):
    texto = str(valor)
    texto = "".join(
        caracter
        for caracter in texto
        if caracter in "\t\n\r" or ord(caracter) >= 32
    )
    return texto[:32700]


def escape_xml_texto(valor):
    return escape(limpiar_texto_excel(valor))


def escape_xml_atributo(valor):
    return escape(limpiar_texto_excel(valor), {'"': "&quot;"})


def columna_excel(indice):
    letras = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def numero_excel(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return int(texto) if texto.isdigit() else float(texto)
    except ValueError:
        return None


def celda_excel_xml(fila_indice, columna_indice, valor, estilo=2):
    referencia = f"{columna_excel(columna_indice)}{fila_indice}"
    numero = numero_excel(valor)
    if numero is not None:
        return f'<c r="{referencia}" s="{estilo}"><v>{numero}</v></c>'

    return (
        f'<c r="{referencia}" s="{estilo}" t="inlineStr">'
        f'<is><t xml:space="preserve">{escape_xml_texto(valor or "")}</t></is>'
        "</c>"
    )


def fila_excel_xml(fila_indice, valores, estilo=2):
    celdas = "".join(
        celda_excel_xml(fila_indice, columna_indice, valor, estilo)
        for columna_indice, valor in enumerate(valores, start=1)
    )
    return f'<row r="{fila_indice}">{celdas}</row>'


def ancho_columna(filas, columna):
    valores = [EXCEL_COLUMN_LABELS.get(columna, columna)]
    valores.extend(str(fila.get(columna, ""))[:80] for fila in filas[:80])
    return min(max(max(len(valor) for valor in valores) + 2, 12), 48)


def hoja_excel_xml(filas, columnas):
    encabezados = [EXCEL_COLUMN_LABELS.get(columna, columna) for columna in columnas]
    filas_xml = [fila_excel_xml(1, encabezados, estilo=1)]
    for indice, fila in enumerate(filas, start=2):
        filas_xml.append(fila_excel_xml(indice, [fila.get(columna, "") for columna in columnas]))

    cols_xml = "".join(
        f'<col min="{indice}" max="{indice}" width="{ancho_columna(filas, columna)}" customWidth="1"/>'
        for indice, columna in enumerate(columnas, start=1)
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<cols>{cols_xml}</cols>"
        f"<sheetData>{''.join(filas_xml)}</sheetData>"
        "</worksheet>"
    )


def nombre_hoja_excel(nombre, usados):
    invalidados = "[]:*?/\\"
    limpio = "".join("_" if caracter in invalidados else caracter for caracter in nombre)
    limpio = limpio.strip()[:31] or "Hoja"
    base = limpio
    contador = 2
    while limpio in usados:
        sufijo = f" {contador}"
        limpio = f"{base[:31 - len(sufijo)]}{sufijo}"
        contador += 1
    usados.add(limpio)
    return limpio


def estilos_excel_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><color rgb="FF17202A"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="4">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF17202A"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFFFF"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2"><border/>'
        '<border><left style="thin"><color rgb="FFD8DEE6"/></left>'
        '<right style="thin"><color rgb="FFD8DEE6"/></right>'
        '<top style="thin"><color rgb="FFD8DEE6"/></top>'
        '<bottom style="thin"><color rgb="FFD8DEE6"/></bottom></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1">'
        '<alignment vertical="top" wrapText="1"/></xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>'
        '</styleSheet>'
    )


def escribir_libro_excel(ruta, hojas):
    """Escribe un XLSX basico sin pandas/openpyxl para mantener portabilidad."""
    usados = set()
    hojas_normalizadas = [
        (nombre_hoja_excel(nombre, usados), filas, columnas)
        for nombre, filas, columnas in hojas
    ]
    workbook_sheets = "".join(
        f'<sheet name="{escape_xml_atributo(nombre)}" sheetId="{indice}" r:id="rId{indice}"/>'
        for indice, (nombre, _, _) in enumerate(hojas_normalizadas, start=1)
    )
    workbook_rels = "".join(
        '<Relationship '
        f'Id="rId{indice}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{indice}.xml"/>'
        for indice in range(1, len(hojas_normalizadas) + 1)
    )
    workbook_rels += (
        '<Relationship Id="rId99" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{indice}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for indice in range(1, len(hojas_normalizadas) + 1)
    )

    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as archivo:
        archivo.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" '
            'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            f"{overrides}</Types>",
        )
        archivo.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
            'Target="docProps/app.xml"/>'
            "</Relationships>",
        )
        archivo.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets></workbook>",
        )
        archivo.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{workbook_rels}</Relationships>",
        )
        archivo.writestr("xl/styles.xml", estilos_excel_xml())
        archivo.writestr(
            "docProps/core.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>Consolidado por red</dc:title>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).isoformat()}</dcterms:created>'
            "</cp:coreProperties>",
        )
        archivo.writestr(
            "docProps/app.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>LINDA</Application>"
            "</Properties>",
        )
        for indice, (_, filas, columnas) in enumerate(hojas_normalizadas, start=1):
            archivo.writestr(
                f"xl/worksheets/sheet{indice}.xml",
                hoja_excel_xml(filas, columnas),
            )


def filas_resumen_excel(datos):
    resumen_por_red = {
        fila.get("plataforma"): fila
        for fila in datos.get("platform_summary", [])
    }
    filas = []

    for plataforma in PLATAFORMAS:
        valor = plataforma["value"]
        vista = datos["views"].get(valor, {})
        resumen = vista.get("resumen", {})
        fila_plataforma = resumen_por_red.get(valor, {})
        filas.append(
            {
                "red": plataforma["label"],
                "publicaciones": resumen.get("publicaciones", 0),
                "descartadas": resumen.get("descartadas", 0),
                "bancos_con_resultados": resumen.get("bancos_con_resultados", 0),
                "duracion_total_minutos": resumen.get("duracion_total_minutos", 0),
                "total_busquedas": resumen.get("total_busquedas", 0),
                "ejecuciones": (
                    len(datos.get("ejecuciones_incluidas", []))
                    if valor == "all"
                    else fila_plataforma.get("ejecuciones", 0)
                ),
            }
        )

    return filas


def filas_red_excel(datos, plataforma):
    vista = datos["views"].get(plataforma, {})
    label = vista.get("label") or plataforma_label(plataforma)
    comparativo = {
        fila.get("banco"): fila
        for fila in vista.get("tablas", {}).get("comparativo", [])
        if fila.get("banco")
    }
    tiempos = {
        fila.get("banco"): fila
        for fila in vista.get("graficas", {}).get("tiempos_banco", [])
        if fila.get("banco")
    }
    bancos = list(comparativo)
    for banco in tiempos:
        if banco not in bancos:
            bancos.append(banco)

    filas = []
    for banco in bancos:
        fila_comparativo = comparativo.get(banco, {})
        fila_tiempo = tiempos.get(banco, {})
        filas.append(
            {
                "red": label,
                "banco": banco,
                "denuncias_directas": fila_comparativo.get("denuncias_directas", 0),
                "denuncias_descartadas": fila_comparativo.get("denuncias_descartadas", 0),
                "participacion_total_porcentaje": fila_comparativo.get(
                    "participacion_total_porcentaje",
                    0,
                ),
                "diferencia_vs_banco_popular": fila_comparativo.get(
                    "diferencia_vs_banco_popular",
                    0,
                ),
                "interacciones_total": fila_comparativo.get("interacciones_total", 0),
                "ranking_denuncias": fila_comparativo.get("ranking_denuncias", ""),
                "duracion_minutos": fila_tiempo.get("duracion_minutos", 0),
                "total_busquedas": fila_tiempo.get("total_busquedas", 0),
                "publicaciones_relevantes": fila_tiempo.get("publicaciones_relevantes", 0),
                "publicaciones_descartadas": fila_tiempo.get("publicaciones_descartadas", 0),
            }
        )

    return filas


def crear_excel_consolidado(datos, salida, archivos):
    """Genera el unico Excel entregable con resumen y detalle por red."""
    ruta = salida / "archivos" / "consolidado_por_red.xlsx"
    tablas = datos["views"]["all"]["tablas"]
    hojas = [
        ("Resumen", filas_resumen_excel(datos), RESUMEN_COLUMNS),
        ("Facebook", filas_red_excel(datos, "facebook"), RED_COLUMNS),
        ("LinkedIn", filas_red_excel(datos, "linkedin"), RED_COLUMNS),
        ("Instagram", filas_red_excel(datos, "instagram"), RED_COLUMNS),
        ("Publicaciones", tablas.get("publicaciones", []), PUBLICACION_COLUMNS),
        ("Descartadas", tablas.get("descartadas", []), DESCARTADAS_COLUMNS),
        ("Tiempos", tablas.get("tiempos", []), TIEMPOS_COLUMNS),
    ]
    escribir_libro_excel(ruta, hojas)
    archivos["items"].append(
        {
            "key": "consolidado_por_red",
            "label": "Consolidado por red.xlsx",
            "path": ruta.relative_to(salida).as_posix(),
            "platform": "all",
            "execution": datos.get("ejecucion_base", ""),
        }
    )


def json_para_html(datos):
    return json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")


HTML_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LINDA - Dashboard estatico</title>
  <style>
    :root {
      --bg: #f3f6f8;
      --panel: #ffffff;
      --text: #1d2733;
      --muted: #637083;
      --line: #d9e0e7;
      --accent: #0f6b63;
      --accent-2: #275d9f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    header {
      background: #17202a;
      color: #fff;
      border-bottom: 1px solid #0c1117;
    }
    .topbar {
      max-width: 1440px;
      margin: 0 auto;
      padding: 14px 18px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
    }
    .brand {
      display: flex;
      align-items: center;
      min-width: 0;
      gap: 12px;
    }
    .brand img {
      width: 62px;
      height: 48px;
      object-fit: contain;
      border-radius: 6px;
      background: #071426;
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 22px; }
    h2 { font-size: 16px; }
    .subtitle, .stamp, .muted { color: var(--muted); }
    header .subtitle, header .stamp { color: #c8d5e2; }
    main {
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px;
    }
    .metrics, .platform-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .card, .section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .card { padding: 14px; }
    .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .value {
      margin-top: 4px;
      font-size: 28px;
      line-height: 1.1;
      font-weight: 750;
    }
    .sub { margin-top: 4px; color: var(--muted); }
    .section { margin-top: 16px; }
    .section-head {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .section-body { padding: 14px; }
    .grid-2 {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    select, input, button, a.button {
      font: inherit;
      height: 36px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      padding: 0 10px;
    }
    button, a.button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 650;
    }
    button.secondary, a.button.secondary {
      background: #fff;
      color: var(--accent);
      border-color: var(--accent);
    }
    .bars { display: grid; gap: 10px; }
    .bar-row {
      display: grid;
      grid-template-columns: minmax(160px, 260px) 1fr 74px;
      gap: 12px;
      align-items: center;
    }
    .bar-label {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .bar-track {
      height: 16px;
      background: #eef2f5;
      border-radius: 3px;
      overflow: hidden;
    }
    .bar-fill {
      height: 100%;
      min-width: 2px;
      background: var(--accent-2);
    }
    .bar-fill.popular { background: var(--accent); }
    .bar-value {
      text-align: right;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    .donut-layout {
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      gap: 20px;
      align-items: center;
    }
    .donut {
      width: min(100%, 240px);
      aspect-ratio: 1;
      border-radius: 50%;
      background: #eef2f6;
      position: relative;
      box-shadow: inset 0 0 0 1px rgba(23, 32, 42, .08);
    }
    .donut::after {
      content: "";
      position: absolute;
      inset: 27%;
      border-radius: 50%;
      background: var(--panel);
      box-shadow: 0 0 0 1px rgba(23, 32, 42, .08);
    }
    .legend { display: grid; gap: 8px; }
    .legend-item {
      display: grid;
      grid-template-columns: 14px 1fr auto;
      gap: 9px;
      align-items: center;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 3px;
      background: var(--color);
    }
    .files {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .toolbar input {
      min-width: 260px;
      flex: 1 1 260px;
    }
    .table-wrap {
      overflow: auto;
      max-height: 680px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 1080px;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef3f7;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: #405066;
    }
    td.long {
      min-width: 280px;
      max-width: 460px;
      white-space: pre-wrap;
    }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .tab.active {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .empty { padding: 24px; color: var(--muted); }
    .modal {
      position: fixed;
      inset: 0;
      z-index: 50;
      background: rgba(9, 14, 22, .72);
      display: grid;
      place-items: center;
      padding: 22px;
    }
    .modal.hidden { display: none; }
    .modal-panel {
      width: min(1120px, 100%);
      max-height: 92vh;
      overflow: auto;
      background: var(--panel);
      border-radius: 8px;
      border: 1px solid var(--line);
    }
    .modal-head {
      position: sticky;
      top: 0;
      z-index: 1;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .modal-body {
      padding: 14px;
      display: grid;
      gap: 12px;
    }
    .modal-body img {
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
    }
    .evidence-text {
      white-space: pre-wrap;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 260px;
      overflow: auto;
    }
    @media (max-width: 900px) {
      .topbar, .metrics, .platform-grid, .grid-2, .donut-layout {
        grid-template-columns: 1fr;
      }
      .bar-row {
        grid-template-columns: 1fr;
        gap: 5px;
      }
      .bar-value { text-align: left; }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="brand">
        <img id="logo" alt="LINDA">
        <div>
          <h1>LINDA</h1>
          <div class="subtitle" id="subtitle"></div>
        </div>
      </div>
      <div class="stamp" id="stamp"></div>
    </div>
  </header>
  <main>
    <section class="section">
      <div class="section-head">
        <h2>Vista</h2>
        <div class="controls">
          <label for="platformSelect">Red</label>
          <select id="platformSelect"></select>
        </div>
      </div>
      <div class="section-body">
        <div class="platform-grid" id="platformCards"></div>
      </div>
    </section>

    <section class="metrics" id="metrics"></section>

    <section class="section">
      <div class="section-head">
        <h2>Archivos</h2>
      </div>
      <div class="section-body">
        <div class="files" id="files"></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Denuncias por banco</h2>
      </div>
      <div class="section-body">
        <div class="bars" id="bankBars"></div>
      </div>
    </section>

    <section class="grid-2">
      <section class="section">
        <div class="section-head">
          <h2>Tiempo por banco</h2>
        </div>
        <div class="section-body">
          <div class="bars" id="timeBars"></div>
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <h2>Modalidad reportada</h2>
        </div>
        <div class="section-body donut-layout">
          <div class="donut" id="donut"></div>
          <div class="legend" id="legend"></div>
        </div>
      </section>
    </section>

    <section class="section">
      <div class="section-head">
        <div class="tabs" id="tabs"></div>
        <div class="toolbar">
          <input id="filter" type="search" placeholder="Filtrar tabla">
        </div>
      </div>
      <div class="table-wrap">
        <table id="table"></table>
      </div>
    </section>
  </main>

  <div class="modal hidden" id="modal">
    <div class="modal-panel">
      <div class="modal-head">
        <div>
          <h3 id="modalTitle">Captura</h3>
          <div class="muted" id="modalSubtitle"></div>
        </div>
        <button class="secondary" id="closeModal" type="button">Cerrar</button>
      </div>
      <div class="modal-body" id="modalBody"></div>
    </div>
  </div>

  <script id="dashboardData" type="application/json">__PAYLOAD__</script>
  <script>
    const DATA = JSON.parse(document.getElementById("dashboardData").textContent);
    const TABLE_LABELS = __TABLE_LABELS__;
    const COLORS = ["#0f6b63", "#275d9f", "#b7791f", "#8a63d2", "#c2410c", "#2f855a", "#b83280", "#4a5568"];
    const POPULAR = "Banco Popular Colombia";
    let currentTable = "publicaciones";
    let currentPlatform = "all";

    const columns = {
      publicaciones: ["plataforma_label", "banco", "autor", "fecha_publicacion_estimada", "tipo_contenido", "dolor_cliente", "modalidad_especifica", "comentarios", "interacciones_total", "url"],
      descartadas: ["plataforma_label", "banco", "fecha_publicacion_estimada", "fecha_en_rango", "tipo_contenido", "motivo_relevancia", "comentarios", "url"],
      conteo: ["banco", "rango_fecha", "publicaciones"],
      comparativo: ["banco", "grupo", "denuncias_directas", "denuncias_descartadas", "participacion_total_porcentaje", "diferencia_vs_banco_popular", "interacciones_total", "ranking_denuncias"],
      tiempos: ["plataforma_label", "banco", "inicio", "fin", "duracion_segundos", "duracion_minutos", "publicaciones_relevantes", "publicaciones_descartadas", "estado"]
    };

    const labels = {
      plataforma_label: "Red",
      ejecucion: "Ejecucion",
      banco: "Banco",
      autor: "Autor",
      fecha_publicacion_estimada: "Fecha",
      fecha_en_rango: "Rango",
      tipo_contenido: "Tipo",
      dolor_cliente: "Dolor",
      modalidad_especifica: "Modalidad",
      comentarios: "Comentarios",
      interacciones_total: "Interacciones",
      url: "URL",
      motivo_relevancia: "Motivo",
      rango_fecha: "Rango",
      publicaciones: "Publicaciones",
      grupo: "Grupo",
      denuncias_directas: "Denuncias",
      denuncias_descartadas: "Descartadas",
      participacion_total_porcentaje: "Participacion %",
      diferencia_vs_banco_popular: "Dif. vs Popular",
      ranking_denuncias: "Ranking",
      inicio: "Inicio",
      fin: "Fin",
      duracion_segundos: "Segundos",
      duracion_minutos: "Minutos",
      publicaciones_relevantes: "Relevantes",
      publicaciones_descartadas: "Descartadas",
      estado: "Estado"
    };

    function esc(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function num(value) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : 0;
    }

    function view() {
      return DATA.views[currentPlatform] || DATA.views.all;
    }

    function formatDuration(seconds) {
      const value = num(seconds);
      return value >= 60 ? `${(value / 60).toFixed(1)} min` : `${value.toFixed(0)} s`;
    }

    function renderHeader() {
      const metadata = DATA.metadata || {};
      const logo = DATA.archivos.logo && DATA.archivos.logo.path;
      document.getElementById("logo").src = logo || "";
      document.getElementById("logo").style.display = logo ? "block" : "none";
      document.getElementById("subtitle").textContent = [
        "Consolidado por red",
        metadata.rango_fecha,
        `${DATA.ejecuciones_incluidas.length} ejecuciones`
      ].filter(Boolean).join(" | ");
      document.getElementById("stamp").textContent = `Generado: ${DATA.generado_en || ""}`;
    }

    function card(label, value, sub) {
      return `<div class="card">
        <div class="label">${esc(label)}</div>
        <div class="value">${esc(value)}</div>
        <div class="sub">${esc(sub || "")}</div>
      </div>`;
    }

    function renderPlatformSelect() {
      const select = document.getElementById("platformSelect");
      select.innerHTML = DATA.platforms.map(platform => {
        return `<option value="${esc(platform.value)}">${esc(platform.label)}</option>`;
      }).join("");
      select.value = currentPlatform;
      select.addEventListener("change", () => {
        currentPlatform = select.value;
        document.getElementById("filter").value = "";
        renderAll();
      });
    }

    function renderPlatformCards() {
      const byPlatform = new Map((DATA.platform_summary || []).map(row => [row.plataforma, row]));
      document.getElementById("platformCards").innerHTML = DATA.platforms
        .filter(platform => platform.value !== "all")
        .map(platform => {
          const row = byPlatform.get(platform.value) || {};
          return card(
            platform.label,
            num(row.publicaciones),
            `${num(row.descartadas)} descartadas | ${num(row.ejecuciones)} ejec.`
          );
        }).join("");
    }

    function renderMetrics() {
      const s = view().resumen || {};
      document.getElementById("metrics").innerHTML = [
        card("Denuncias directas", s.publicaciones || 0, "publicaciones relevantes"),
        card("Descartadas", s.descartadas || 0, "auditoria del filtro"),
        card("Bancos", s.bancos_con_resultados || 0, "con al menos una denuncia"),
        card("Tiempo total", `${s.duracion_total_minutos || 0} min`, `${s.total_busquedas || 0} consultas`)
      ].join("");
    }

    function renderFiles() {
      const files = (DATA.archivos.items || [])
        .filter(file => file.platform === "all" || currentPlatform === "all" || file.platform === currentPlatform)
        .map(file => `<a class="button secondary" href="${esc(file.path)}" download>${esc(file.label)}</a>`);
      document.getElementById("files").innerHTML = files.join("") || `<div class="muted">Sin archivos exportados para esta red.</div>`;
    }

    function renderBars(id, rows, labelKey, valueKey, formatter) {
      const data = [...(rows || [])];
      const max = Math.max(1, ...data.map(row => num(row[valueKey])));
      document.getElementById(id).innerHTML = data.map(row => {
        const label = row[labelKey] || "";
        const value = num(row[valueKey]);
        const width = Math.max(2, Math.round((value / max) * 100));
        const popular = label === POPULAR ? " popular" : "";
        const display = formatter ? formatter(value, row) : value;
        return `<div class="bar-row">
          <div class="bar-label" title="${esc(label)}">${esc(label)}</div>
          <div class="bar-track"><div class="bar-fill${popular}" style="width:${width}%"></div></div>
          <div class="bar-value">${esc(display)}</div>
        </div>`;
      }).join("") || `<div class="muted">Sin datos.</div>`;
    }

    function renderDonut() {
      const rows = [...(view().graficas.dolor_cliente || [])]
        .filter(row => num(row.publicaciones) > 0)
        .sort((a, b) => num(b.publicaciones) - num(a.publicaciones))
        .slice(0, 8);
      const total = rows.reduce((sum, row) => sum + num(row.publicaciones), 0);
      const donut = document.getElementById("donut");
      const legend = document.getElementById("legend");

      if (!total) {
        donut.style.background = "#eef2f6";
        legend.innerHTML = `<div class="muted">Sin datos.</div>`;
        return;
      }

      let cursor = 0;
      donut.style.background = `conic-gradient(${rows.map((row, index) => {
        const start = cursor;
        const end = cursor + (num(row.publicaciones) / total) * 100;
        cursor = end;
        return `${COLORS[index % COLORS.length]} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
      }).join(", ")})`;

      legend.innerHTML = rows.map((row, index) => {
        const value = num(row.publicaciones);
        const percent = total ? ((value / total) * 100).toFixed(1) : "0.0";
        const label = row.modalidad_reportada || row.dolor_cliente || "Sin modalidad";
        return `<div class="legend-item">
          <div class="swatch" style="--color:${COLORS[index % COLORS.length]}"></div>
          <div>${esc(label)}</div>
          <div class="bar-value">${value} | ${percent}%</div>
        </div>`;
      }).join("");
    }

    function renderTabs() {
      document.getElementById("tabs").innerHTML = Object.keys(TABLE_LABELS).map(key => {
        const active = key === currentTable ? " active" : "";
        return `<button class="tab secondary${active}" data-table="${key}" type="button">${esc(TABLE_LABELS[key])}</button>`;
      }).join("");
      document.querySelectorAll(".tab").forEach(button => {
        button.addEventListener("click", () => {
          currentTable = button.dataset.table;
          renderTabs();
          renderTable();
        });
      });
    }

    function rowText(row) {
      return Object.values(row).join(" ").toLowerCase();
    }

    function renderTable() {
      const filter = document.getElementById("filter").value.trim().toLowerCase();
      const rows = (view().tablas[currentTable] || []).filter(row => !filter || rowText(row).includes(filter));
      const table = document.getElementById("table");

      if (!rows.length) {
        table.innerHTML = `<tbody><tr><td class="empty">Sin filas para mostrar.</td></tr></tbody>`;
        return;
      }

      const tableColumns = columns[currentTable] || Object.keys(rows[0]);
      const actionHead = ["publicaciones", "descartadas"].includes(currentTable) ? "<th>Captura</th>" : "";
      const head = `<thead><tr>${actionHead}${tableColumns.map(col => `<th>${esc(labels[col] || col)}</th>`).join("")}</tr></thead>`;
      const body = rows.map((row, index) => {
        const action = ["publicaciones", "descartadas"].includes(currentTable)
          ? `<td><button class="secondary" type="button" data-index="${index}">Ver</button></td>`
          : "";
        const cells = tableColumns.map(col => {
          const value = row[col] || "";
          const cls = ["texto", "motivo_relevancia", "url"].includes(col) ? "long" : "";
          const html = col === "url" && value
            ? `<a href="${esc(value)}" target="_blank" rel="noopener">${esc(value)}</a>`
            : esc(value);
          return `<td class="${cls}">${html}</td>`;
        }).join("");
        return `<tr>${action}${cells}</tr>`;
      }).join("");

      table.innerHTML = `${head}<tbody>${body}</tbody>`;
      table.querySelectorAll("button[data-index]").forEach(button => {
        button.addEventListener("click", () => openModal(rows[Number(button.dataset.index)]));
      });
    }

    function openModal(row) {
      const modal = document.getElementById("modal");
      const path = row.imagen_exportada || "";
      const text = row.texto || "";
      document.getElementById("modalTitle").textContent = row.banco || "Captura";
      document.getElementById("modalSubtitle").textContent = [row.plataforma_label, row.fecha_visible, row.archivo_imagen].filter(Boolean).join(" | ");
      document.getElementById("modalBody").innerHTML = [
        path ? `<a href="${esc(path)}" target="_blank" rel="noopener"><img src="${esc(path)}" alt="Captura"></a>` : `<div class="muted">Esta fila no tiene captura asociada.</div>`,
        text ? `<div class="evidence-text">${esc(text)}</div>` : ""
      ].join("");
      modal.classList.remove("hidden");
    }

    function closeModal() {
      document.getElementById("modal").classList.add("hidden");
      document.getElementById("modalBody").innerHTML = "";
    }

    function renderAll() {
      renderPlatformCards();
      renderMetrics();
      renderFiles();
      renderBars("bankBars", view().graficas.conteo || [], "banco", "publicaciones");
      renderBars("timeBars", view().graficas.tiempos_banco || [], "banco", "duracion_segundos", formatDuration);
      renderDonut();
      renderTable();
    }

    function init() {
      renderHeader();
      renderPlatformSelect();
      renderTabs();
      renderAll();
      document.getElementById("filter").addEventListener("input", renderTable);
      document.getElementById("closeModal").addEventListener("click", closeModal);
      document.getElementById("modal").addEventListener("click", event => {
        if (event.target.id === "modal") closeModal();
      });
      document.addEventListener("keydown", event => {
        if (event.key === "Escape") closeModal();
      });
    }

    init();
  </script>
</body>
</html>
"""


def html_dashboard(datos):
    return (
        HTML_TEMPLATE
        .replace("__PAYLOAD__", json_para_html(datos))
        .replace("__TABLE_LABELS__", json.dumps(TABLE_LABELS, ensure_ascii=False))
    )


def escribir_bat(salida):
    contenido = '@echo off\r\nstart "" "%~dp0index.html"\r\n'
    (salida / "abrir_dashboard.bat").write_text(contenido, encoding="utf-8")


def exportar(ejecucion, salida_base=None):
    """Crea la carpeta estatica final con HTML, datos, capturas y Excel."""
    salida_base = salida_base or EXPORT_DIR / ejecucion.name
    salida = ruta_salida_unica(salida_base)
    salida.mkdir(parents=True, exist_ok=False)

    ejecuciones = ejecuciones_del_contexto(ejecucion)
    archivos = {"items": []}
    copiar_logo(salida, archivos)
    copiar_capturas(ejecuciones, salida)
    datos = construir_datos(ejecucion, ejecuciones, salida, archivos)
    crear_excel_consolidado(datos, salida, archivos)

    (salida / "datos.json").write_text(
        json.dumps(datos, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (salida / "index.html").write_text(html_dashboard(datos), encoding="utf-8")
    escribir_bat(salida)

    return salida


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exporta resultados del dashboard a HTML estatico."
    )
    parser.add_argument(
        "ejecucion",
        nargs="?",
        help="Nombre o ruta de resultados/ejecucion_*. Si se omite usa la mas reciente.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Carpeta de salida. Si existe, se crea una variante con sufijo.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    ejecucion = resolver_ejecucion(args.ejecucion)
    salida_base = Path(args.output).resolve() if args.output else None
    salida = exportar(ejecucion, salida_base)

    print(f"Ejecucion base: {ejecucion.name}")
    print(f"Carpeta: {salida}")
    print(f"Abrir: {salida / 'index.html'}")


if __name__ == "__main__":
    main()

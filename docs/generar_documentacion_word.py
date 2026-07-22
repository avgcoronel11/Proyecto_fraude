"""
Genera el documento Word de la documentacion del proyecto LINDA.

No usa dependencias externas. Un archivo .docx es un paquete ZIP con documentos
XML internos, asi que este script convierte la fuente Markdown mantenida en
`Documentacion_Proyecto_LINDA.md` a un Word simple y portable.
"""

import argparse
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MARKDOWN_PATH = BASE_DIR / "Documentacion_Proyecto_LINDA.md"
DEFAULT_DOCX_PATH = BASE_DIR / "Documentacion_Proyecto_LINDA.docx"


def xml_texto(valor):
    return escape(str(valor), {'"': "&quot;"})


def run_texto(texto, monospace=False, bold=False):
    propiedades = []
    if bold:
        propiedades.append("<w:b/>")
    if monospace:
        propiedades.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')

    props_xml = f"<w:rPr>{''.join(propiedades)}</w:rPr>" if propiedades else ""
    return f"<w:r>{props_xml}<w:t xml:space=\"preserve\">{xml_texto(texto)}</w:t></w:r>"


def runs_inline(texto):
    partes = re.split(r"(`[^`]+`)", texto)
    runs = []
    for parte in partes:
        if not parte:
            continue
        if parte.startswith("`") and parte.endswith("`"):
            runs.append(run_texto(parte[1:-1], monospace=True))
        else:
            runs.append(run_texto(parte))
    return "".join(runs)


def parrafo(texto="", estilo=None, indent=False, monospace=False):
    props = []
    if estilo:
        props.append(f'<w:pStyle w:val="{estilo}"/>')
    if indent:
        props.append('<w:ind w:left="360" w:hanging="180"/>')
    if monospace:
        props.append('<w:spacing w:before="60" w:after="60"/>')

    props_xml = f"<w:pPr>{''.join(props)}</w:pPr>" if props else ""
    contenido = run_texto(texto, monospace=True) if monospace else runs_inline(texto)
    return f"<w:p>{props_xml}{contenido}</w:p>"


def convertir_markdown(md_texto):
    bloques = []
    en_codigo = False
    codigo_lineas = []

    for linea in md_texto.splitlines():
        if linea.startswith("```"):
            if en_codigo:
                for codigo in codigo_lineas:
                    bloques.append(parrafo(codigo, estilo="Code", monospace=True))
                codigo_lineas = []
                en_codigo = False
            else:
                en_codigo = True
            continue

        if en_codigo:
            codigo_lineas.append(linea)
            continue

        if not linea.strip():
            bloques.append(parrafo(""))
            continue

        if linea.startswith("# "):
            bloques.append(parrafo(linea[2:].strip(), estilo="Title"))
            continue

        if linea.startswith("## "):
            bloques.append(parrafo(linea[3:].strip(), estilo="Heading1"))
            continue

        if linea.startswith("### "):
            bloques.append(parrafo(linea[4:].strip(), estilo="Heading2"))
            continue

        if linea.startswith("- "):
            bloques.append(parrafo(f"- {linea[2:].strip()}", estilo="ListParagraph", indent=True))
            continue

        bloques.append(parrafo(linea.strip()))

    return "".join(bloques)


def estilos_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>'
        '<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Title">'
        '<w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="240"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="17202A"/><w:sz w:val="36"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:before="260" w:after="120"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="0F6B63"/><w:sz w:val="28"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:before="180" w:after="100"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="275D9F"/><w:sz w:val="24"/></w:rPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="ListParagraph">'
        '<w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="80"/></w:pPr>'
        '</w:style>'
        '<w:style w:type="paragraph" w:styleId="Code">'
        '<w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="40"/></w:pPr>'
        '<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/></w:rPr>'
        '</w:style>'
        '</w:styles>'
    )


def documento_xml(cuerpo):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        f"{cuerpo}"
        '<w:sectPr>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        '</w:sectPr>'
        '</w:body>'
        '</w:document>'
    )


def content_types_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )


def relaciones_raiz_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def relaciones_documento_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '</Relationships>'
    )


def titulo_desde_markdown(markdown):
    for linea in markdown.splitlines():
        if linea.startswith("# "):
            return linea[2:].strip()
    return "Documentacion LINDA"


def core_xml(titulo):
    creado = datetime.now(timezone.utc).isoformat()
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dc:title>{xml_texto(titulo)}</dc:title>'
        '<dc:creator>Proyecto LINDA</dc:creator>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{creado}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{creado}</dcterms:modified>'
        '</cp:coreProperties>'
    )


def app_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        '<Application>LINDA</Application>'
        '</Properties>'
    )


def generar_docx(markdown_path=DEFAULT_MARKDOWN_PATH, docx_path=DEFAULT_DOCX_PATH):
    markdown_path = Path(markdown_path)
    docx_path = Path(docx_path) if docx_path else markdown_path.with_suffix(".docx")
    markdown = markdown_path.read_text(encoding="utf-8")
    cuerpo = convertir_markdown(markdown)
    titulo = titulo_desde_markdown(markdown)

    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as archivo:
        archivo.writestr("[Content_Types].xml", content_types_xml())
        archivo.writestr("_rels/.rels", relaciones_raiz_xml())
        archivo.writestr("word/document.xml", documento_xml(cuerpo))
        archivo.writestr("word/_rels/document.xml.rels", relaciones_documento_xml())
        archivo.writestr("word/styles.xml", estilos_xml())
        archivo.writestr("docProps/core.xml", core_xml(titulo))
        archivo.writestr("docProps/app.xml", app_xml())

    return docx_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Genera un .docx desde una documentacion Markdown."
    )
    parser.add_argument(
        "markdown",
        nargs="?",
        default=str(DEFAULT_MARKDOWN_PATH),
        help="Archivo Markdown fuente.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_DOCX_PATH),
        help="Ruta del .docx de salida.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ruta = generar_docx(args.markdown, args.output)
    print(f"Documento Word generado: {ruta}")

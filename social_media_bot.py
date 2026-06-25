"""
Base compartida para bots de Instagram y Facebook.

El flujo de estas redes es distinto a LinkedIn. En vez de buscar por palabras
en toda la red, se entra al perfil oficial de cada banco, se revisan
publicaciones dentro del rango configurado y se leen comentarios publicos para
identificar denuncias de fraude. El conteo final es por publicacion con al
menos un comentario denunciante, no por cantidad de comentarios.
"""

import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import proyecto


MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

PATRONES_CARGAR_COMENTARIOS = [
    re.compile(r"ver\s+todos?\s+los\s+comentarios?", re.IGNORECASE),
    re.compile(r"mostrar\s+todos?\s+los\s+comentarios?", re.IGNORECASE),
    re.compile(r"cargar\s+m[aá]s\s+comentarios?", re.IGNORECASE),
    re.compile(r"ver\s+m[aá]s\s+comentarios?", re.IGNORECASE),
    re.compile(r"ver\s+(?:los\s+)?\d+\s+comentarios?", re.IGNORECASE),
    re.compile(r"mostrar\s+m[aá]s\s+comentarios?", re.IGNORECASE),
    re.compile(r"m[aá]s\s+comentarios?", re.IGNORECASE),
    re.compile(r"comentarios?\s+anteriores", re.IGNORECASE),
    re.compile(r"view\s+all\s+\d+\s+comments?", re.IGNORECASE),
    re.compile(r"view\s+more\s+comments?", re.IGNORECASE),
    re.compile(r"view\s+hidden\s+comments?", re.IGNORECASE),
    re.compile(r"load\s+more\s+comments?", re.IGNORECASE),
    re.compile(r"more\s+comments?", re.IGNORECASE),
    re.compile(r"hidden\s+comments?", re.IGNORECASE),
    re.compile(r"previous\s+comments?", re.IGNORECASE),
    re.compile(r"ver\s+comentarios?\s+ocultos?", re.IGNORECASE),
    re.compile(r"mostrar\s+comentarios?\s+ocultos?", re.IGNORECASE),
]

PATRONES_EXPANDIR_TEXTO = [
    re.compile(r"^\s*m[aá]s\s*$", re.IGNORECASE),
    re.compile(r"ver\s+m[aá]s", re.IGNORECASE),
    re.compile(r"see\s+more", re.IGNORECASE),
]

TEXTOS_UI_EXACTOS = {
    "me gusta",
    "like",
    "responder",
    "reply",
    "ver traduccion",
    "ver traducción",
    "see translation",
    "seguir",
    "follow",
    "compartir",
    "share",
    "comentar",
    "comment",
}

CUENTAS_COMPARTIDAS = {
    "grupoaval",
    "experienciasaval",
    "dale.com.co",
}

TERMINOS_QUEJA_OPERATIVA = [
    "app",
    "aplicacion",
    "no funciona",
    "no deja",
    "no me deja",
    "caida",
    "caido",
    "bloqueada",
    "bloqueado",
    "clave",
    "asesor",
    "atencion",
    "servicio al cliente",
    "centrales",
    "centrales de riesgo",
    "datacredito",
    "cifin",
    "transunion",
    "consulta centrales",
    "consultan centrales",
    "cupo",
    "tarjeta erronea",
    "desbloquear",
    "pse",
    "mensaje",
    "mensajes",
]

TERMINOS_FRAUDE_CONCRETO = [
    "fraude",
    "fraudes",
    "fraudulento",
    "fraudulenta",
    "estafa",
    "estafas",
    "me estafaron",
    "estafaron",
    "estafador",
    "estafadores",
    "robo",
    "robos",
    "robaron",
    "me robaron",
    "suplantacion",
    "suplantaciones",
    "suplantaron",
    "phishing",
    "vishing",
    "smishing",
    "qr falso",
    "cuenta falsa",
    "llamada fraudulenta",
    "whatsapp falso",
    "correo falso",
    "correos falsos",
    "transaccion no reconocida",
    "transaccion no autorizada",
    "movimiento no reconocido",
    "movimiento no autorizado",
    "sin mi autorizacion",
    "sin su autorizacion",
    "no autorice",
    "no solicite",
    "credito no solicitado",
    "sacaron un credito",
    "sacaron dinero",
    "me quitaron",
    "me vaciaron",
    "clonaron",
    "hackearon",
    "hurtaron",
    "hurto",
    "productos fraudulentos",
]


def cargar_credenciales_red(usuario_clave, contrasena_clave):
    datos = proyecto.leer_archivo_env(proyecto.RUTA_CREDENCIALES)
    usuario = datos.get(usuario_clave) or datos.get(usuario_clave.lower())
    contrasena = datos.get(contrasena_clave) or datos.get(contrasena_clave.lower())

    if not usuario or not contrasena:
        raise ValueError(
            f"Faltan credenciales en .env: {usuario_clave} y {contrasena_clave}."
        )

    return usuario, contrasena


def perfil_red(nombre):
    return Path(__file__).with_name(f".perfil_chromium_{nombre}")


def abrir_contexto_chromium(playwright, nombre_red):
    context = playwright.chromium.launch_persistent_context(
        str(perfil_red(nombre_red)),
        headless=False,
        slow_mo=250,
        no_viewport=True,
        args=[
            "--start-maximized",
            "--window-position=60,40",
            "--window-size=1440,920",
        ],
    )
    page = context.pages[0] if context.pages else context.new_page()
    proyecto.hacer_visible_ventana_chromium(page)
    return context, page


def escribir_en_primer_input_visible(page, selectores, valor, nombre):
    for selector in selectores:
        elementos = page.locator(selector)
        try:
            cantidad = elementos.count()
        except Exception:
            continue

        for indice in range(cantidad):
            elemento = elementos.nth(indice)
            try:
                if elemento.is_visible() and elemento.is_enabled():
                    print(f"{nombre}: usando elemento visible #{indice}")
                    proyecto.escribir_texto_como_humano(elemento, valor)
                    return True
            except Exception:
                continue

    return False


def hacer_login_generico(page, login_url, usuario, contrasena, nombre_red):
    print(f"Abriendo {nombre_red}...")
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    proyecto.hacer_visible_ventana_chromium(page)
    time.sleep(5)

    escribio_usuario = escribir_en_primer_input_visible(
        page,
        [
            "input[name='username']",
            "input[name='email']",
            "input[type='email']",
            "input[type='text']",
        ],
        usuario,
        "usuario",
    )
    escribio_contrasena = escribir_en_primer_input_visible(
        page,
        ["input[name='password']", "input[type='password']"],
        contrasena,
        "contraseña",
    )

    if escribio_usuario and escribio_contrasena:
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
        print(f"Login enviado a {nombre_red}.")
    else:
        print(
            f"No se detectaron campos de login de {nombre_red}. "
            "Si ya habia sesion, continua manualmente."
        )


def esperar_confirmacion_red(page, nombre_red):
    while True:
        texto = input(
            f"Cuando la sesion de {nombre_red} este lista, presiona ENTER..."
        ).strip()

        if not texto:
            return

        if texto.upper().startswith("CODIGO:"):
            proyecto.ingresar_codigo_verificacion(page, texto.split(":", 1)[1])
            continue

        print("Comando no reconocido. Usa CODIGO:123456 o ENTER para continuar.")


def normalizar_url_publicacion(href, base_url):
    if not href:
        return ""

    url = urljoin(base_url, href)
    partes = urlsplit(url)
    query = partes.query if "story_fbid=" in partes.query else ""

    return urlunsplit((partes.scheme, partes.netloc, partes.path, query, ""))


def usuario_desde_url(url):
    partes = urlsplit(url or "")
    segmentos = [segmento for segmento in partes.path.split("/") if segmento]

    if not segmentos:
        return ""

    if segmentos[0] in {"p", "reel", "tv", "permalink.php", "story.php", "watch"}:
        return ""

    return segmentos[0].lower()


def aliases_banco_social(definicion, banco):
    aliases = list(proyecto.CRITERIOS_RELEVANCIA["aliases_bancos"].get(banco, [banco]))
    perfil = definicion.get("perfiles", {}).get(banco, "")
    usuario = usuario_desde_url(perfil)

    if usuario and usuario not in aliases:
        aliases.append(usuario)

    return aliases


def bancos_mencionados_en_texto(texto, definicion):
    menciones = []
    texto_normalizado = f" {proyecto.normalizar_texto_busqueda(texto)} "

    for banco in proyecto.CRITERIOS_RELEVANCIA["aliases_bancos"]:
        puntaje = 0
        aliases_encontrados = []

        for alias in aliases_banco_social(definicion, banco):
            alias_normalizado = proyecto.normalizar_texto_busqueda(alias)
            if not alias_normalizado:
                continue
            if f" {alias_normalizado} " not in texto_normalizado:
                continue

            aliases_encontrados.append(alias)
            puntaje += max(1, len(alias_normalizado.split()))

        if aliases_encontrados:
            menciones.append(
                {
                    "banco": banco,
                    "puntaje": puntaje,
                    "aliases": aliases_encontrados,
                }
            )

    menciones.sort(key=lambda item: (-item["puntaje"], item["banco"]))
    return menciones


def banco_principal_mencionado(texto, definicion):
    menciones = bancos_mencionados_en_texto(texto, definicion)
    return menciones[0] if menciones else None


def requiere_banco_explicito(perfil_url, post_url):
    usuario_perfil = usuario_desde_url(perfil_url)
    usuario_post = usuario_desde_url(post_url)

    if usuario_post in CUENTAS_COMPARTIDAS:
        return True

    return bool(usuario_post and usuario_perfil and usuario_post != usuario_perfil)


def es_url_publicacion(url, definicion):
    return any(
        re.search(patron, url, re.IGNORECASE)
        for patron in definicion.get("patrones_url_publicacion", [])
    )


def recolectar_urls_publicaciones(page, perfil_url, definicion, limite):
    urls = []
    vistos = set()
    intentos_sin_cambios = 0
    intentos_maximos = max(8, min(30, limite * 2))

    for _ in range(intentos_maximos):
        enlaces = page.locator("a[href]")
        try:
            cantidad = min(enlaces.count(), 800)
        except Exception:
            cantidad = 0

        for indice in range(cantidad):
            try:
                href = enlaces.nth(indice).get_attribute("href") or ""
            except Exception:
                continue

            url = normalizar_url_publicacion(href, perfil_url)
            if not url or url in vistos or not es_url_publicacion(url, definicion):
                continue

            vistos.add(url)
            urls.append(url)

            if len(urls) >= limite:
                return urls

        cantidad_previa = len(urls)
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(2200)

        if len(urls) == cantidad_previa:
            intentos_sin_cambios += 1
        else:
            intentos_sin_cambios = 0

        if intentos_sin_cambios >= 4:
            break

    return urls[:limite]


def texto_control(elemento):
    partes = []
    for getter in (
        lambda: elemento.inner_text(timeout=700),
        lambda: elemento.get_attribute("aria-label") or "",
        lambda: elemento.get_attribute("title") or "",
    ):
        try:
            valor = getter()
        except Exception:
            valor = ""
        if valor:
            partes.append(valor)

    return proyecto.limpiar_linea(" ".join(partes))


def click_controles(page, patrones, max_clicks=1, excluir_respuestas=True):
    controles = page.locator("button, div[role='button'], span[role='button'], a[role='button']")
    clicks = 0

    try:
        cantidad = min(controles.count(), 250)
    except Exception:
        return clicks

    for indice in range(cantidad):
        if clicks >= max_clicks:
            break

        control = controles.nth(indice)
        texto = texto_control(control)
        texto_normalizado = proyecto.normalizar_texto_busqueda(texto)

        if not texto_normalizado:
            continue
        if excluir_respuestas and (
            "respuesta" in texto_normalizado or "reply" in texto_normalizado
        ):
            continue
        if not any(patron.search(texto) for patron in patrones):
            continue

        try:
            if control.is_visible() and control.is_enabled():
                control.click(timeout=1500)
                clicks += 1
                page.wait_for_timeout(1200)
        except Exception:
            continue

    return clicks


def cargar_comentarios_visibles(page, max_comentarios):
    iteraciones = max(4, min(20, max_comentarios // 25 + 2))
    ciclos_sin_clicks = 0

    for _ in range(iteraciones):
        clicks = click_controles(page, PATRONES_CARGAR_COMENTARIOS, max_clicks=4)
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(900)

        if clicks:
            ciclos_sin_clicks = 0
        else:
            ciclos_sin_clicks += 1

        if ciclos_sin_clicks >= 3:
            break


def expandir_texto_visible(page):
    click_controles(
        page,
        PATRONES_EXPANDIR_TEXTO,
        max_clicks=6,
        excluir_respuestas=True,
    )


def parsear_fecha_iso(valor):
    if not valor:
        return None

    texto = valor.strip().replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        return None


def parsear_fecha_texto(valor):
    texto = proyecto.normalizar_texto_busqueda(valor)
    coincidencia = re.search(
        r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})",
        texto,
    )

    if not coincidencia:
        return None

    dia = int(coincidencia.group(1))
    mes = MESES.get(coincidencia.group(2))
    anio = int(coincidencia.group(3))

    if not mes:
        return None

    try:
        return datetime(anio, mes, dia).date()
    except ValueError:
        return None


def extraer_fecha_publicacion(page):
    selectores = [
        "time[datetime]",
        "abbr[data-utime]",
        "meta[property='article:published_time']",
    ]

    for selector in selectores:
        elementos = page.locator(selector)
        try:
            cantidad = min(elementos.count(), 5)
        except Exception:
            continue

        for indice in range(cantidad):
            elemento = elementos.nth(indice)
            for atributo in ("datetime", "data-utime", "content", "title", "aria-label"):
                try:
                    valor = elemento.get_attribute(atributo)
                except Exception:
                    valor = ""

                if not valor:
                    continue
                if atributo == "data-utime":
                    try:
                        return datetime.fromtimestamp(int(valor)).date(), valor
                    except (TypeError, ValueError):
                        continue

                fecha = parsear_fecha_iso(valor) or parsear_fecha_texto(valor)
                if fecha:
                    return fecha, valor

            try:
                texto = elemento.inner_text(timeout=700)
            except Exception:
                texto = ""

            fecha = parsear_fecha_texto(texto)
            if fecha:
                return fecha, texto

    return None, ""


def texto_es_ui(texto):
    normalizado = proyecto.normalizar_texto_busqueda(texto)

    if not normalizado or len(normalizado) < 12:
        return True
    if normalizado in TEXTOS_UI_EXACTOS:
        return True
    if normalizado.startswith(("ver ", "view ")) and "comentario" in normalizado:
        return True
    if normalizado.startswith("view ") and "comment" in normalizado:
        return True
    if normalizado.startswith(("ver ", "view ")) and "respuesta" in normalizado:
        return True
    if "these comments were hidden" in normalizado:
        return True
    if normalizado.startswith(("http ", "https ", "www ")):
        return True

    return False


def candidatos_desde_texto(texto):
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    lineas = [
        proyecto.limpiar_linea(linea)
        for linea in texto.split("\n")
        if proyecto.limpiar_linea(linea)
    ]

    if not lineas:
        return []

    unido = proyecto.limpiar_linea(" ".join(lineas))
    if len(lineas) <= 4 and len(unido) <= 900:
        return [unido]

    return [linea for linea in lineas if len(linea) <= 900]


def extraer_comentarios_publicos(page, definicion, max_comentarios):
    comentarios = []
    vistos = set()

    for selector in definicion.get("selectores_comentario", []):
        elementos = page.locator(selector)
        try:
            cantidad = min(elementos.count(), 500)
        except Exception:
            continue

        for indice in range(cantidad):
            if len(comentarios) >= max_comentarios:
                return comentarios

            try:
                texto = elementos.nth(indice).inner_text(timeout=1200)
            except Exception:
                continue

            for candidato in candidatos_desde_texto(texto):
                if len(comentarios) >= max_comentarios:
                    return comentarios
                if texto_es_ui(candidato):
                    continue

                clave = proyecto.normalizar_texto_busqueda(candidato)[:500]
                if clave in vistos:
                    continue

                vistos.add(clave)
                comentarios.append(candidato)

    return comentarios


def es_queja_operativa(comentario, terminos_fraude, terminos_fuertes):
    terminos_operativos = proyecto.buscar_terminos(
        comentario,
        TERMINOS_QUEJA_OPERATIVA,
    )
    terminos_concretos = proyecto.buscar_terminos(
        comentario,
        TERMINOS_FRAUDE_CONCRETO,
    )

    if not terminos_operativos:
        return False, ""

    if terminos_concretos:
        return False, ""

    terminos_genericos = {
        proyecto.normalizar_texto_busqueda(termino)
        for termino in terminos_fraude + terminos_fuertes
    }
    solo_genericos = terminos_genericos <= {
        "denuncia",
        "denunciar",
        "sin autorizacion",
        "no autorizado",
        "no autorizada",
    }

    if solo_genericos:
        return True, ", ".join(terminos_operativos)

    return False, ""


def evaluar_comentario_denuncia(banco, comentario):
    evaluacion = proyecto.evaluar_relevancia_publicacion(
        banco,
        comentario,
        f"{banco}\n{comentario}",
    )

    terminos_fraude = proyecto.buscar_terminos(
        comentario,
        proyecto.CRITERIOS_RELEVANCIA["terminos_fraude"],
    )
    terminos_fuertes = proyecto.buscar_terminos(
        comentario,
        proyecto.CRITERIOS_RELEVANCIA["terminos_fraude_fuertes"],
    )
    terminos_contexto = proyecto.buscar_terminos(
        comentario,
        proyecto.CRITERIOS_RELEVANCIA["terminos_contexto_denuncia"],
    )
    terminos_bancarios = proyecto.buscar_terminos(
        comentario,
        proyecto.CRITERIOS_RELEVANCIA["terminos_contexto_bancario"],
    )
    terminos_educativos = proyecto.buscar_terminos(
        comentario,
        proyecto.CRITERIOS_RELEVANCIA["terminos_educativos_preventivos"],
    )
    es_operativa, terminos_operativos = es_queja_operativa(
        comentario,
        terminos_fraude,
        terminos_fuertes,
    )

    if es_operativa:
        return {
            "es_relevante": False,
            "relevancia": "descartada",
            "motivo": "Queja operativa o de servicio, no denuncia de fraude",
            "tipo_contenido": "queja_operativa",
            "terminos_banco": banco,
            "terminos_fraude": ", ".join(terminos_fraude),
            "terminos_contexto": ", ".join(terminos_contexto),
            "terminos_contexto_bancario": ", ".join(terminos_bancarios),
            "terminos_exclusion": terminos_operativos,
        }

    if evaluacion["es_relevante"]:
        return evaluacion

    es_denuncia = bool(
        terminos_fraude
        and (terminos_contexto or terminos_bancarios or terminos_fuertes)
        and not (terminos_educativos and not terminos_contexto)
    )

    if not es_denuncia:
        return evaluacion

    return {
        "es_relevante": True,
        "relevancia": "alta" if terminos_fuertes else "media",
        "motivo": "Comentario publico en perfil oficial con denuncia de fraude",
        "tipo_contenido": "denuncia_directa",
        "terminos_banco": banco,
        "terminos_fraude": ", ".join(terminos_fraude),
        "terminos_contexto": ", ".join(terminos_contexto),
        "terminos_contexto_bancario": ", ".join(terminos_bancarios),
        "terminos_exclusion": "",
    }


def clasificar_comentarios(banco_perfil, comentarios, definicion, perfil_url, post_url):
    relevantes_por_banco = {}
    auditoria = {
        "quejas_operativas": [],
        "sin_banco_explicito": [],
        "reasignados": [],
    }
    exige_banco = requiere_banco_explicito(perfil_url, post_url)

    for comentario in comentarios:
        mencion = banco_principal_mencionado(comentario, definicion)

        if mencion:
            banco_evaluado = mencion["banco"]
            if banco_evaluado != banco_perfil:
                auditoria["reasignados"].append(
                    f"{banco_perfil} -> {banco_evaluado}: {comentario}"
                )
        elif exige_banco:
            auditoria["sin_banco_explicito"].append(comentario)
            continue
        else:
            banco_evaluado = banco_perfil

        evaluacion = evaluar_comentario_denuncia(banco_evaluado, comentario)

        if evaluacion["tipo_contenido"] == "queja_operativa":
            auditoria["quejas_operativas"].append(comentario)

        if not evaluacion["es_relevante"]:
            continue

        relevantes_por_banco.setdefault(banco_evaluado, []).append(
            {
                "texto": comentario,
                "evaluacion": evaluacion,
            }
        )

    return relevantes_por_banco, auditoria


def unir_valores(registros, campo):
    valores = []

    for registro in registros:
        texto = registro["evaluacion"].get(campo, "")
        for parte in texto.split(","):
            valor = proyecto.limpiar_linea(parte)
            if valor and valor not in valores:
                valores.append(valor)

    return ", ".join(valores)


def texto_publicacion_visible(page):
    for selector in ("article", "div[role='article']", "main", "body"):
        try:
            elemento = page.locator(selector).first
            if elemento.count() and elemento.is_visible():
                texto = proyecto.limpiar_texto_publicacion(
                    elemento.inner_text(timeout=3000)
                )
                if texto:
                    return texto[:3000]
        except Exception:
            continue

    return ""


def enfocar_comentario_relevante(page, comentarios_denuncia):
    if not comentarios_denuncia:
        return False

    comentario = comentarios_denuncia[0].get("texto", "")
    comentario_normalizado = proyecto.normalizar_texto_busqueda(comentario)
    fragmento = comentario_normalizado[:120]

    if len(fragmento) < 20:
        return False

    elementos = page.locator("span, li, div[role='button'], div[dir='auto'], article")
    try:
        cantidad = min(elementos.count(), 700)
    except Exception:
        return False

    for indice in range(cantidad):
        elemento = elementos.nth(indice)
        try:
            texto = elemento.inner_text(timeout=600)
        except Exception:
            continue

        texto_normalizado = proyecto.normalizar_texto_busqueda(texto)
        if fragmento not in texto_normalizado:
            continue

        try:
            elemento.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(800)
            return True
        except Exception:
            return False

    return False


def capturar_pagina_publicacion(
    page,
    banco,
    contadores_seriales,
    fecha_archivo,
    comentarios_denuncia=None,
):
    serial = proyecto.siguiente_serial_banco(
        contadores_seriales,
        banco,
        "publicaciones",
    )
    imagen_serial = f"{proyecto.normalizar_nombre_archivo(banco)}_{serial:04d}"
    carpeta = (
        proyecto.RUTA_CAPTURAS
        / "publicaciones"
        / proyecto.normalizar_nombre_archivo(banco)
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{fecha_archivo}_{imagen_serial}.png"

    try:
        enfocar_comentario_relevante(page, comentarios_denuncia or [])
        page.screenshot(path=str(ruta), timeout=15000, animations="disabled")
    except Exception as exc:
        print(f"No se pudo capturar la publicacion {imagen_serial}: {exc}")
        return serial, imagen_serial, "", ""

    return (
        serial,
        imagen_serial,
        proyecto.ruta_relativa_proyecto(ruta),
        ruta.name,
    )


def registro_publicacion_con_denuncia(
    page,
    banco,
    perfil_url,
    post_url,
    fecha_publicacion,
    fecha_visible,
    configuracion,
    contadores_seriales,
    comentarios_denuncia,
):
    serial, imagen_serial, ruta_imagen, nombre_imagen = capturar_pagina_publicacion(
        page,
        banco,
        contadores_seriales,
        configuracion.get("fecha_ejecucion_archivo"),
        comentarios_denuncia,
    )
    texto_post = texto_publicacion_visible(page)
    comentarios_texto = "\n".join(
        f"- {registro['texto']}" for registro in comentarios_denuncia
    )
    fecha_iso = fecha_publicacion.isoformat() if fecha_publicacion else ""
    fecha_en_rango = "si"

    if fecha_publicacion and not proyecto.esta_en_rango(
        fecha_iso,
        configuracion["fecha_inicio"],
        configuracion["fecha_fin"],
    ):
        fecha_en_rango = "no"
    elif not fecha_publicacion:
        fecha_en_rango = "sin_fecha"

    return {
        "imagen_serial": imagen_serial,
        "serial_por_banco": serial,
        "imagen_publicacion": ruta_imagen,
        "archivo_imagen": nombre_imagen,
        "tipo_resultado": "publicaciones",
        "banco": banco,
        "busqueda": perfil_url,
        "autor": banco,
        "fecha_visible": fecha_visible,
        "fecha_publicacion_estimada": fecha_iso,
        "fecha_en_rango": fecha_en_rango,
        "rango_fecha": proyecto.formatear_rango_fecha(configuracion),
        "rango_fecha_inicio": configuracion["fecha_inicio"].isoformat(),
        "rango_fecha_fin": configuracion["fecha_fin"].isoformat(),
        "tipo_contenido": "denuncia_directa",
        "terminos_banco": banco,
        "terminos_fraude": unir_valores(comentarios_denuncia, "terminos_fraude"),
        "terminos_contexto": unir_valores(comentarios_denuncia, "terminos_contexto"),
        "terminos_contexto_bancario": unir_valores(
            comentarios_denuncia,
            "terminos_contexto_bancario",
        ),
        "terminos_exclusion": unir_valores(comentarios_denuncia, "terminos_exclusion"),
        "texto": (
            f"Perfil oficial: {perfil_url}\n"
            f"Publicacion: {post_url}\n\n"
            f"Texto visible:\n{texto_post}\n\n"
            f"Comentarios publicos relevantes:\n{comentarios_texto}"
        ),
        "reacciones": "",
        "comentarios": len(comentarios_denuncia),
        "compartidos": "",
        "interacciones_total": len(comentarios_denuncia),
        "url": post_url,
        "fecha_recoleccion": datetime.now().isoformat(timespec="seconds"),
        "relevancia": "alta",
        "motivo_relevancia": "Publicacion con comentarios publicos de denuncia",
    }


def registro_descartado(
    banco,
    perfil_url,
    post_url,
    fecha_publicacion,
    fecha_visible,
    configuracion,
    comentarios_revisados,
    motivo,
    comentarios_muestra=None,
    tipo_contenido="comentarios_sin_denuncia",
):
    fecha_iso = fecha_publicacion.isoformat() if fecha_publicacion else ""
    fecha_en_rango = "sin_fecha"

    if fecha_publicacion:
        fecha_en_rango = (
            "si"
            if proyecto.esta_en_rango(
                fecha_iso,
                configuracion["fecha_inicio"],
                configuracion["fecha_fin"],
            )
            else "no"
        )

    if comentarios_muestra:
        comentarios_texto = "\n".join(
            f"- {comentario}" for comentario in comentarios_muestra[:30]
        )
    else:
        comentarios_texto = ""

    return {
        "imagen_serial": "",
        "serial_por_banco": "",
        "imagen_publicacion": "",
        "archivo_imagen": "",
        "tipo_resultado": "descartadas",
        "banco": banco,
        "busqueda": perfil_url,
        "autor": banco,
        "fecha_visible": fecha_visible,
        "fecha_publicacion_estimada": fecha_iso,
        "fecha_en_rango": fecha_en_rango,
        "rango_fecha": proyecto.formatear_rango_fecha(configuracion),
        "rango_fecha_inicio": configuracion["fecha_inicio"].isoformat(),
        "rango_fecha_fin": configuracion["fecha_fin"].isoformat(),
        "tipo_contenido": tipo_contenido,
        "relevancia": "descartada",
        "motivo_relevancia": motivo,
        "terminos_banco": banco,
        "terminos_fraude": "",
        "terminos_contexto": "",
        "terminos_contexto_bancario": "",
        "terminos_exclusion": "",
        "texto": (
            f"Perfil oficial: {perfil_url}\n"
            f"Publicacion revisada: {post_url}\n"
            f"Comentarios publicos revisados: {comentarios_revisados}"
            + (
                f"\n\nComentarios revisados de muestra:\n{comentarios_texto}"
                if comentarios_texto
                else ""
            )
        ),
        "reacciones": "",
        "comentarios": comentarios_revisados,
        "compartidos": "",
        "interacciones_total": 0,
        "url": post_url,
        "fecha_recoleccion": datetime.now().isoformat(timespec="seconds"),
    }


def fecha_fuera_de_rango(fecha_publicacion, configuracion):
    if not fecha_publicacion:
        return False

    return not proyecto.esta_en_rango(
        fecha_publicacion.isoformat(),
        configuracion["fecha_inicio"],
        configuracion["fecha_fin"],
    )


def guardar_diagnostico_perfil(page, banco, definicion):
    carpeta = proyecto.RUTA_EJECUCION / "diagnostico"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre_base = (
        f"{definicion['nombre']}_"
        f"{proyecto.normalizar_nombre_archivo(banco)}_sin_publicaciones"
    )
    ruta_txt = carpeta / f"{nombre_base}.txt"
    ruta_png = carpeta / f"{nombre_base}.png"

    enlaces = []
    elementos = page.locator("a[href]")
    try:
        cantidad_enlaces = min(elementos.count(), 120)
    except Exception:
        cantidad_enlaces = 0

    for indice in range(cantidad_enlaces):
        elemento = elementos.nth(indice)
        try:
            href = elemento.get_attribute("href") or ""
        except Exception:
            href = ""
        try:
            texto = proyecto.limpiar_linea(elemento.inner_text(timeout=500))
        except Exception:
            texto = ""
        if href or texto:
            enlaces.append(f"{indice + 1}. {href} | {texto[:160]}")

    try:
        titulo = page.title()
    except Exception:
        titulo = ""
    try:
        texto_body = page.locator("body").inner_text(timeout=3000)
    except Exception:
        texto_body = ""

    contenido = [
        f"Red: {definicion['nombre_visible']}",
        f"Banco: {banco}",
        f"URL actual: {page.url}",
        f"Titulo: {titulo}",
        f"Total enlaces muestreados: {cantidad_enlaces}",
        "",
        "Enlaces:",
        "\n".join(enlaces[:120]),
        "",
        "Texto visible:",
        proyecto.limpiar_texto_publicacion(texto_body)[:5000],
    ]
    ruta_txt.write_text("\n".join(contenido), encoding="utf-8")

    try:
        page.screenshot(path=str(ruta_png), full_page=True, timeout=15000)
    except Exception as exc:
        print(f"No se pudo guardar captura de diagnostico: {exc}")

    print(f"Diagnostico guardado: {ruta_txt}")


def ejecutar_perfil_banco(
    page,
    banco,
    perfil_url,
    configuracion,
    definicion,
    indice,
    total,
    contadores_seriales,
):
    publicaciones = []
    descartadas = []
    max_publicaciones = configuracion["max_publicaciones_por_banco"]
    max_comentarios = configuracion["max_comentarios_por_publicacion"]
    inicio_perf = time.perf_counter()
    inicio = datetime.now()

    print(f"[{indice}/{total}] Revisando perfil {definicion['nombre_visible']}: {banco}")
    page.goto(perfil_url, wait_until="domcontentloaded", timeout=60000)
    proyecto.hacer_visible_ventana_chromium(page)
    page.wait_for_timeout(5000)

    urls = recolectar_urls_publicaciones(
        page,
        perfil_url,
        definicion,
        max_publicaciones,
    )
    print(f"Publicaciones encontradas para revisar en {banco}: {len(urls)}")
    if not urls:
        guardar_diagnostico_perfil(page, banco, definicion)

    antiguas_consecutivas = 0

    for post_indice, post_url in enumerate(urls, start=1):
        print(f"  Publicacion {post_indice}/{len(urls)}")
        page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        proyecto.hacer_visible_ventana_chromium(page)
        page.wait_for_timeout(3500)
        expandir_texto_visible(page)
        cargar_comentarios_visibles(page, max_comentarios)

        fecha_publicacion, fecha_visible = extraer_fecha_publicacion(page)

        if (
            configuracion["filtrar_por_fecha"]
            and fecha_publicacion
            and fecha_publicacion < configuracion["fecha_inicio"]
        ):
            antiguas_consecutivas += 1
            descartadas.append(
                registro_descartado(
                    banco,
                    perfil_url,
                    post_url,
                    fecha_publicacion,
                    fecha_visible,
                    configuracion,
                    0,
                    "Publicacion anterior al rango configurado",
                )
            )
            if antiguas_consecutivas >= 3:
                print("  Se encontraron varias publicaciones antiguas; se detiene este perfil.")
                break
            continue

        antiguas_consecutivas = 0

        if (
            configuracion["filtrar_por_fecha"]
            and fecha_publicacion
            and fecha_fuera_de_rango(fecha_publicacion, configuracion)
        ):
            descartadas.append(
                registro_descartado(
                    banco,
                    perfil_url,
                    post_url,
                    fecha_publicacion,
                    fecha_visible,
                    configuracion,
                    0,
                    "Publicacion fuera del rango configurado",
                )
            )
            continue

        comentarios = extraer_comentarios_publicos(
            page,
            definicion,
            max_comentarios,
        )
        relevantes_por_banco, auditoria = clasificar_comentarios(
            banco,
            comentarios,
            definicion,
            perfil_url,
            post_url,
        )

        if relevantes_por_banco:
            for banco_asignado, relevantes in relevantes_por_banco.items():
                publicaciones.append(
                    registro_publicacion_con_denuncia(
                        page,
                        banco_asignado,
                        perfil_url,
                        post_url,
                        fecha_publicacion,
                        fecha_visible,
                        configuracion,
                        contadores_seriales,
                        relevantes,
                    )
                )
            continue

        if configuracion["guardar_descartadas"]:
            comentarios_muestra = comentarios
            tipo_descartado = "comentarios_sin_denuncia"
            motivo = "No se encontraron comentarios publicos de denuncia"

            if auditoria["quejas_operativas"]:
                comentarios_muestra = auditoria["quejas_operativas"]
                tipo_descartado = "queja_operativa"
                motivo = "Se encontraron quejas operativas, no denuncia de fraude"
            elif auditoria["sin_banco_explicito"]:
                comentarios_muestra = auditoria["sin_banco_explicito"]
                motivo = (
                    "Post compartido o de tercero sin banco explicito en "
                    "comentarios de denuncia"
                )

            descartadas.append(
                registro_descartado(
                    banco,
                    perfil_url,
                    post_url,
                    fecha_publicacion,
                    fecha_visible,
                    configuracion,
                    len(comentarios),
                    motivo,
                    comentarios_muestra,
                    tipo_descartado,
                )
            )

    fin = datetime.now()
    duracion = round(time.perf_counter() - inicio_perf, 2)
    tiempo = {
        "tipo_tiempo": "busqueda",
        "banco": banco,
        "busqueda": perfil_url,
        "indice_busqueda": indice,
        "total_busquedas": total,
        "inicio": inicio.isoformat(timespec="seconds"),
        "fin": fin.isoformat(timespec="seconds"),
        "duracion_segundos": duracion,
        "duracion_minutos": round(duracion / 60, 2),
        "publicaciones_relevantes": len(publicaciones),
        "publicaciones_descartadas": len(descartadas),
        "resultados_total": len(publicaciones) + len(descartadas),
    }

    print(f"Publicaciones con denuncias para {banco}: {len(publicaciones)}")
    print(f"Publicaciones descartadas para {banco}: {len(descartadas)}")

    return publicaciones, descartadas, tiempo


def bancos_disponibles_para_red(configuracion, definicion):
    perfiles = definicion["perfiles"]
    bancos = []
    omitidos = []

    for banco in configuracion["bancos_seleccionados"]:
        if banco in perfiles:
            bancos.append(banco)
        else:
            omitidos.append(banco)

    for banco in omitidos:
        print(
            f"{banco} no tiene perfil configurado en "
            f"{definicion['nombre_visible']}, se omite."
        )

    if not bancos:
        raise ValueError(
            f"No hay bancos seleccionados con perfil de {definicion['nombre_visible']}."
        )

    return bancos


def ejecutar_busquedas_red(page, configuracion, definicion):
    publicaciones = []
    descartadas = []
    tiempos = []
    contadores_seriales = {}
    bancos = bancos_disponibles_para_red(configuracion, definicion)
    configuracion["bancos_seleccionados"] = bancos
    inicio_total_perf = time.perf_counter()
    inicio_total = datetime.now()

    print(f"Plataforma: {definicion['nombre_visible']}")
    print(f"Bancos seleccionados ({len(bancos)}): {', '.join(bancos)}")
    print(
        "Limites: "
        f"{configuracion['max_publicaciones_por_banco']} publicaciones por banco, "
        f"{configuracion['max_comentarios_por_publicacion']} comentarios por publicacion"
    )
    print("Respuestas a comentarios: no")

    for indice, banco in enumerate(bancos, start=1):
        perfil_url = definicion["perfiles"][banco]
        publicaciones_banco, descartadas_banco, tiempo_banco = ejecutar_perfil_banco(
            page,
            banco,
            perfil_url,
            configuracion,
            definicion,
            indice,
            len(bancos),
            contadores_seriales,
        )
        publicaciones.extend(publicaciones_banco)
        descartadas.extend(descartadas_banco)
        tiempos.append(tiempo_banco)

    publicaciones = proyecto.deduplicar_publicaciones(publicaciones)
    descartadas = proyecto.deduplicar_publicaciones(descartadas)
    fin_total = datetime.now()
    duracion_total = round(time.perf_counter() - inicio_total_perf, 2)
    tiempos.append(
        {
            "tipo_tiempo": "total_proyecto",
            "banco": "TOTAL",
            "busqueda": "TOTAL",
            "indice_busqueda": "",
            "total_busquedas": len(bancos),
            "inicio": inicio_total.isoformat(timespec="seconds"),
            "fin": fin_total.isoformat(timespec="seconds"),
            "duracion_segundos": duracion_total,
            "duracion_minutos": round(duracion_total / 60, 2),
            "publicaciones_relevantes": len(publicaciones),
            "publicaciones_descartadas": len(descartadas),
            "resultados_total": len(publicaciones) + len(descartadas),
        }
    )

    conteo = proyecto.guardar_resultados(
        publicaciones,
        descartadas,
        configuracion,
        tiempos,
    )
    print(f"Recoleccion finalizada en {definicion['nombre_visible']}.")
    print(f"Total de publicaciones con denuncias: {len(publicaciones)}")
    print("Conteo por banco:")
    for banco, total in conteo.items():
        print(f"- {banco}: {total}")


def ejecutar_bot_red(definicion):
    configuracion = proyecto.preparar_rutas_ejecucion(proyecto.cargar_configuracion())
    usuario, contrasena = cargar_credenciales_red(
        definicion["usuario_env"],
        definicion["contrasena_env"],
    )

    print("Credenciales cargadas correctamente.")
    print("Usuario: ********")
    print("Contraseña: ********")
    print(f"Fecha de ejecución: {configuracion['fecha_ejecucion_archivo']}")
    print(f"Carpeta de ejecución: {proyecto.RUTA_EJECUCION}")

    with sync_playwright() as p:
        context, page = abrir_contexto_chromium(p, definicion["nombre"])
        try:
            hacer_login_generico(
                page,
                definicion["login_url"],
                usuario,
                contrasena,
                definicion["nombre_visible"],
            )
            print(
                f"Si {definicion['nombre_visible']} pide código, captcha o "
                "verificación, complétalo o envía el código desde la interfaz."
            )
            esperar_confirmacion_red(page, definicion["nombre_visible"])
            ejecutar_busquedas_red(page, configuracion, definicion)
            print("El navegador quedará abierto.")
            input("Presiona ENTER en esta consola cuando quieras cerrar el navegador...")
        except PlaywrightTimeoutError as exc:
            print(f"Error de tiempo en {definicion['nombre_visible']}:")
            print(exc)
            input("Presiona ENTER para cerrar el navegador...")
        except Exception as exc:
            print("Ocurrió un error inesperado:")
            print(exc)
            input("Presiona ENTER para cerrar el navegador...")
        finally:
            context.close()

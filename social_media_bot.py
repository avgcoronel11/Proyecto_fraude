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
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import proyecto


MESES = {
    "enero": 1,
    "ene": 1,
    "january": 1,
    "jan": 1,
    "febrero": 2,
    "feb": 2,
    "february": 2,
    "marzo": 3,
    "mar": 3,
    "march": 3,
    "abril": 4,
    "abr": 4,
    "april": 4,
    "apr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "june": 6,
    "julio": 7,
    "jul": 7,
    "july": 7,
    "agosto": 8,
    "ago": 8,
    "august": 8,
    "aug": 8,
    "septiembre": 9,
    "setiembre": 9,
    "sept": 9,
    "sep": 9,
    "september": 9,
    "octubre": 10,
    "oct": 10,
    "october": 10,
    "noviembre": 11,
    "nov": 11,
    "november": 11,
    "diciembre": 12,
    "dic": 12,
    "december": 12,
    "dec": 12,
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
    "mas pertinentes",
    "más pertinentes",
    "most relevant",
    "todos los comentarios",
    "all comments",
}

PATRON_FECHA_COMPLETA = re.compile(
    r"\b(\d{1,2})\s+(?:de\s+)?([a-z]+)\s+(?:de\s+)?(\d{4})\b",
    re.IGNORECASE,
)
PATRON_FECHA_MES_PRIMERO = re.compile(
    r"\b([a-z]+)\s+(\d{1,2})\s+(?:de\s+)?(\d{4})\b",
    re.IGNORECASE,
)
PATRON_FECHA_SIN_ANIO = re.compile(
    r"\b(\d{1,2})\s+(?:de\s+)?([a-z]+)\b",
    re.IGNORECASE,
)
PATRON_FECHA_MES_PRIMERO_SIN_ANIO = re.compile(
    r"\b([a-z]+)\s+(\d{1,2})\b",
    re.IGNORECASE,
)

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
    parametros_permitidos = {
        clave: valor
        for clave, valor in parse_qsl(partes.query, keep_blank_values=True)
        if clave in {"fbid", "set", "story_fbid", "id"}
    }
    query = urlencode(parametros_permitidos)

    return urlunsplit((partes.scheme, partes.netloc, partes.path, query, ""))


def usuario_desde_url(url):
    partes = urlsplit(url or "")
    segmentos = [segmento for segmento in partes.path.split("/") if segmento]

    if not segmentos:
        return ""

    if segmentos[0] in {"p", "reel", "tv", "permalink.php", "story.php", "watch"}:
        return ""

    return segmentos[0].lower()


def slug_perfil_desde_url(url):
    partes = urlsplit(url or "")
    segmentos = [segmento for segmento in partes.path.split("/") if segmento]

    if not segmentos:
        return ""

    if segmentos[0] in {"p", "reel", "tv", "permalink.php", "story.php", "watch"}:
        return ""

    return segmentos[0]


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


def url_pertenece_a_perfil(url, perfil_url, definicion):
    ruta = urlsplit(url).path or ""
    usuario_perfil = usuario_desde_url(perfil_url)
    usuario_url = usuario_desde_url(url)
    nombre_red = definicion.get("nombre")

    if nombre_red == "instagram":
        if not usuario_perfil:
            return False
        if usuario_url:
            return usuario_url == usuario_perfil
        return bool(re.match(r"^/(?:p|reel|tv)/[^/]+/?$", ruta, re.IGNORECASE))

    if nombre_red != "facebook":
        return True

    if ruta.startswith("/reel/"):
        return True
    if ruta == "/photo" and "fbid=" in (urlsplit(url).query or ""):
        return True
    if usuario_perfil and usuario_url == usuario_perfil:
        return True
    if "story_fbid=" in (urlsplit(url).query or ""):
        return True

    return False


def url_seccion_publicaciones_facebook(perfil_url):
    usuario = slug_perfil_desde_url(perfil_url)
    if not usuario:
        return ""

    partes = urlsplit(perfil_url)
    query = partes.query or "locale=es_LA"

    return urlunsplit((partes.scheme, partes.netloc, f"/{usuario}/posts", query, ""))


def abrir_url_publicaciones(page, perfil_url, definicion):
    if definicion.get("nombre") != "facebook":
        return False

    url_publicaciones = url_seccion_publicaciones_facebook(perfil_url)
    if not url_publicaciones:
        return False

    try:
        print(f"Abriendo seccion de publicaciones: {url_publicaciones}")
        page.goto(url_publicaciones, wait_until="domcontentloaded", timeout=60000)
        proyecto.hacer_visible_ventana_chromium(page)
        page.wait_for_timeout(5000)
        return True
    except Exception as exc:
        print(f"No se pudo abrir URL de publicaciones: {exc}")
        return False


def abrir_seccion_publicaciones(page, perfil_url, definicion):
    if abrir_url_publicaciones(page, perfil_url, definicion):
        return True

    textos = definicion.get("seccion_publicaciones_textos", [])
    if not textos:
        return False

    for texto in textos:
        for selector in (
            f"a:has-text('{texto}')",
            f"div[role='tab']:has-text('{texto}')",
            f"span:has-text('{texto}')",
        ):
            try:
                elemento = page.locator(selector).first
                if elemento.count() <= 0 or not elemento.is_visible(timeout=1200):
                    continue
                elemento.click(timeout=2500)
                page.wait_for_timeout(3500)
                print(f"Seccion abierta: {texto}")
                return True
            except Exception:
                continue

    print("No se pudo abrir explicitamente la seccion Publicaciones; se continua desde el perfil.")
    return False


def enlace_coincide_con_perfil(elemento, href, banco, perfil_url, definicion):
    if definicion.get("nombre") != "facebook":
        return False

    usuario_perfil = usuario_desde_url(perfil_url)
    url = normalizar_url_publicacion(href, perfil_url)

    if usuario_perfil and usuario_desde_url(url) == usuario_perfil:
        return True

    try:
        texto = proyecto.normalizar_texto_busqueda(elemento.inner_text(timeout=700))
    except Exception:
        texto = ""

    banco_normalizado = proyecto.normalizar_texto_busqueda(banco)
    return bool(texto and banco_normalizado and banco_normalizado in texto)


def buscar_perfil_facebook(page, banco, perfil_url, definicion):
    if definicion.get("nombre") != "facebook":
        return False

    selectores_busqueda = [
        "input[aria-label='Buscar en Facebook'][type='search']",
        "input[placeholder='Buscar en Facebook'][type='search']",
        "input[role='combobox'][type='search']",
    ]

    if not escribir_en_primer_input_visible(
        page,
        selectores_busqueda,
        banco,
        "busqueda Facebook",
    ):
        print("No se encontro el campo Buscar en Facebook.")
        return False

    try:
        page.keyboard.press("Enter")
        page.wait_for_timeout(6000)
    except Exception:
        pass

    enlaces = page.locator("a[href]")
    try:
        cantidad = min(enlaces.count(), 250)
    except Exception:
        cantidad = 0

    for indice in range(cantidad):
        enlace = enlaces.nth(indice)
        try:
            href = enlace.get_attribute("href") or ""
        except Exception:
            continue

        if not enlace_coincide_con_perfil(enlace, href, banco, perfil_url, definicion):
            continue

        try:
            print(f"Abriendo resultado de busqueda para {banco}: {href}")
            enlace.click(timeout=3000)
            page.wait_for_timeout(5000)
            return True
        except Exception:
            try:
                page.goto(normalizar_url_publicacion(href, perfil_url), wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                return True
            except Exception:
                continue

    print(f"No se encontro resultado de busqueda confiable para {banco}.")
    return False


def hrefs_desde_seccion_publicaciones(page, definicion):
    if definicion.get("nombre") != "facebook":
        enlaces = page.locator("a[href]")
        hrefs = []
        try:
            cantidad = min(enlaces.count(), 800)
        except Exception:
            return hrefs

        for indice in range(cantidad):
            try:
                href = enlaces.nth(indice).get_attribute("href") or ""
            except Exception:
                continue
            hrefs.append(href)

        return hrefs

    try:
        return page.evaluate(
            """
            () => {
                const visible = (element) => {
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const normalized = (value) => (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const headings = Array.from(document.querySelectorAll("h1, h2, h3, [role='heading']"));
                const headingPublicaciones = headings
                    .filter((element) => visible(element) && normalized(element.innerText || element.textContent) === "publicaciones")
                    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
                let marcador = headingPublicaciones[headingPublicaciones.length - 1];

                if (!marcador) {
                    const spans = Array.from(document.querySelectorAll("span"));
                    marcador = spans
                        .filter((element) => {
                            if (!visible(element)) return false;
                            if (normalized(element.innerText || element.textContent) !== "publicaciones") return false;
                            return Boolean(element.closest("h1, h2, h3, [role='heading']"));
                        })
                        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
                        .pop();
                }

                if (!marcador) {
                    return [];
                }

                const publicacionesTop = marcador.getBoundingClientRect().top - 8;
                const anchors = Array.from(document.querySelectorAll("a[href]"));
                return anchors
                    .filter((anchor) => visible(anchor) && anchor.getBoundingClientRect().top >= publicacionesTop)
                    .map((anchor) => anchor.href || anchor.getAttribute("href") || "")
                    .filter(Boolean);
            }
            """
        )
    except Exception:
        return []


def recolectar_urls_publicaciones(page, perfil_url, definicion, limite):
    urls = []
    vistos = set()
    intentos_sin_cambios = 0
    intentos_maximos = max(8, min(30, limite * 2))

    for _ in range(intentos_maximos):
        cantidad_previa = len(urls)
        hrefs = hrefs_desde_seccion_publicaciones(page, definicion)
        if definicion.get("nombre") == "facebook" and not hrefs:
            print("  Aun no se ve la seccion Publicaciones; bajando...")

        for href in hrefs:
            url = normalizar_url_publicacion(href, perfil_url)
            if (
                not url
                or url in vistos
                or not es_url_publicacion(url, definicion)
                or not url_pertenece_a_perfil(url, perfil_url, definicion)
            ):
                continue

            vistos.add(url)
            urls.append(url)
            print(f"  URL candidata: {url}")

            if len(urls) >= limite:
                return urls

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


def click_botones_comentarios_facebook(page, max_clicks=2):
    try:
        return page.evaluate(
            """
            (maxClicks) => {
                const visible = (element) => {
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const objetivoVisible = (marker) => {
                    const candidatos = [];
                    const clickeable = marker.closest("button, [role='button'], a");
                    if (clickeable) candidatos.push(clickeable);

                    let actual = marker;
                    for (let nivel = 0; nivel < 6 && actual; nivel += 1) {
                        candidatos.push(actual);
                        actual = actual.parentElement;
                    }

                    return candidatos.find((element) => visible(element)) || null;
                };
                const clickCentro = (element) => {
                    element.scrollIntoView({ block: "center", inline: "center" });
                    const rect = element.getBoundingClientRect();
                    if (!rect.width || !rect.height) return false;

                    const clientX = rect.left + rect.width / 2;
                    const clientY = rect.top + rect.height / 2;
                    const destino = document.elementFromPoint(clientX, clientY) || element;
                    const options = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX,
                        clientY
                    };

                    destino.dispatchEvent(new MouseEvent("mousedown", options));
                    destino.dispatchEvent(new MouseEvent("mouseup", options));
                    destino.dispatchEvent(new MouseEvent("click", options));
                    return true;
                };
                const candidatos = Array.from(document.querySelectorAll("[data-ad-rendering-role='comment_button']"));
                let clicks = 0;

                for (const candidato of candidatos) {
                    if (clicks >= maxClicks) break;

                    const objetivo = objetivoVisible(candidato);
                    if (!objetivo) continue;

                    if (clickCentro(objetivo)) {
                        clicks += 1;
                    }
                }

                return clicks;
            }
            """,
            max_clicks,
        )
    except Exception:
        return 0


def cargar_comentarios_visibles(page, max_comentarios):
    iteraciones = max(4, min(20, max_comentarios // 25 + 2))
    ciclos_sin_clicks = 0

    for _ in range(iteraciones):
        clicks = click_controles(page, PATRONES_CARGAR_COMENTARIOS, max_clicks=4)
        clicks_comentario = click_botones_comentarios_facebook(page, max_clicks=2)
        clicks += clicks_comentario
        if clicks_comentario:
            page.wait_for_timeout(1400)
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


def inferir_fecha_sin_anio(dia, mes, configuracion=None):
    inicio = (configuracion or {}).get("fecha_inicio")
    fin = (configuracion or {}).get("fecha_fin")

    if inicio and fin:
        for anio in range(inicio.year, fin.year + 1):
            try:
                fecha = datetime(anio, mes, dia).date()
            except ValueError:
                continue

            if inicio <= fecha <= fin:
                return fecha

        try:
            return datetime(inicio.year, mes, dia).date()
        except ValueError:
            return None

    try:
        return datetime(datetime.now().year, mes, dia).date()
    except ValueError:
        return None


def parsear_fecha_con_anio(valor):
    texto = proyecto.normalizar_texto_busqueda(valor)
    coincidencia = PATRON_FECHA_COMPLETA.search(texto)

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = MESES.get(coincidencia.group(2))
        anio = int(coincidencia.group(3))
    else:
        coincidencia = PATRON_FECHA_MES_PRIMERO.search(texto)
        if not coincidencia:
            return None

        mes = MESES.get(coincidencia.group(1))
        dia = int(coincidencia.group(2))
        anio = int(coincidencia.group(3))

    if not mes:
        return None

    try:
        return datetime(anio, mes, dia).date()
    except ValueError:
        return None


def parsear_fecha_sin_anio(valor, configuracion=None):
    texto = proyecto.normalizar_texto_busqueda(valor)
    coincidencia = PATRON_FECHA_SIN_ANIO.search(texto)

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = MESES.get(coincidencia.group(2))
    else:
        coincidencia = PATRON_FECHA_MES_PRIMERO_SIN_ANIO.search(texto)
        if not coincidencia:
            return None

        mes = MESES.get(coincidencia.group(1))
        dia = int(coincidencia.group(2))

    if not mes:
        return None

    return inferir_fecha_sin_anio(dia, mes, configuracion)


def parsear_fecha_texto(valor, configuracion=None):
    return (
        parsear_fecha_con_anio(valor)
        or parsear_fecha_sin_anio(valor, configuracion)
    )


def parsear_fecha_relativa(valor):
    texto = proyecto.normalizar_texto_busqueda(valor)
    hoy = datetime.now().date()

    if not texto:
        return None
    if re.search(r"\b(ahora|justo ahora|hoy)\b", texto):
        return hoy
    if re.search(r"\bayer\b", texto):
        return hoy - timedelta(days=1)

    patrones = [
        (r"\b(\d+)\s*(?:min|mins|minuto|minutos)\b", "minutos"),
        (r"\b(\d+)\s*(?:h|hr|hrs|hora|horas)\b", "horas"),
        (r"\b(\d+)\s*(?:d|dia|dias)\b", "dias"),
        (r"\b(\d+)\s*(?:sem|semana|semanas)\b", "semanas"),
        (r"\b(\d+)\s*(?:mes|meses)\b", "meses"),
        (r"\b(\d+)\s*(?:ano|anos|year|years)\b", "anos"),
    ]

    for patron, unidad in patrones:
        coincidencia = re.search(patron, texto)
        if not coincidencia:
            continue

        cantidad = int(coincidencia.group(1))
        if unidad in {"minutos", "horas"}:
            return hoy
        if unidad == "dias":
            return hoy - timedelta(days=cantidad)
        if unidad == "semanas":
            return hoy - timedelta(weeks=cantidad)
        if unidad == "meses":
            return hoy - timedelta(days=cantidad * 30)
        if unidad == "anos":
            return hoy - timedelta(days=cantidad * 365)

    return None


def parsear_fecha_visible(valor, configuracion=None):
    return (
        parsear_fecha_iso(valor)
        or parsear_fecha_texto(valor, configuracion)
        or parsear_fecha_relativa(valor)
    )


def textos_fecha_desde_dom(page):
    selectores = (
        "time, abbr, a[aria-label], span[aria-label], "
        "a[href*='/posts/'], a[href*='/reel/'], "
        "a[href*='/videos/'], a[href*='photo?fbid='], "
        "a[href*='story_fbid='], a[href*='permalink.php'], "
        "div[role='article'] a, div[role='article'] span"
    )

    try:
        return page.locator(selectores).evaluate_all(
            """
            (elements) => elements.slice(0, 180).map((element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                if (!rect.width || !rect.height || style.visibility === "hidden" || style.display === "none") {
                    return "";
                }
                const values = [
                    element.innerText,
                    element.textContent,
                    element.getAttribute("aria-label"),
                    element.getAttribute("title"),
                    element.getAttribute("datetime")
                ].filter(Boolean);
                return values.join("\\n").trim();
            }).filter(Boolean)
            """
        )
    except Exception:
        return []


def extraer_fecha_desde_texto_visible(page, configuracion=None):
    for texto in textos_fecha_desde_dom(page):
        fecha = parsear_fecha_iso(texto) or parsear_fecha_con_anio(texto)
        if fecha:
            return fecha, proyecto.limpiar_linea(texto)[:120]

    for selector in ("article", "div[role='article']", "main"):
        elementos = page.locator(selector)
        try:
            cantidad = min(elementos.count(), 3)
        except Exception:
            continue

        for indice in range(cantidad):
            try:
                texto = elementos.nth(indice).inner_text(timeout=1200)
            except Exception:
                continue

            fecha = parsear_fecha_con_anio(texto)
            if fecha:
                return fecha, proyecto.limpiar_linea(texto)[:120]

            lineas = [
                proyecto.limpiar_linea(linea)
                for linea in texto.splitlines()
                if proyecto.limpiar_linea(linea)
            ]

            for linea in lineas[:18]:
                fecha = parsear_fecha_iso(linea) or parsear_fecha_con_anio(linea)
                if fecha:
                    return fecha, linea

            for linea in lineas[:18]:
                fecha = parsear_fecha_sin_anio(linea, configuracion)
                if fecha:
                    return fecha, linea

            for linea in lineas[:18]:
                fecha = parsear_fecha_relativa(linea)
                if fecha:
                    return fecha, linea

            fecha = parsear_fecha_texto(texto, configuracion)
            if fecha:
                return fecha, proyecto.limpiar_linea(texto)[:120]

    return None, ""


def extraer_fecha_desde_textos(textos, configuracion=None):
    candidatos = [
        proyecto.limpiar_linea(texto)
        for texto in textos
        if proyecto.limpiar_linea(texto)
    ]

    for texto in candidatos:
        fecha = parsear_fecha_iso(texto) or parsear_fecha_con_anio(texto)
        if fecha:
            return fecha, texto[:120]

    for texto in candidatos:
        fecha = parsear_fecha_sin_anio(texto, configuracion)
        if fecha:
            return fecha, texto[:120]

    for texto in candidatos:
        fecha = parsear_fecha_relativa(texto)
        if fecha:
            return fecha, texto[:120]

    texto_unido = proyecto.limpiar_linea(" ".join(candidatos))
    fecha = parsear_fecha_texto(texto_unido, configuracion)
    if fecha:
        return fecha, texto_unido[:120]

    return None, ""


def extraer_fecha_publicacion(page, configuracion=None):
    selectores = [
        "time[datetime]",
        "abbr[data-utime]",
        "meta[property='article:published_time']",
    ]
    candidatos = []

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
                        candidatos.append(
                            (datetime.fromtimestamp(int(valor)).date(), valor, "timestamp")
                        )
                    except (TypeError, ValueError):
                        continue
                    continue

                candidatos.append((None, valor, "atributo"))

            try:
                texto = elemento.inner_text(timeout=700)
            except Exception:
                texto = ""

            if texto:
                candidatos.append((None, texto, "texto"))

    for fecha, valor, tipo in candidatos:
        if fecha and tipo == "timestamp":
            return fecha, valor

        fecha = parsear_fecha_iso(valor) or parsear_fecha_con_anio(valor)
        if fecha:
            return fecha, valor

    for _, valor, _ in candidatos:
        fecha = parsear_fecha_sin_anio(valor, configuracion)
        if fecha:
            return fecha, valor

    for _, valor, _ in candidatos:
        fecha = parsear_fecha_relativa(valor)
        if fecha:
            return fecha, valor

    return extraer_fecha_desde_texto_visible(page, configuracion)


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


def textos_visibles_por_selector(page, selector, limite):
    try:
        elementos = page.locator(selector)
        cantidad = min(elementos.count(), limite)
    except Exception:
        return []

    if cantidad <= 0:
        return []

    try:
        return elementos.evaluate_all(
            """
            (elements, limit) => elements.slice(0, limit).map((element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                if (!rect.width || !rect.height || style.visibility === "hidden" || style.display === "none") {
                    return "";
                }
                return (element.innerText || element.getAttribute("aria-label") || "").trim();
            }).filter(Boolean)
            """,
            cantidad,
        )
    except Exception:
        textos = []
        for indice in range(cantidad):
            try:
                textos.append(elementos.nth(indice).inner_text(timeout=350))
            except Exception:
                continue
        return textos


def extraer_comentarios_publicos(page, definicion, max_comentarios):
    comentarios = []
    vistos = set()
    limite_nodos = max(80, min(260, max_comentarios * 3))

    for selector in definicion.get("selectores_comentario", []):
        for texto in textos_visibles_por_selector(page, selector, limite_nodos):
            if len(comentarios) >= max_comentarios:
                return comentarios

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


def enfocar_inicio_publicacion(page):
    for accion in (
        lambda: page.keyboard.press("Home"),
        lambda: page.evaluate("window.scrollTo(0, 0)"),
    ):
        try:
            accion()
            page.wait_for_timeout(500)
            return True
        except Exception:
            continue

    return False


def capturar_pagina_publicacion(
    page,
    banco,
    contadores_seriales,
    fecha_archivo,
    comentarios_denuncia=None,
    tipo_resultado="publicaciones",
):
    serial = proyecto.siguiente_serial_banco(
        contadores_seriales,
        banco,
        tipo_resultado,
    )
    imagen_serial = f"{proyecto.normalizar_nombre_archivo(banco)}_{serial:04d}"
    carpeta = (
        proyecto.RUTA_CAPTURAS
        / tipo_resultado
        / proyecto.normalizar_nombre_archivo(banco)
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{fecha_archivo}_{imagen_serial}.png"

    try:
        if tipo_resultado == "descartadas":
            enfocar_inicio_publicacion(page)
        else:
            enfocar_comentario_relevante(page, comentarios_denuncia or [])
        page.screenshot(path=str(ruta), timeout=15000, animations="disabled")
    except Exception as exc:
        print(f"No se pudo capturar {tipo_resultado} {imagen_serial}: {exc}")
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
    page=None,
    contadores_seriales=None,
):
    fecha_iso = fecha_publicacion.isoformat() if fecha_publicacion else ""
    fecha_en_rango = "sin_fecha"
    serial = ""
    imagen_serial = ""
    ruta_imagen = ""
    nombre_imagen = ""

    if page is not None and contadores_seriales is not None:
        serial, imagen_serial, ruta_imagen, nombre_imagen = capturar_pagina_publicacion(
            page,
            banco,
            contadores_seriales,
            configuracion.get("fecha_ejecucion_archivo"),
            tipo_resultado="descartadas",
        )

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
        "imagen_serial": imagen_serial,
        "serial_por_banco": serial,
        "imagen_publicacion": ruta_imagen,
        "archivo_imagen": nombre_imagen,
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


def tarjetas_facebook_visibles(page, perfil_url, definicion, limite):
    try:
        candidatas = page.evaluate(
            """
            (limite) => {
                const visible = (element) => {
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const normalized = (value) => (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const postHref = (href) => {
                    const value = (href || "").toLowerCase();
                    return value.includes("/posts/")
                        || value.includes("/photos/")
                        || value.includes("/videos/")
                        || value.includes("/reel/")
                        || value.includes("/reels/")
                        || value.includes("photo?fbid=")
                        || value.includes("story_fbid=")
                        || value.includes("permalink.php");
                };
                const hasCommentSignal = (element) => {
                    if (element.querySelector("[data-ad-rendering-role='comment_button']")) return true;

                    const text = normalized(element.innerText || element.textContent);
                    if (/\\b\\d+\\s+comentarios?\\b|\\b\\d+\\s+comments?\\b|comentarios?|comments?/.test(text)) {
                        return true;
                    }

                    return Boolean(Array.from(element.querySelectorAll("i[data-visualcompletion='css-img']"))
                        .find((icon) => {
                            const style = icon.getAttribute("style") || "";
                            return style.includes("-231px") || style.includes("20px; height: 20px");
                        }));
                };
                const cardFromAnchor = (anchor) => {
                    const article = anchor.closest("div[role='article']");
                    if (article && visible(article)) return article;

                    const candidatos = [];
                    let actual = anchor.parentElement;
                    for (let nivel = 0; nivel < 14 && actual; nivel += 1) {
                        if (visible(actual)) {
                            const rect = actual.getBoundingClientRect();
                            const texto = normalized(actual.innerText || actual.textContent);
                            const enlacesPost = Array.from(actual.querySelectorAll("a[href]"))
                                .filter((link) => postHref(link.href || link.getAttribute("href") || ""))
                                .length;

                            if (
                                rect.width >= 280
                                && rect.height >= 120
                                && rect.height <= 2600
                                && enlacesPost >= 1
                                && texto.length >= 20
                            ) {
                                candidatos.push(actual);
                            }
                        }
                        actual = actual.parentElement;
                    }

                    candidatos.sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.width * ar.height) - (br.width * br.height);
                    });

                    return candidatos.find(hasCommentSignal) || candidatos[0] || null;
                };
                const findPublicacionesTop = () => {
                    const headings = Array.from(document.querySelectorAll("h1, h2, h3, [role='heading']"));
                    const byHeading = headings
                        .filter((element) => visible(element) && normalized(element.innerText || element.textContent) === "publicaciones")
                        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
                        .pop();
                    if (byHeading) return byHeading.getBoundingClientRect().top - 8;

                    const bySpan = Array.from(document.querySelectorAll("span"))
                        .filter((element) => {
                            if (!visible(element)) return false;
                            if (normalized(element.innerText || element.textContent) !== "publicaciones") return false;
                            return Boolean(element.closest("h1, h2, h3, [role='heading']"));
                        })
                        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
                        .pop();

                    return bySpan ? bySpan.getBoundingClientRect().top - 8 : null;
                };

                const publicacionesTop = findPublicacionesTop();
                const minTop = publicacionesTop === null
                    ? (location.pathname.includes("/posts") ? -100000 : null)
                    : publicacionesTop;
                if (minTop === null) return [];

                window.__codexFacebookPostSeq = window.__codexFacebookPostSeq || 0;
                const salida = [];
                const vistos = new Set();
                const anchors = Array.from(document.querySelectorAll("a[href]"));

                for (const anchor of anchors) {
                    if (salida.length >= limite) break;
                    if (!visible(anchor)) continue;

                    const href = anchor.href || anchor.getAttribute("href") || "";
                    if (!postHref(href)) continue;

                    const card = cardFromAnchor(anchor);
                    if (!card || !visible(card)) continue;

                    const rect = card.getBoundingClientRect();
                    if (rect.bottom < minTop || rect.height < 80) continue;

                    if (!card.dataset.codexPostCard) {
                        window.__codexFacebookPostSeq += 1;
                        card.dataset.codexPostCard = `fb-post-${window.__codexFacebookPostSeq}`;
                    }

                    const cardId = card.dataset.codexPostCard;
                    if (vistos.has(cardId)) continue;
                    vistos.add(cardId);

                    const dateNodes = Array.from(card.querySelectorAll(
                        "time, abbr, a[aria-label], span[aria-label], a[href], span, div[dir='auto']"
                    ));
                    const dateTexts = dateNodes.slice(0, 120).map((element) => {
                        const values = [
                            element.innerText,
                            element.textContent,
                            element.getAttribute("aria-label"),
                            element.getAttribute("title"),
                            element.getAttribute("datetime"),
                            element.getAttribute("href")
                        ].filter(Boolean);
                        return values.join("\\n").trim();
                    }).filter(Boolean);

                    salida.push({
                        card_id: cardId,
                        url: href,
                        tiene_comentarios: hasCommentSignal(card),
                        texto: (card.innerText || card.textContent || "").trim(),
                        date_texts: dateTexts
                    });
                }

                return salida;
            }
            """,
            limite,
        )
    except Exception as exc:
        print(f"  No se pudieron leer tarjetas visibles de Facebook: {exc}")
        return []

    tarjetas = []
    vistas = set()
    for item in candidatas:
        url = normalizar_url_publicacion(item.get("url", ""), perfil_url)
        if (
            not url
            or url in vistas
            or not es_url_publicacion(url, definicion)
            or not url_pertenece_a_perfil(url, perfil_url, definicion)
        ):
            continue

        vistas.add(url)
        tarjetas.append(
            {
                "card_id": item.get("card_id", ""),
                "url": url,
                "tiene_comentarios": bool(item.get("tiene_comentarios")),
                "texto": item.get("texto", ""),
                "date_texts": item.get("date_texts") or [],
            }
        )

    return tarjetas


def scroll_tarjeta_facebook(page, card_id):
    try:
        return page.evaluate(
            """
            (cardId) => {
                const card = document.querySelector(`[data-codex-post-card="${cardId}"]`);
                if (!card) return false;
                card.scrollIntoView({ block: "center", inline: "nearest" });
                return true;
            }
            """,
            card_id,
        )
    except Exception:
        return False


def expandir_texto_tarjeta_facebook(page, card_id):
    try:
        return page.evaluate(
            """
            (cardId) => {
                const card = document.querySelector(`[data-codex-post-card="${cardId}"]`);
                if (!card) return 0;

                const normalized = (value) => (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const controles = Array.from(card.querySelectorAll("button, [role='button'], a, span"));
                let clicks = 0;

                for (const control of controles) {
                    if (clicks >= 4) break;
                    const text = normalized(control.innerText || control.textContent || control.getAttribute("aria-label"));
                    if (!text) continue;
                    if (!/^(mas|más)$|ver\\s+mas|ver\\s+más|see\\s+more/.test(text)) continue;

                    control.click();
                    clicks += 1;
                }

                return clicks;
            }
            """,
            card_id,
        )
    except Exception:
        return 0


def click_comentarios_en_tarjeta_facebook(page, card_id, max_clicks=2):
    try:
        objetivos = page.evaluate(
            """
            ({ cardId, maxClicks }) => {
                const card = document.querySelector(`[data-codex-post-card="${cardId}"]`);
                if (!card) return [];
                card.scrollIntoView({ block: "center", inline: "nearest" });

                const visible = (element) => {
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const normalized = (value) => (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const rectInfo = (element, origen) => {
                    if (!element || !visible(element)) return null;
                    const rect = element.getBoundingClientRect();
                    if (!rect.width || !rect.height) return null;
                    return {
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                        width: rect.width,
                        height: rect.height,
                        area: rect.width * rect.height,
                        origen
                    };
                };
                const candidatosParaMarker = (marker) => {
                    const candidatos = [];
                    const clickeable = marker.closest("button, [role='button'], a");
                    if (clickeable) candidatos.push(clickeable);

                    const icono = marker.parentElement
                        ? marker.parentElement.querySelector("i[data-visualcompletion='css-img']")
                        : null;
                    if (icono) candidatos.push(icono);

                    let actual = marker;
                    for (let nivel = 0; nivel < 8 && actual; nivel += 1) {
                        candidatos.push(actual);
                        actual = actual.parentElement;
                    }

                    return candidatos
                        .map((element, index) => rectInfo(element, `marker-${index}`))
                        .filter(Boolean);
                };

                const markers = Array.from(card.querySelectorAll("[data-ad-rendering-role='comment_button']"));
                const iconosComentario = Array.from(card.querySelectorAll("i[data-visualcompletion='css-img']"))
                    .filter((icon) => {
                        const style = icon.getAttribute("style") || "";
                        return style.includes("-231px") || style.includes("20px; height: 20px");
                    });
                const contadoresComentario = iconosComentario.flatMap((icon) => {
                    const fila = icon.parentElement && icon.parentElement.parentElement
                        ? icon.parentElement.parentElement
                        : icon.parentElement;
                    if (!fila) return [];
                    return Array.from(fila.querySelectorAll("span, div"))
                        .filter((element) => /^\\d+$/.test(normalized(element.innerText || element.textContent)));
                });
                const controlesTexto = Array.from(card.querySelectorAll("button, [role='button'], a, span"))
                    .filter((element) => /comentarios?|comments?/.test(normalized(
                        element.innerText || element.textContent || element.getAttribute("aria-label")
                    )));
                const objetivos = [];

                for (const marker of markers) {
                    objetivos.push(...candidatosParaMarker(marker));
                }
                for (const icono of iconosComentario) {
                    objetivos.push(...candidatosParaMarker(icono));
                }
                for (const contador of contadoresComentario) {
                    objetivos.push(...candidatosParaMarker(contador));
                }

                for (const control of controlesTexto) {
                    const info = rectInfo(control, "texto-comentarios");
                    if (info) objetivos.push(info);
                }

                const unicos = [];
                const vistos = new Set();
                for (const objetivo of objetivos.sort((a, b) => a.area - b.area)) {
                    const clave = [
                        Math.round(objetivo.x),
                        Math.round(objetivo.y),
                        Math.round(objetivo.width),
                        Math.round(objetivo.height)
                    ].join(":");
                    if (vistos.has(clave)) continue;
                    vistos.add(clave);
                    unicos.push(objetivo);
                }

                return unicos.slice(0, Math.max(maxClicks * 3, 3));
            }
            """,
            {"cardId": card_id, "maxClicks": max_clicks},
        )
    except Exception:
        return 0

    objetivos = objetivos or []
    clicks = 0
    for objetivo in objetivos:
        if clicks >= max_clicks:
            break

        try:
            page.mouse.click(objetivo["x"], objetivo["y"])
            clicks += 1
            page.wait_for_timeout(1200)
        except Exception:
            continue

    return clicks


def cargar_comentarios_tarjeta_facebook(page, card_id, max_comentarios):
    iteraciones = max(3, min(12, max_comentarios // 25 + 2))
    clicks_total = 0
    sin_clicks = 0

    for _ in range(iteraciones):
        clicks = 0
        if not clicks_total:
            clicks = click_comentarios_en_tarjeta_facebook(page, card_id, max_clicks=1)
        clicks_total += clicks
        if clicks:
            sin_clicks = 0
            page.wait_for_timeout(1500)
        else:
            sin_clicks += 1

        page.mouse.wheel(0, 450)
        page.wait_for_timeout(800)

        if sin_clicks >= 3:
            break

    return clicks_total


def textos_comentarios_tarjeta_facebook(page, card_id, max_comentarios):
    try:
        return page.evaluate(
            """
            ({ cardId, maxComentarios }) => {
                const card = document.querySelector(`[data-codex-post-card="${cardId}"]`);
                if (!card) return [];

                const visible = (element) => {
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const normalized = (value) => (value || "").replace(/\\s+/g, " ").trim().toLowerCase();
                const orden = Array.from(card.querySelectorAll("button, [role='button'], span, div"))
                    .filter((element) => {
                        if (!visible(element)) return false;
                        const text = normalized(element.innerText || element.textContent || element.getAttribute("aria-label"));
                        return text === "mas pertinentes"
                            || text === "más pertinentes"
                            || text === "most relevant"
                            || text === "todos los comentarios"
                            || text === "all comments";
                    })
                    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
                    .pop();
                const marcadorComentarios = Array.from(card.querySelectorAll("[data-ad-rendering-role='comment_button']"))
                    .filter(visible)
                    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
                    .pop();
                const iconoComentarios = Array.from(card.querySelectorAll("i[data-visualcompletion='css-img']"))
                    .filter((icon) => {
                        if (!visible(icon)) return false;
                        const style = icon.getAttribute("style") || "";
                        return style.includes("-231px") || style.includes("20px; height: 20px");
                    })
                    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
                    .pop();
                const minTop = orden
                    ? orden.getBoundingClientRect().bottom
                    : marcadorComentarios
                        ? marcadorComentarios.getBoundingClientRect().bottom
                        : iconoComentarios
                            ? iconoComentarios.getBoundingClientRect().bottom
                            : card.getBoundingClientRect().top;
                const elementos = Array.from(card.querySelectorAll(
                    "div[dir='auto'], span[dir='auto'], [aria-label*='comentario' i], [aria-label*='comment' i], [aria-label*='respuesta' i], [aria-label*='reply' i]"
                ));
                const textos = [];
                const vistos = new Set();

                for (const element of elementos) {
                    if (textos.length >= maxComentarios * 3) break;
                    if (!visible(element)) continue;

                    const rect = element.getBoundingClientRect();
                    if (rect.top < minTop - 2) continue;

                    const text = (element.innerText || element.textContent || element.getAttribute("aria-label") || "").trim();
                    const limpio = text.replace(/\\s+/g, " ").trim();
                    if (!limpio || vistos.has(limpio)) continue;

                    vistos.add(limpio);
                    textos.push(limpio);
                }

                return textos;
            }
            """,
            {"cardId": card_id, "maxComentarios": max_comentarios},
        )
    except Exception:
        return []


def extraer_comentarios_tarjeta_facebook(page, card_id, max_comentarios):
    comentarios = []
    vistos = set()

    for texto in textos_comentarios_tarjeta_facebook(page, card_id, max_comentarios):
        if len(comentarios) >= max_comentarios:
            return comentarios

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


def registrar_publicacion_revisada(
    page,
    banco,
    perfil_url,
    post_url,
    fecha_publicacion,
    fecha_visible,
    comentarios,
    configuracion,
    definicion,
    contadores_seriales,
    publicaciones,
    descartadas,
):
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
        return

    if not configuracion["guardar_descartadas"]:
        return

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


def ejecutar_perfil_facebook_en_feed(
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
    urls_vistas = set()
    antiguas_consecutivas = 0
    intentos_sin_nuevas = 0
    intentos_maximos = max(8, min(35, max_publicaciones * 2))

    print(f"[{indice}/{total}] Revisando perfil Facebook desde Publicaciones: {banco}")
    page.goto(perfil_url, wait_until="domcontentloaded", timeout=60000)
    proyecto.hacer_visible_ventana_chromium(page)
    page.wait_for_timeout(5000)
    abrir_seccion_publicaciones(page, perfil_url, definicion)

    for _ in range(intentos_maximos):
        nuevas = 0
        tarjetas = tarjetas_facebook_visibles(
            page,
            perfil_url,
            definicion,
            max_publicaciones,
        )

        if not tarjetas:
            print("  Aun no se ven tarjetas de Publicaciones con comentarios; bajando...")

        for tarjeta in tarjetas:
            if len(urls_vistas) >= max_publicaciones:
                break

            post_url = tarjeta["url"]
            if post_url in urls_vistas:
                continue

            urls_vistas.add(post_url)
            nuevas += 1
            post_indice = len(urls_vistas)
            card_id = tarjeta["card_id"]

            print(f"  Publicacion {post_indice}/{max_publicaciones}: {post_url}")
            if not tarjeta.get("tiene_comentarios"):
                print("    Tarjeta detectada sin indicador visible de comentarios.")
            scroll_tarjeta_facebook(page, card_id)
            page.wait_for_timeout(700)
            expandir_texto_tarjeta_facebook(page, card_id)

            fecha_publicacion, fecha_visible = extraer_fecha_desde_textos(
                tarjeta["date_texts"] + [tarjeta["texto"]],
                configuracion,
            )
            if fecha_publicacion:
                print(f"    Fecha detectada en tarjeta: {fecha_publicacion} ({fecha_visible})")
            else:
                print("    Fecha no detectada en tarjeta.")

            if configuracion["filtrar_por_fecha"] and not fecha_publicacion:
                if configuracion["guardar_descartadas"]:
                    descartadas.append(
                        registro_descartado(
                            banco,
                            perfil_url,
                            post_url,
                            fecha_publicacion,
                            fecha_visible,
                            configuracion,
                            0,
                            "No se pudo extraer la fecha de la publicacion en la tarjeta",
                            tipo_contenido="sin_fecha",
                        )
                    )
                print("    Descartada porque no se pudo detectar la fecha.")
                continue

            if (
                configuracion["filtrar_por_fecha"]
                and fecha_publicacion
                and fecha_publicacion < configuracion["fecha_inicio"]
            ):
                antiguas_consecutivas += 1
                if configuracion["guardar_descartadas"]:
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
                print("    Descartada por fecha anterior al rango.")
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
                if configuracion["guardar_descartadas"]:
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
                print("    Descartada por fecha fuera del rango.")
                continue

            clicks = cargar_comentarios_tarjeta_facebook(
                page,
                card_id,
                max_comentarios,
            )
            print(f"    Clicks en comentarios de la tarjeta: {clicks}")

            comentarios = extraer_comentarios_tarjeta_facebook(
                page,
                card_id,
                max_comentarios,
            )
            print(f"    Comentarios revisados en tarjeta: {len(comentarios)}")

            registrar_publicacion_revisada(
                page,
                banco,
                perfil_url,
                post_url,
                fecha_publicacion,
                fecha_visible,
                comentarios,
                configuracion,
                definicion,
                contadores_seriales,
                publicaciones,
                descartadas,
            )

        if len(urls_vistas) >= max_publicaciones or antiguas_consecutivas >= 3:
            break

        if nuevas:
            intentos_sin_nuevas = 0
        else:
            intentos_sin_nuevas += 1

        if intentos_sin_nuevas >= 5:
            break

        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(2200)

    print(f"Publicaciones encontradas para revisar en {banco}: {len(urls_vistas)}")
    if not urls_vistas:
        guardar_diagnostico_perfil(page, banco, definicion)

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


def procesar_publicacion_perfil(
    page,
    banco,
    perfil_url,
    post_url,
    configuracion,
    definicion,
    contadores_seriales,
    publicaciones,
    descartadas,
    post_indice,
    total_estimado,
):
    max_comentarios = configuracion["max_comentarios_por_publicacion"]

    print(f"  Publicacion {post_indice}/{total_estimado}")
    page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
    proyecto.hacer_visible_ventana_chromium(page)
    page.wait_for_timeout(3500)
    expandir_texto_visible(page)

    fecha_publicacion, fecha_visible = extraer_fecha_publicacion(page, configuracion)
    if fecha_publicacion:
        print(f"    Fecha detectada: {fecha_publicacion} ({fecha_visible})")
    else:
        print("    Fecha no detectada.")

    if configuracion["filtrar_por_fecha"] and not fecha_publicacion:
        if configuracion["guardar_descartadas"]:
            descartadas.append(
                registro_descartado(
                    banco,
                    perfil_url,
                    post_url,
                    fecha_publicacion,
                    fecha_visible,
                    configuracion,
                    0,
                    "No se pudo extraer la fecha de la publicacion",
                    tipo_contenido="sin_fecha",
                    page=page,
                    contadores_seriales=contadores_seriales,
                )
            )
        print("    Descartada porque no se pudo detectar la fecha.")
        return "sin_fecha"

    if (
        configuracion["filtrar_por_fecha"]
        and fecha_publicacion
        and fecha_publicacion < configuracion["fecha_inicio"]
    ):
        if configuracion["guardar_descartadas"]:
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
                    page=page,
                    contadores_seriales=contadores_seriales,
                )
            )
        print("    Descartada por fecha anterior al rango.")
        return "antigua"

    if (
        configuracion["filtrar_por_fecha"]
        and fecha_publicacion
        and fecha_fuera_de_rango(fecha_publicacion, configuracion)
    ):
        if configuracion["guardar_descartadas"]:
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
                    page=page,
                    contadores_seriales=contadores_seriales,
                )
            )
        print("    Descartada por fecha fuera del rango.")
        return "fuera_rango"

    cargar_comentarios_visibles(page, max_comentarios)

    comentarios = extraer_comentarios_publicos(
        page,
        definicion,
        max_comentarios,
    )
    print(f"    Comentarios revisados: {len(comentarios)}")
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
        return "procesada"

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
                page=page,
                contadores_seriales=contadores_seriales,
            )
        )

    return "procesada"


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
    if definicion.get("nombre") == "facebook":
        return ejecutar_perfil_facebook_en_feed(
            page,
            banco,
            perfil_url,
            configuracion,
            definicion,
            indice,
            total,
            contadores_seriales,
        )

    publicaciones = []
    descartadas = []
    max_publicaciones = configuracion["max_publicaciones_por_banco"]
    inicio_perf = time.perf_counter()
    inicio = datetime.now()

    print(f"[{indice}/{total}] Revisando perfil {definicion['nombre_visible']}: {banco}")
    page.goto(perfil_url, wait_until="domcontentloaded", timeout=60000)
    proyecto.hacer_visible_ventana_chromium(page)
    page.wait_for_timeout(5000)
    abrir_seccion_publicaciones(page, perfil_url, definicion)
    if configuracion["filtrar_por_fecha"]:
        print(
            "  Corte temprano por fecha activo: se detiene tras "
            "3 publicaciones anteriores al rango."
        )

    urls_vistas = set()
    antiguas_consecutivas = 0
    intentos_sin_nuevas = 0
    intentos_maximos = max(8, min(35, max_publicaciones * 2))
    post_page = page.context.new_page()

    try:
        for _ in range(intentos_maximos):
            nuevas = 0
            hrefs = hrefs_desde_seccion_publicaciones(page, definicion)

            if not hrefs:
                print("  Aun no se ven publicaciones; bajando...")

            for href in hrefs:
                if len(urls_vistas) >= max_publicaciones:
                    break

                post_url = normalizar_url_publicacion(href, perfil_url)
                if (
                    not post_url
                    or post_url in urls_vistas
                    or not es_url_publicacion(post_url, definicion)
                    or not url_pertenece_a_perfil(post_url, perfil_url, definicion)
                ):
                    continue

                urls_vistas.add(post_url)
                nuevas += 1
                print(f"  URL candidata: {post_url}")
                estado = procesar_publicacion_perfil(
                    post_page,
                    banco,
                    perfil_url,
                    post_url,
                    configuracion,
                    definicion,
                    contadores_seriales,
                    publicaciones,
                    descartadas,
                    len(urls_vistas),
                    max_publicaciones,
                )

                if estado == "antigua":
                    antiguas_consecutivas += 1
                    if antiguas_consecutivas >= 3:
                        print("  Se encontraron varias publicaciones antiguas; se detiene este perfil.")
                        break
                    continue

                if estado != "sin_fecha":
                    antiguas_consecutivas = 0

            if len(urls_vistas) >= max_publicaciones or antiguas_consecutivas >= 3:
                break

            if nuevas:
                intentos_sin_nuevas = 0
            else:
                intentos_sin_nuevas += 1

            if intentos_sin_nuevas >= 4:
                break

            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(2200)
    finally:
        try:
            post_page.close()
        except Exception:
            pass

    print(f"Publicaciones encontradas para revisar en {banco}: {len(urls_vistas)}")
    if not urls_vistas:
        guardar_diagnostico_perfil(page, banco, definicion)

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


def cerrar_contexto_seguro(context):
    try:
        context.close()
    except Exception as exc:
        print(f"No se pudo cerrar el navegador automaticamente: {exc}")


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
            cerrar_contexto_seguro(context)

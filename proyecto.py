"""
Bot de recoleccion y analisis de publicaciones de LinkedIn.

Este archivo contiene la automatizacion principal del proyecto. Normalmente no
se ejecuta manualmente; lo lanza interfaz.py cuando el usuario presiona
"Ejecutar proyecto" en el dashboard. Aun asi, tambien puede ejecutarse desde
Visual Studio Code o terminal con:

    .venv/bin/python proyecto.py

Responsabilidad de este archivo
-------------------------------
1. Lee credenciales desde .env.
2. Lee parametros desde configuracion_busqueda.json.
3. Abre LinkedIn con Playwright/Chromium.
4. Inicia sesion con las credenciales locales.
5. Espera intervencion manual si LinkedIn pide codigo, captcha o verificacion.
6. Construye busquedas por cada banco seleccionado y cada termino:
   - fraude;
   - estafa;
   - denuncia.
7. Extrae publicaciones visibles, metricas, fechas aproximadas y URL.
8. Evalua si cada publicacion es relevante o descartada.
9. Guarda CSV de publicaciones, descartadas, conteos, comparativo y tiempos.
10. Genera un Excel consolidado con hojas y graficas.
11. Guarda capturas de publicaciones para auditoria visual.

Flujo normal de ejecucion
-------------------------
1. cargar_configuracion() lee configuracion_busqueda.json.
2. preparar_rutas_ejecucion() crea una carpeta resultados/ejecucion_...
3. cargar_credenciales() lee .env.
4. main() abre LinkedIn y hace login.
5. El usuario completa cualquier verificacion manual.
6. ejecutar_busquedas_linkedin() recorre las busquedas seleccionadas.
7. extraer_publicaciones_visibles() clasifica publicaciones relevantes y
   descartadas.
8. guardar_resultados() escribe los archivos finales.

Para que sirve configuracion_busqueda.json
------------------------------------------
Este JSON es el puente entre la interfaz y el bot. La interfaz lo modifica y
este script lo consume al iniciar. Sus campos controlan:

- fecha_inicio / fecha_fin: periodo usado para incluir o descartar posts.
- max_publicaciones_por_busqueda: limite por cada busqueda individual.
- max_publicaciones_por_banco: limite de posts de perfil para Instagram/Facebook.
- max_comentarios_por_publicacion: limite de comentarios publicos por post.
- filtrar_por_fecha: si esta activo, descarta publicaciones fuera del rango.
- filtrar_por_relevancia: si esta activo, aplica reglas de fraude/denuncia.
- guardar_descartadas: permite auditar que se excluyo y por que.
- bancos_seleccionados: reduce el numero de bancos buscados para acelerar la
  ejecucion.

Mapa general del archivo
------------------------
- Rutas y constantes: ubicacion de .env, JSON, resultados y bancos.
- CRITERIOS_RELEVANCIA: vocabulario y reglas para clasificar publicaciones.
- Configuracion y fechas: normaliza JSON y estima fechas relativas de LinkedIn.
- Relevancia: decide si una publicacion habla de fraude bancario real.
- Automatizacion web: navega LinkedIn, hace scroll y extrae datos visibles.
- Capturas: guarda imagenes de publicaciones relevantes/descartadas.
- Persistencia: escribe CSV, XLSX y graficas.
- Orquestacion: ejecuta busquedas, mide tiempos y controla el navegador.

Inventario de funciones principales
-----------------------------------
- construir_busqueda_banco()/construir_busquedas_linkedin(): generan consultas
  banco + termino.
- leer_archivo_env()/cargar_credenciales(): leen usuario y contrasena desde
  .env sin imprimir secretos.
- cargar_configuracion()/normalizar_configuracion(): leen y validan el JSON.
- normalizar_bancos_seleccionados(): asegura que solo se usen bancos validos.
- restar_meses()/estimar_fecha_publicacion()/esta_en_rango(): convierten fechas
  relativas de LinkedIn a fechas aproximadas y aplican el rango configurado.
- normalizar_texto_busqueda()/buscar_terminos()/combinar_terminos(): preparan
  texto para aplicar reglas de relevancia.
- evaluar_relevancia_publicacion(): decide si una publicacion es denuncia
  directa, descartada, educativa, comercial o noticia/reporte.
- construir_url_busqueda(): arma URL de busqueda de LinkedIn.
- preparar_rutas_ejecucion(): crea carpeta resultados/ejecucion_* y actualiza
  rutas globales de salida.
- expandir_publicacion()/cargar_mas_resultados(): interactuan con la pagina para
  ver mas contenido.
- ajustar_viewport_para_publicacion()/capturar_imagen_publicacion(): preparan y
  guardan capturas.
- extraer_metricas()/calcular_interacciones_total(): leen reacciones,
  comentarios y compartidos.
- extraer_datos_item_publicacion(): obtiene texto, autor, metricas, fecha y URL
  desde un contenedor visible.
- extraer_publicaciones_visibles(): recorre posts, filtra, captura y separa
  publicaciones relevantes de descartadas.
- deduplicar_publicaciones(): evita repetir el mismo post.
- contar_publicaciones_por_banco(): calcula conteo por banco.
- campos_resultados()/campos_publicaciones()/campos_tiempos_ejecucion(): definen
  columnas estables de los CSV.
- escribir_csv(): escribe archivos CSV con encabezados consistentes.
- crear_reporte_excel() y auxiliares XML: construyen reporte_bancos.xlsx sin
  depender de pandas/openpyxl.
- guardar_comparativo_banco_popular(): calcula participacion, diferencias,
  multiplo, interacciones y ranking.
- guardar_resultados(): escribe todos los archivos finales.
- ejecutar_busquedas_linkedin(): orquesta las busquedas y mide tiempos.
- escribir_texto_como_humano()/llenar_input_visible()/click_boton_iniciar_sesion():
  automatizan el login inicial.
- main(): flujo completo del bot con Playwright usando un perfil persistente de
  Chromium en .perfil_chromium_linkedin.
"""

import csv
import json
import random
import re
import time
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ----------------------------------------------
# Ruta del archivo local de credenciales
# ----------------------------------------------
RUTA_CREDENCIALES = Path(__file__).with_name(".env")
RUTA_CONFIGURACION = Path(__file__).with_name("configuracion_busqueda.json")
RUTA_RESULTADOS = Path(__file__).with_name("resultados")
RUTA_PUBLICACIONES = RUTA_RESULTADOS / "publicaciones_linkedin.csv"
RUTA_DESCARTADAS = RUTA_RESULTADOS / "publicaciones_descartadas.csv"
RUTA_CONTEO_BANCOS = RUTA_RESULTADOS / "conteo_por_banco.csv"
RUTA_COMPARATIVO_POPULAR = RUTA_RESULTADOS / "comparativo_banco_popular.csv"
RUTA_TIEMPOS_EJECUCION = RUTA_RESULTADOS / "tiempos_ejecucion.csv"
RUTA_REPORTE_EXCEL = RUTA_RESULTADOS / "reporte_bancos.xlsx"
RUTA_CAPTURAS = RUTA_RESULTADOS / "capturas_publicaciones"
RUTA_EJECUCION = RUTA_RESULTADOS
RUTA_PERFIL_CHROMIUM = Path(__file__).with_name(".perfil_chromium_linkedin")
TIMEOUT_NAVEGACION_LINKEDIN_MS = 90000
INTENTOS_NAVEGACION_LINKEDIN = 2

BANCOS_OBJETIVO = [
    "Banco Popular Colombia",
    "Banco Davivienda",
    "Bancolombia",
    "Banco de Bogotá",
    "BBVA Colombia",
    "Banco Agrario de Colombia",
    "Scotiabank Colpatria",
    "Banco de Occidente",
    "Banco AV Villas",
    "Banco Caja Social",
]

CONFIGURACION_DEFAULT = {
    "plataforma": "linkedin",
    "fecha_inicio": "2026-05-01",
    "fecha_fin": "2026-05-31",
    "max_publicaciones_por_busqueda": 20,
    "max_publicaciones_por_banco": 50,
    "max_comentarios_por_publicacion": 200,
    "leer_respuestas_comentarios": False,
    "filtrar_por_fecha": True,
    "filtrar_por_relevancia": True,
    "guardar_descartadas": True,
    "bancos_seleccionados": BANCOS_OBJETIVO.copy(),
}

CRITERIOS_RELEVANCIA = {
    # Alias aceptados para confirmar que la publicación habla del banco objetivo.
    # No dependemos solo de la búsqueda de LinkedIn porque LinkedIn puede devolver
    # resultados relacionados pero no necesariamente centrados en el banco buscado.
    "aliases_bancos": {
        "Banco Popular Colombia": [
            "Banco Popular",
            "Banco Popular Colombia",
            "BancoPopular",
            "BancoPopularColombia",
        ],
        "Banco Davivienda": [
            "Banco Davivienda",
            "Davivienda",
        ],
        "Bancolombia": [
            "Bancolombia",
            "Bancolombia S.A.",
        ],
        "Banco de Bogotá": [
            "Banco de Bogota",
            "Banco de Bogotá",
            "BancodeBogota",
            "BancodeBogotá",
        ],
        "BBVA Colombia": [
            "BBVA Colombia",
            "BBVA",
            "Banco BBVA",
        ],
        "Banco Agrario de Colombia": [
            "Banco Agrario de Colombia",
            "Banco Agrario",
        ],
        "Scotiabank Colpatria": [
            "Scotiabank Colpatria",
            "Scotia Bank Colpatria",
            "Banco Colpatria",
            "Colpatria",
        ],
        "Banco de Occidente": [
            "Banco de Occidente",
            "Banco del Occidente",
            "Banco Occidente",
        ],
        "Banco AV Villas": [
            "Banco AV Villas",
            "AV Villas",
            "AVVillas",
        ],
        "Banco Caja Social": [
            "Banco Caja Social",
            "Caja Social",
        ],
    },
    # Vocabulario amplio: si aparece alguno, la publicación puede tratar de fraude.
    # Esta lista por sí sola no basta para incluir un resultado; se cruza con banco,
    # contexto bancario y contexto de denuncia.
    "terminos_fraude": [
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
        "correo sospechoso",
        "correos sospechosos",
        "aparentan provenir",
        "transaccion no reconocida",
        "transaccion no autorizada",
        "movimiento no reconocido",
        "movimiento no autorizado",
        "no reconocido",
        "no reconocida",
        "sin autorizacion",
        "sin mi autorizacion",
        "sin su autorizacion",
        "no autorice",
        "no solicite",
        "clave principal",
        "clave dinamica",
        "codigo de seguridad",
        "codigos de seguridad",
        "credito a tu nombre",
        "credito no solicitado",
        "credito nunca fue solicitado",
        "sacaron un credito",
        "a tu nombre",
        "me sacaron",
        "sacaron dinero",
        "perdi dinero",
        "me quitaron",
        "clonaron",
        "hackearon",
        "hurtaron",
        "hurto",
        "productos fraudulentos",
        "denuncia",
        "denunciar",
        "delito",
        "victima",
        "victimas",
    ],
    # Señales de mayor peso. Normalmente describen una modalidad concreta o una
    # denuncia directa, por eso elevan la relevancia.
    "terminos_fraude_fuertes": [
        "me estafaron",
        "estafaron",
        "me robaron",
        "robaron",
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
        "correo sospechoso",
        "correos sospechosos",
        "aparentan provenir",
        "transaccion no reconocida",
        "transaccion no autorizada",
        "movimiento no reconocido",
        "movimiento no autorizado",
        "no reconocido",
        "no reconocida",
        "sin autorizacion",
        "sin mi autorizacion",
        "sin su autorizacion",
        "no autorice",
        "no solicite",
        "credito a tu nombre",
        "credito no solicitado",
        "credito nunca fue solicitado",
        "sacaron un credito",
        "a tu nombre",
        "me sacaron",
        "sacaron dinero",
        "perdi dinero",
        "me quitaron",
        "clonaron",
        "hackearon",
        "hurtaron",
        "hurto",
        "productos fraudulentos",
        "denuncia",
        "denunciar",
        "delito",
        "victima",
        "victimas",
    ],
    # Señales de caso real o denuncia. Ayudan a diferenciar una publicación
    # genérica sobre "riesgo de fraude" de una denuncia o experiencia concreta.
    "terminos_contexto_denuncia": [
        "denuncia publica",
        "quiero denunciar",
        "quiero reportar",
        "quiero dejar constancia",
        "dejo constancia",
        "hago publica",
        "hago publico",
        "fui victima",
        "fue victima",
        "fuimos victimas",
        "me estafaron",
        "nos estafaron",
        "me robaron",
        "le robaron",
        "me hurtaron",
        "hurto de mis",
        "me vaciaron",
        "me debitaron",
        "debitaron ilegalmente",
        "me hicieron phishing",
        "le hicieron phishing",
        "mi cuenta",
        "mi dinero",
        "mi patrimonio",
        "mi nombre",
        "mi documento",
        "mis documentos",
        "mis tarjetas",
        "mi tarjeta",
        "mi mama",
        "mi madre",
        "mi esposo",
        "mi familia",
        "su cuenta",
        "sin mi autorizacion",
        "sin su autorizacion",
        "sin autorizacion",
        "no autorice",
        "nunca autorice",
        "no solicite",
        "nunca solicite",
        "no fue solicitado",
        "nunca fue solicitado",
        "credito nunca fue solicitado",
        "credito no solicitado",
        "transaccion no reconocida",
        "movimiento no reconocido",
        "productos fraudulentos",
        "falta de respuesta",
        "no responden",
        "no me responden",
        "no he recibido respuesta",
        "respuesta desfavorable",
        "respuesta negativa",
        "interponer queja",
        "interpuse una queja",
        "radicado",
        "derecho de peticion",
        "fiscalia",
        "superintendencia",
        "policia",
        "exijo respuesta",
        "solicito respuesta",
        "recuperar el dinero",
        "reincorporado",
        "soportes",
        "comprobantes",
        "tomaron el caso",
    ],
    # Contexto operativo bancario. Sirve para descartar ruido de industria,
    # compliance, corrupción o marketing que menciona "fraude" sin hablar de una
    # cuenta, tarjeta, transferencia, QR, saldo, crédito, etc.
    "terminos_contexto_bancario": [
        "cuenta",
        "cuentas",
        "mi cuenta",
        "transaccion",
        "transacciones",
        "transferencia",
        "transferencias",
        "movimiento",
        "movimientos",
        "saldo",
        "saldos",
        "retiro",
        "retiros",
        "debito",
        "debitaron",
        "pago",
        "pagos",
        "pse",
        "qr",
        "tarjeta",
        "tarjetas",
        "cvv",
        "credito",
        "creditos",
        "prestamo",
        "prestamos",
        "clave principal",
        "clave dinamica",
        "clave de la app",
        "codigo",
        "codigos",
        "app",
        "aplicacion",
        "billetera",
        "billeteras",
        "cajero",
        "cajeros",
        "corresponsal",
        "corresponsales",
        "cliente",
        "clientes",
        "usuario",
        "usuarios",
        "dinero",
        "plata",
    ],
    # Ruido comercial frecuente en resultados. Solo descarta cuando no hay señales
    # reales de denuncia directa.
    "terminos_comerciales": [
        "abogados",
        "consultores",
        "servicios legales",
        "asesoria legal",
        "asesoría legal",
        "agenda tu consulta",
        "contactanos",
        "contáctanos",
        "nuestros clientes",
        "reintegrar los fondos de nuestros clientes",
        "obligamos a las entidades",
        "recupera tu dinero",
        "vitaminas",
        "minerales",
        "cosmetica",
        "belleza",
        "dia de la madre",
        "madresita",
        "promocion",
        "oferta",
        "vendo",
        "venta",
        "regalo perfecto",
        "llamame",
    ],
    "terminos_educativos_preventivos": [
        "podcast",
        "webinar",
        "episodio",
        "a prueba de fraude",
        "youtube",
        "spotify",
        "tips",
        "consejos",
        "prevencion",
        "prevención",
        "prevenir",
        "campaña",
        "capacitacion",
        "capacitación",
        "curso",
        "evento",
        "entrevista",
        "estreno",
        "no te lo pierdas",
        "conversemos",
        "modalidades de fraude",
        "como proteger",
        "cómo proteger",
        "seguridad digital",
        "ciberseguridad",
        "dataengineering",
        "banca digital",
    ],
    "terminos_noticia_reporte": [
        "hemos identificado",
        "informe",
        "boletin",
        "boletín",
        "comunicado",
        "noticia",
        "reporte",
        "estudio",
        "segun el reporte",
        "según el reporte",
    ],
}

CONSULTAS_BUSQUEDA = [
    {
        "etiqueta": "fraude",
        "terminos": ["fraude"],
    },
    {
        "etiqueta": "estafa",
        "terminos": ["estafa"],
    },
    {
        "etiqueta": "denuncia",
        "terminos": ["denuncia"],
    },
]


def construir_busqueda_banco(banco, terminos):
    return f"{' '.join(terminos)} {banco}"


def construir_busquedas_linkedin(bancos):
    return [
        {
            "banco": banco,
            "etiqueta": consulta["etiqueta"],
            "busqueda": construir_busqueda_banco(banco, consulta["terminos"]),
        }
        for banco in bancos
        for consulta in CONSULTAS_BUSQUEDA
    ]


# ----------------------------------------------
# Función para cargar credenciales
# ----------------------------------------------
def leer_archivo_env(ruta_env):
    """
    Lee un archivo .env simple con lineas CLAVE=VALOR.
    """

    if not ruta_env.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de credenciales: {ruta_env}"
        )

    datos = {}

    with ruta_env.open("r", encoding="utf-8") as archivo:
        for numero_linea, linea in enumerate(archivo, start=1):
            linea = linea.strip()

            if not linea or linea.startswith("#"):
                continue

            if "=" not in linea:
                raise ValueError(
                    f"Línea inválida en {ruta_env}, línea {numero_linea}: falta '='"
                )

            clave, valor = linea.split("=", 1)
            clave = clave.strip()
            valor = valor.strip()

            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {"'", '"'}:
                valor = valor[1:-1]

            datos[clave] = valor

    return datos


def cargar_credenciales(ruta_env=RUTA_CREDENCIALES):
    """
    Lee las credenciales de LinkedIn desde un archivo .env local.
    Variables requeridas:
    LINKEDIN_USUARIO
    LINKEDIN_CONTRASENA
    """

    datos = leer_archivo_env(ruta_env)

    usuario = datos.get("LINKEDIN_USUARIO", "").strip()
    contrasena = datos.get("LINKEDIN_CONTRASENA", "").strip()

    if not usuario or not contrasena:
        raise ValueError(
            "El archivo .env debe tener LINKEDIN_USUARIO y LINKEDIN_CONTRASENA."
        )

    return usuario, contrasena


# ----------------------------------------------
# Funciones de configuración y fechas
# ----------------------------------------------
def cargar_configuracion(ruta_configuracion=RUTA_CONFIGURACION):
    if not ruta_configuracion.exists():
        return normalizar_configuracion(CONFIGURACION_DEFAULT)

    with ruta_configuracion.open("r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    configuracion = CONFIGURACION_DEFAULT.copy()
    configuracion.update(datos)

    return normalizar_configuracion(configuracion)


def normalizar_bancos_seleccionados(bancos_raw):
    if isinstance(bancos_raw, str):
        bancos_raw = [bancos_raw]
    if not isinstance(bancos_raw, list):
        raise ValueError("bancos_seleccionados debe ser una lista.")

    bancos_seleccionados = []
    for banco in bancos_raw:
        banco = str(banco).strip()
        if banco in BANCOS_OBJETIVO and banco not in bancos_seleccionados:
            bancos_seleccionados.append(banco)

    if not bancos_seleccionados:
        raise ValueError("Debe seleccionarse al menos un banco válido.")

    return bancos_seleccionados


def normalizar_configuracion(configuracion):
    plataforma = str(configuracion.get("plataforma", "linkedin")).strip().lower()
    fecha_inicio = date.fromisoformat(configuracion["fecha_inicio"])
    fecha_fin = date.fromisoformat(configuracion["fecha_fin"])

    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio no puede ser mayor que fecha_fin.")

    max_publicaciones = int(configuracion["max_publicaciones_por_busqueda"])
    max_publicaciones_banco = int(
        configuracion.get("max_publicaciones_por_banco", 50)
    )
    max_comentarios = int(
        configuracion.get("max_comentarios_por_publicacion", 200)
    )

    if max_publicaciones <= 0:
        raise ValueError("max_publicaciones_por_busqueda debe ser mayor que 0.")
    if max_publicaciones_banco <= 0:
        raise ValueError("max_publicaciones_por_banco debe ser mayor que 0.")
    if max_comentarios <= 0:
        raise ValueError("max_comentarios_por_publicacion debe ser mayor que 0.")

    bancos_seleccionados = normalizar_bancos_seleccionados(
        configuracion.get("bancos_seleccionados", BANCOS_OBJETIVO)
    )
    filtrar_por_relevancia = bool(configuracion["filtrar_por_relevancia"])

    if plataforma == "linkedin":
        filtrar_por_relevancia = True

    return {
        "plataforma": plataforma,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "max_publicaciones_por_busqueda": max_publicaciones,
        "max_publicaciones_por_banco": max_publicaciones_banco,
        "max_comentarios_por_publicacion": max_comentarios,
        "leer_respuestas_comentarios": bool(
            configuracion.get("leer_respuestas_comentarios", False)
        ),
        "filtrar_por_fecha": bool(configuracion["filtrar_por_fecha"]),
        "filtrar_por_relevancia": filtrar_por_relevancia,
        "guardar_descartadas": bool(configuracion["guardar_descartadas"]),
        "bancos_seleccionados": bancos_seleccionados,
    }


def restar_meses(fecha, meses):
    mes_total = fecha.month - meses
    anio = fecha.year + ((mes_total - 1) // 12)
    mes = ((mes_total - 1) % 12) + 1
    dias_mes = [
        31,
        29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    dia = min(fecha.day, dias_mes[mes - 1])

    return date(anio, mes, dia)


def estimar_fecha_publicacion(fecha_visible, fecha_referencia=None):
    if not fecha_visible:
        return ""

    fecha_referencia = fecha_referencia or datetime.now().date()
    texto = limpiar_linea(fecha_visible).lower()
    texto = texto.replace("• editado", "").strip()
    coincidencia = re.search(
        r"(\d+)\s+"
        r"(segundo|segundos|minuto|minutos|hora|horas|"
        r"día|días|dia|dias|semana|semanas|mes|meses|"
        r"año|años|ano|anos)",
        texto,
    )

    if not coincidencia:
        return ""

    cantidad = int(coincidencia.group(1))
    unidad = coincidencia.group(2)

    if unidad.startswith(("segundo", "minuto", "hora")):
        fecha_estimada = fecha_referencia
    elif unidad in {"día", "días", "dia", "dias"}:
        fecha_estimada = fecha_referencia - timedelta(days=cantidad)
    elif unidad.startswith("semana"):
        fecha_estimada = fecha_referencia - timedelta(days=cantidad * 7)
    elif unidad.startswith("mes"):
        fecha_estimada = restar_meses(fecha_referencia, cantidad)
    else:
        fecha_estimada = restar_meses(fecha_referencia, cantidad * 12)

    return fecha_estimada.isoformat()


def esta_en_rango(fecha_iso, fecha_inicio, fecha_fin):
    if not fecha_iso:
        return False

    fecha = date.fromisoformat(fecha_iso)

    return fecha_inicio <= fecha <= fecha_fin


# ----------------------------------------------
# Funciones de relevancia
# ----------------------------------------------
def normalizar_texto_busqueda(texto):
    """
    Convierte texto libre a una forma estable para comparar palabras clave.

    La normalización quita tildes, pasa a minúsculas y reemplaza signos por
    espacios. Así "Bogotá", "bogota" y "BOGOTA" se comparan igual.
    """

    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9ñ]+", " ", texto)

    return limpiar_linea(texto)


def buscar_terminos(texto, terminos):
    """
    Devuelve los términos que aparecen en el texto normalizado.

    Se usa una comparación por frase completa para evitar coincidencias muy
    débiles dentro de otras palabras.
    """

    texto_normalizado = f" {normalizar_texto_busqueda(texto)} "
    encontrados = []

    for termino in terminos:
        termino_normalizado = normalizar_texto_busqueda(termino)

        if termino_normalizado and f" {termino_normalizado} " in texto_normalizado:
            encontrados.append(termino)

    return encontrados


def combinar_terminos(*listas_terminos):
    combinados = []

    for terminos in listas_terminos:
        for termino in terminos:
            if termino not in combinados:
                combinados.append(termino)

    return combinados


def evaluar_relevancia_publicacion(banco, texto_publicacion, texto_visible):
    """
    Clasifica una publicación antes de guardarla.

    Regla principal:
    - Debe mencionar el banco objetivo.
    - Debe contener al menos una señal de fraude, denuncia, robo o suplantación.
    - Debe tener señales de denuncia directa o caso real, no solo prevención,
      educación, podcast, noticia o promoción de servicios.

    El resultado incluye motivos y términos encontrados para poder auditar y
    ajustar el filtro con ejemplos reales.
    """

    aliases_banco = CRITERIOS_RELEVANCIA["aliases_bancos"].get(banco, [banco])
    texto_para_banco = f"{texto_publicacion}\n{texto_visible}"
    terminos_banco = buscar_terminos(texto_para_banco, aliases_banco)
    terminos_fraude = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_fraude"],
    )
    terminos_fuertes = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_fraude_fuertes"],
    )
    terminos_contexto = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_contexto_denuncia"],
    )
    terminos_bancarios = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_contexto_bancario"],
    )
    terminos_comerciales = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_comerciales"],
    )
    terminos_educativos = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_educativos_preventivos"],
    )
    terminos_noticia = buscar_terminos(
        texto_publicacion,
        CRITERIOS_RELEVANCIA["terminos_noticia_reporte"],
    )
    terminos_exclusion = combinar_terminos(
        terminos_comerciales,
        terminos_educativos,
        terminos_noticia,
    )

    if terminos_contexto:
        tipo_contenido = "denuncia_directa"
    elif terminos_comerciales:
        tipo_contenido = "comercial_servicios"
    elif terminos_educativos:
        tipo_contenido = "educativo_preventivo"
    elif terminos_noticia:
        tipo_contenido = "noticia_o_reporte"
    else:
        tipo_contenido = "indeterminado"

    def respuesta(es_relevante, relevancia, motivo, tipo=None):
        return {
            "es_relevante": es_relevante,
            "relevancia": relevancia,
            "motivo": motivo,
            "tipo_contenido": tipo or tipo_contenido,
            "terminos_banco": ", ".join(terminos_banco),
            "terminos_fraude": ", ".join(terminos_fraude),
            "terminos_contexto": ", ".join(terminos_contexto),
            "terminos_contexto_bancario": ", ".join(terminos_bancarios),
            "terminos_exclusion": ", ".join(terminos_exclusion),
        }

    if not terminos_banco:
        return respuesta(
            False,
            "descartada",
            "No menciona el banco objetivo",
        )

    if not terminos_fraude:
        return respuesta(
            False,
            "descartada",
            "No contiene palabras de fraude o denuncia",
        )

    if not terminos_bancarios:
        return respuesta(
            False,
            "descartada",
            "No contiene contexto bancario operativo",
        )

    if terminos_comerciales and not terminos_contexto:
        return respuesta(
            False,
            "descartada",
            "Contenido comercial o de servicios, no denuncia directa",
            "comercial_servicios",
        )

    if terminos_educativos and not terminos_contexto:
        return respuesta(
            False,
            "descartada",
            "Contenido educativo o preventivo, no denuncia directa",
            "educativo_preventivo",
        )

    if terminos_noticia and not terminos_contexto:
        return respuesta(
            False,
            "descartada",
            "Noticia o reporte general, no denuncia directa",
            "noticia_o_reporte",
        )

    if not terminos_contexto:
        return respuesta(
            False,
            "descartada",
            "Menciona fraude, pero no presenta una denuncia directa",
        )

    relevancia = "alta" if terminos_fuertes or len(terminos_fraude) >= 2 else "media"

    return respuesta(
        True,
        relevancia,
        "Menciona banco objetivo y denuncia directa de fraude",
        "denuncia_directa",
    )


# ----------------------------------------------
# Funciones para buscar y recolectar publicaciones
# ----------------------------------------------
def construir_url_busqueda(busqueda):
    return (
        "https://www.linkedin.com/search/results/content/"
        f"?keywords={quote(busqueda)}&origin=GLOBAL_SEARCH_HEADER"
    )


def limpiar_linea(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def resumir_error(error, max_caracteres=450):
    texto = limpiar_linea(str(error))

    if len(texto) <= max_caracteres:
        return texto

    return f"{texto[:max_caracteres].rstrip()}..."


def url_actual_segura(page):
    try:
        return page.url
    except Exception:
        return ""


def detener_carga_pagina(page):
    try:
        page.evaluate("window.stop()")
    except Exception:
        pass


def navegar_linkedin_con_reintentos(
    page,
    url,
    descripcion,
    fragmento_esperado=None,
    intentos=INTENTOS_NAVEGACION_LINKEDIN,
    timeout=TIMEOUT_NAVEGACION_LINKEDIN_MS,
):
    ultimo_error = None

    for intento in range(1, intentos + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except PlaywrightTimeoutError as error:
            ultimo_error = error
            url_actual = url_actual_segura(page)

            if fragmento_esperado and fragmento_esperado in url_actual:
                print(
                    f"Aviso: {descripcion} tardo mas de "
                    f"{round(timeout / 1000)}s, pero ya esta en la URL esperada. "
                    "Se continua con la extraccion."
                )
                detener_carga_pagina(page)
                return

            print(
                f"Aviso: no cargo {descripcion} en el intento "
                f"{intento}/{intentos}. URL actual: {url_actual or 'no disponible'}"
            )
            detener_carga_pagina(page)

            if intento < intentos:
                page.wait_for_timeout(3000)
                continue

        except Exception as error:
            ultimo_error = error
            print(
                f"Aviso: fallo la navegacion de {descripcion} en el intento "
                f"{intento}/{intentos}: {resumir_error(error)}"
            )
            detener_carga_pagina(page)

            if intento < intentos:
                page.wait_for_timeout(3000)
                continue

    raise ultimo_error


def formatear_rango_fecha(configuracion):
    return (
        f"{configuracion['fecha_inicio'].isoformat()} a "
        f"{configuracion['fecha_fin'].isoformat()}"
    )


def formatear_fecha_ejecucion(fecha_ejecucion):
    return fecha_ejecucion.strftime("%d-%m-%Y")


def preparar_rutas_ejecucion(configuracion):
    global RUTA_EJECUCION
    global RUTA_PUBLICACIONES
    global RUTA_DESCARTADAS
    global RUTA_CONTEO_BANCOS
    global RUTA_COMPARATIVO_POPULAR
    global RUTA_TIEMPOS_EJECUCION
    global RUTA_REPORTE_EXCEL
    global RUTA_CAPTURAS

    fecha_ejecucion = datetime.now()
    fecha_archivo = formatear_fecha_ejecucion(fecha_ejecucion)
    marca_ejecucion = fecha_ejecucion.strftime("%d-%m-%Y_%H-%M-%S")
    RUTA_RESULTADOS.mkdir(exist_ok=True)

    ruta_ejecucion = RUTA_RESULTADOS / f"ejecucion_{marca_ejecucion}"
    contador = 2

    while ruta_ejecucion.exists():
        ruta_ejecucion = RUTA_RESULTADOS / f"ejecucion_{marca_ejecucion}_{contador}"
        contador += 1

    ruta_ejecucion.mkdir(parents=True, exist_ok=True)

    RUTA_EJECUCION = ruta_ejecucion
    RUTA_PUBLICACIONES = ruta_ejecucion / "publicaciones_linkedin.csv"
    RUTA_DESCARTADAS = ruta_ejecucion / "publicaciones_descartadas.csv"
    RUTA_CONTEO_BANCOS = ruta_ejecucion / "conteo_por_banco.csv"
    RUTA_COMPARATIVO_POPULAR = ruta_ejecucion / "comparativo_banco_popular.csv"
    RUTA_TIEMPOS_EJECUCION = ruta_ejecucion / "tiempos_ejecucion.csv"
    RUTA_REPORTE_EXCEL = ruta_ejecucion / "reporte_bancos.xlsx"
    RUTA_CAPTURAS = ruta_ejecucion / "capturas_publicaciones"

    configuracion = configuracion.copy()
    configuracion["fecha_ejecucion"] = fecha_ejecucion
    configuracion["fecha_ejecucion_archivo"] = fecha_archivo
    configuracion["ruta_ejecucion"] = ruta_ejecucion

    return configuracion


def normalizar_nombre_archivo(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)

    return texto.strip("_") or "sin_nombre"


def ruta_relativa_proyecto(ruta):
    base = Path(__file__).resolve().parent

    try:
        return str(Path(ruta).resolve().relative_to(base))
    except ValueError:
        return str(ruta)


def siguiente_serial_banco(contadores_seriales, banco, tipo_resultado):
    clave = (tipo_resultado, banco)
    contadores_seriales[clave] = contadores_seriales.get(clave, 0) + 1
    return contadores_seriales[clave]


def expandir_publicacion(item):
    patrones = [
        re.compile(r"^\s*(?:\.{3}|…)?\s*m[aá]s\s*$", re.IGNORECASE),
        re.compile(r"ver\s+m[aá]s", re.IGNORECASE),
        re.compile(r"mostrar\s+m[aá]s", re.IGNORECASE),
        re.compile(r"see\s+more", re.IGNORECASE),
    ]
    selector_controles = "button, span[role='button'], a[role='button']"

    for _ in range(5):
        expandio = False

        for patron in patrones:
            controles = item.locator(selector_controles).filter(has_text=patron)

            try:
                cantidad = min(controles.count(), 5)
            except Exception:
                continue

            for i in range(cantidad):
                control = controles.nth(i)

                try:
                    if control.is_visible():
                        control.click(timeout=3000)
                        time.sleep(0.45)
                        expandio = True
                except Exception:
                    pass

        try:
            expandio_js = item.evaluate(
                """
                (el) => {
                    const normalizar = (valor) => (
                        valor || ''
                    ).replace(/\\s+/g, ' ').trim().toLowerCase();

                    const esControlExpandir = (control) => {
                        const textos = [
                            control.innerText,
                            control.textContent,
                            control.getAttribute('aria-label'),
                            control.getAttribute('title')
                        ].map(normalizar).filter(Boolean);

                        return textos.some((texto) => (
                            texto === 'más' ||
                            texto === 'mas' ||
                            texto === '... más' ||
                            texto === '... mas' ||
                            texto === '… más' ||
                            texto === '… mas' ||
                            texto === 'ver más' ||
                            texto === 'ver mas' ||
                            texto === 'mostrar más' ||
                            texto === 'mostrar mas' ||
                            texto === 'see more' ||
                            texto.endsWith('... más') ||
                            texto.endsWith('... mas') ||
                            texto.endsWith('… más') ||
                            texto.endsWith('… mas')
                        ));
                    };

                    const controles = Array.from(
                        el.querySelectorAll('button, [role="button"], a[role="button"]')
                    );
                    const control = controles.find((candidato) => {
                        const caja = candidato.getBoundingClientRect();
                        return caja.width > 0 && caja.height > 0 && esControlExpandir(candidato);
                    });

                    if (!control) {
                        return false;
                    }

                    control.click();
                    return true;
                }
                """
            )

            if expandio_js:
                time.sleep(0.45)
                expandio = True
        except Exception:
            pass

        if not expandio:
            break


def ajustar_viewport_para_publicacion(page, item):
    viewport_original = page.viewport_size

    if not viewport_original:
        return None

    try:
        caja = item.bounding_box(timeout=5000)
    except Exception:
        return None

    if not caja:
        return None

    alto_necesario = int(caja["height"]) + 160
    alto_actual = viewport_original["height"]

    if alto_necesario <= alto_actual:
        return None

    alto_nuevo = min(alto_necesario, 5000)
    page.set_viewport_size(
        {
            "width": viewport_original["width"],
            "height": alto_nuevo,
        }
    )
    time.sleep(0.2)

    return viewport_original


def capturar_imagen_publicacion(
    page,
    item,
    banco,
    imagen_serial,
    tipo_resultado,
    fecha_archivo,
):
    carpeta_banco = RUTA_CAPTURAS / tipo_resultado / normalizar_nombre_archivo(banco)
    carpeta_banco.mkdir(parents=True, exist_ok=True)
    ruta_imagen = carpeta_banco / f"{fecha_archivo}_{imagen_serial}.png"
    viewport_original = None

    try:
        item.scroll_into_view_if_needed(timeout=5000)
        expandir_publicacion(item)
        item.scroll_into_view_if_needed(timeout=5000)
        viewport_original = ajustar_viewport_para_publicacion(page, item)
        expandir_publicacion(item)
        item.scroll_into_view_if_needed(timeout=5000)
        item.screenshot(path=str(ruta_imagen), timeout=15000, animations="disabled")
    except Exception as e:
        print(f"No se pudo capturar la imagen {imagen_serial}: {e}")
        return "", ""
    finally:
        if viewport_original:
            try:
                page.set_viewport_size(viewport_original)
            except Exception:
                pass

    return ruta_relativa_proyecto(ruta_imagen), ruta_imagen.name


def limpiar_texto_publicacion(texto):
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    lineas = [linea.strip() for linea in texto.split("\n")]
    return "\n".join(linea for linea in lineas if linea)


def extraer_metricas(texto_visible):
    metricas = {
        "reacciones": "",
        "comentarios": "",
        "compartidos": "",
    }

    patrones = {
        "reacciones": r"(\d[\d.,]*(?:\s*(?:mil|k))?)\s+reacciones?",
        "comentarios": r"(\d[\d.,]*(?:\s*(?:mil|k))?)\s+comentarios?",
        "compartidos": r"(\d[\d.,]*(?:\s*(?:mil|k))?)\s+veces compartido",
    }

    for nombre, patron in patrones.items():
        coincidencia = re.search(patron, texto_visible or "", flags=re.IGNORECASE)
        if coincidencia:
            metricas[nombre] = limpiar_linea(coincidencia.group(1))

    return metricas


def convertir_metrica_a_entero(valor):
    texto = limpiar_linea(valor).lower()

    if not texto:
        return 0

    multiplicador = 1

    if texto.endswith("mil"):
        multiplicador = 1000
        texto = texto[:-3].strip()
    elif texto.endswith("k"):
        multiplicador = 1000
        texto = texto[:-1].strip()

    coincidencia = re.search(r"\d[\d.,]*", texto)

    if not coincidencia:
        return 0

    numero = coincidencia.group(0)

    if multiplicador > 1:
        numero = numero.replace(",", ".")
        try:
            return int(float(numero) * multiplicador)
        except ValueError:
            return 0

    numero = numero.replace(".", "").replace(",", "")

    try:
        return int(numero)
    except ValueError:
        return 0


def calcular_interacciones_total(metricas):
    return sum(
        convertir_metrica_a_entero(metricas.get(nombre, ""))
        for nombre in ("reacciones", "comentarios", "compartidos")
    )


def extraer_fecha_visible(texto_visible):
    patron = (
        r"\b(\d+\s+(?:segundo|segundos|minuto|minutos|hora|horas|"
        r"día|días|dia|dias|semana|semanas|mes|meses|año|años|ano|anos)"
        r"(?:\s*•\s*Editado)?)\b"
    )
    coincidencia = re.search(patron, texto_visible or "", flags=re.IGNORECASE)
    if not coincidencia:
        return ""

    return limpiar_linea(coincidencia.group(1))


def extraer_datos_item_publicacion(item):
    return item.evaluate(
        """
        (el) => {
            const textoEl = el.querySelector('span[data-testid="expandable-text-box"]');

            if (!textoEl) {
                return null;
            }

            const links = Array.from(el.querySelectorAll('a[href]'));
            const autorLink = links.find((link) => {
                const href = link.href || '';
                const texto = (link.innerText || '').trim();
                const img = link.querySelector('img');
                const alt = img ? (img.getAttribute('alt') || '') : '';
                const aria = link.getAttribute('aria-label') || '';

                return (
                    (href.includes('/in/') || href.includes('/company/')) &&
                    (texto || alt || aria)
                );
            });

            let autor = '';
            let urlAutor = '';

            if (autorLink) {
                const img = autorLink.querySelector('img');
                const alt = img ? (img.getAttribute('alt') || '') : '';
                autor = (
                    (autorLink.innerText || '').trim().split('\\n')[0] ||
                    alt ||
                    autorLink.getAttribute('aria-label') ||
                    ''
                );
                urlAutor = autorLink.href || '';
            }

            const postLink = links.find((link) => {
                const href = link.href || '';
                return href.includes('/feed/update/') || href.includes('/activity-');
            });

            return {
                texto: (textoEl.innerText || '').trim(),
                autor: autor,
                url_autor: urlAutor,
                url_publicacion: postLink ? postLink.href : '',
                texto_visible: el.innerText || ''
            };
        }
        """
    )


def cargar_mas_resultados(page, limite):
    intentos_maximos = 6

    for _ in range(intentos_maximos):
        textos_publicaciones = page.locator(
            "div[role='listitem'] span[data-testid='expandable-text-box']"
        )

        if textos_publicaciones.count() >= limite:
            return

        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(1500)

        boton_cargar_mas = page.locator("button").filter(
            has_text=re.compile("Cargar más", re.IGNORECASE)
        )

        try:
            if boton_cargar_mas.count() > 0 and boton_cargar_mas.first.is_visible():
                boton_cargar_mas.first.click()
                page.wait_for_timeout(2500)
        except Exception:
            pass


def extraer_publicaciones_visibles(
    page,
    banco,
    busqueda,
    limite,
    configuracion,
    contadores_seriales=None,
    claves_vistas_publicaciones=None,
    claves_vistas_descartadas=None,
):
    publicaciones = []
    descartadas = []
    items = page.locator("div[role='listitem']")
    cantidad = items.count()
    fecha_inicio = configuracion["fecha_inicio"]
    fecha_fin = configuracion["fecha_fin"]
    filtrar_por_fecha = configuracion["filtrar_por_fecha"]
    filtrar_por_relevancia = configuracion["filtrar_por_relevancia"]
    guardar_descartadas = configuracion["guardar_descartadas"]
    rango_fecha = formatear_rango_fecha(configuracion)
    fecha_archivo = configuracion.get(
        "fecha_ejecucion_archivo",
        formatear_fecha_ejecucion(datetime.now()),
    )

    if contadores_seriales is None:
        contadores_seriales = {}
    if claves_vistas_publicaciones is None:
        claves_vistas_publicaciones = set()
    if claves_vistas_descartadas is None:
        claves_vistas_descartadas = set()

    for i in range(cantidad):
        if len(publicaciones) >= limite:
            break

        item = items.nth(i)

        try:
            item.scroll_into_view_if_needed(timeout=5000)
            expandir_publicacion(item)
            datos = extraer_datos_item_publicacion(item)
        except Exception:
            continue

        if not datos or not datos.get("texto"):
            continue

        texto_visible = datos.get("texto_visible", "")
        fecha_visible = extraer_fecha_visible(texto_visible)
        fecha_estimada = estimar_fecha_publicacion(fecha_visible)
        fecha_en_rango = esta_en_rango(fecha_estimada, fecha_inicio, fecha_fin)

        if filtrar_por_fecha and not fecha_en_rango:
            continue

        texto_publicacion = limpiar_texto_publicacion(datos.get("texto"))
        evaluacion = evaluar_relevancia_publicacion(
            banco,
            texto_publicacion,
            texto_visible,
        )
        metricas = extraer_metricas(texto_visible)
        es_descartada = filtrar_por_relevancia and not evaluacion["es_relevante"]

        if es_descartada and not guardar_descartadas:
            continue

        clave_deduplicacion = construir_clave_deduplicacion(
            banco,
            datos.get("autor"),
            texto_publicacion,
        )
        claves_vistas = (
            claves_vistas_descartadas if es_descartada else claves_vistas_publicaciones
        )

        if clave_deduplicacion in claves_vistas:
            continue

        claves_vistas.add(clave_deduplicacion)

        tipo_resultado = "descartadas" if es_descartada else "publicaciones"
        serial_banco = siguiente_serial_banco(
            contadores_seriales,
            banco,
            tipo_resultado,
        )
        imagen_serial = f"{normalizar_nombre_archivo(banco)}_{serial_banco:04d}"
        ruta_imagen, nombre_imagen = capturar_imagen_publicacion(
            page,
            item,
            banco,
            imagen_serial,
            tipo_resultado,
            fecha_archivo,
        )

        registro = {
            "imagen_serial": imagen_serial,
            "serial_por_banco": serial_banco,
            "imagen_publicacion": ruta_imagen,
            "archivo_imagen": nombre_imagen,
            "tipo_resultado": tipo_resultado,
            "banco": banco,
            "busqueda": busqueda,
            "autor": limpiar_linea(datos.get("autor")),
            "fecha_visible": fecha_visible,
            "fecha_publicacion_estimada": fecha_estimada,
            "fecha_en_rango": "si" if fecha_en_rango else "no",
            "rango_fecha": rango_fecha,
            "rango_fecha_inicio": fecha_inicio.isoformat(),
            "rango_fecha_fin": fecha_fin.isoformat(),
            "tipo_contenido": evaluacion["tipo_contenido"],
            "relevancia": evaluacion["relevancia"],
            "motivo_relevancia": evaluacion["motivo"],
            "terminos_banco": evaluacion["terminos_banco"],
            "terminos_fraude": evaluacion["terminos_fraude"],
            "terminos_contexto": evaluacion["terminos_contexto"],
            "terminos_contexto_bancario": evaluacion["terminos_contexto_bancario"],
            "terminos_exclusion": evaluacion["terminos_exclusion"],
            "texto": texto_publicacion,
            "reacciones": metricas["reacciones"],
            "comentarios": metricas["comentarios"],
            "compartidos": metricas["compartidos"],
            "interacciones_total": calcular_interacciones_total(metricas),
            "url": datos.get("url_publicacion") or datos.get("url_autor") or page.url,
            "fecha_recoleccion": datetime.now().isoformat(timespec="seconds"),
        }

        if es_descartada:
            descartadas.append(registro)
            continue

        publicaciones.append(registro)

    return publicaciones, descartadas


def normalizar_para_deduplicar(texto):
    return limpiar_linea(texto).lower()


def construir_clave_deduplicacion(banco, autor, texto):
    return (
        banco,
        normalizar_para_deduplicar(autor),
        normalizar_para_deduplicar(texto)[:700],
    )


def deduplicar_publicaciones(publicaciones):
    publicaciones_unicas = []
    claves_vistas = set()

    for publicacion in publicaciones:
        clave = construir_clave_deduplicacion(
            publicacion["banco"],
            publicacion["autor"],
            publicacion["texto"],
        )

        if clave in claves_vistas:
            continue

        claves_vistas.add(clave)
        publicaciones_unicas.append(publicacion)

    return publicaciones_unicas


def contar_publicaciones_por_banco(publicaciones, bancos=None):
    bancos = bancos or BANCOS_OBJETIVO
    conteo = {banco: 0 for banco in bancos}

    for publicacion in publicaciones:
        banco = publicacion["banco"]
        conteo[banco] = conteo.get(banco, 0) + 1

    return conteo


def campos_resultados():
    """
    Define el contrato completo de columnas para auditoria y descartadas.
    """

    return [
        "imagen_serial",
        "serial_por_banco",
        "imagen_publicacion",
        "archivo_imagen",
        "tipo_resultado",
        "banco",
        "busqueda",
        "autor",
        "fecha_visible",
        "fecha_publicacion_estimada",
        "fecha_en_rango",
        "rango_fecha",
        "rango_fecha_inicio",
        "rango_fecha_fin",
        "tipo_contenido",
        "relevancia",
        "motivo_relevancia",
        "terminos_banco",
        "terminos_fraude",
        "terminos_contexto",
        "terminos_contexto_bancario",
        "terminos_exclusion",
        "texto",
        "reacciones",
        "comentarios",
        "compartidos",
        "interacciones_total",
        "url",
        "fecha_recoleccion",
    ]


def campos_publicaciones():
    """
    Columnas para publicaciones relevantes. No incluye relevancia ni motivo,
    porque todas las filas de este archivo ya son denuncias directas incluidas.
    """

    return [
        campo
        for campo in campos_resultados()
        if campo not in {"relevancia", "motivo_relevancia"}
    ]


def escribir_csv(ruta, filas, campos):
    """
    Escribe CSV con BOM UTF-8 para que Excel abra bien tildes y eñes.
    """

    with ruta.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def letra_columna_excel(indice):
    letras = ""

    while indice:
        indice, residuo = divmod(indice - 1, 26)
        letras = chr(65 + residuo) + letras

    return letras


def limpiar_valor_xml(valor):
    texto = "" if valor is None else str(valor)
    texto = "".join(
        caracter
        for caracter in texto
        if caracter in "\t\n\r" or ord(caracter) >= 32
    )
    return escape(texto, {'"': "&quot;"})


def es_numero_excel(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def celda_excel_xml(fila, columna, valor):
    referencia = f"{letra_columna_excel(columna)}{fila}"

    if es_numero_excel(valor):
        return f'<c r="{referencia}"><v>{valor}</v></c>'

    return (
        f'<c r="{referencia}" t="inlineStr">'
        f'<is><t xml:space="preserve">{limpiar_valor_xml(valor)}</t></is>'
        f"</c>"
    )


def hoja_datos_excel_xml(filas, campos):
    filas_excel = [campos]

    for fila in filas:
        filas_excel.append([fila.get(campo, "") for campo in campos])

    ancho = len(campos)
    alto = max(len(filas_excel), 1)
    dimension = f"A1:{letra_columna_excel(ancho)}{alto}"
    columnas = "".join(
        f'<col min="{indice}" max="{indice}" width="18" customWidth="1"/>'
        for indice in range(1, ancho + 1)
    )
    filas_xml = []

    for numero_fila, valores in enumerate(filas_excel, start=1):
        celdas = "".join(
            celda_excel_xml(numero_fila, indice, valor)
            for indice, valor in enumerate(valores, start=1)
        )
        filas_xml.append(f'<row r="{numero_fila}">{celdas}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        f"<cols>{columnas}</cols>"
        f"<sheetData>{''.join(filas_xml)}</sheetData>"
        "</worksheet>"
    )


def hoja_graficas_excel_xml():
    filas = [
        {"seccion": "Graficas", "descripcion": "Denuncias, comparativo e interacciones por banco"},
        {"seccion": "1", "descripcion": "Denuncias directas por banco"},
        {"seccion": "2", "descripcion": "Participacion porcentual por banco"},
        {"seccion": "3", "descripcion": "Interacciones promedio por banco"},
        {"seccion": "4", "descripcion": "Tiempo de ejecucion por banco"},
    ]
    hoja = hoja_datos_excel_xml(filas, ["seccion", "descripcion"])
    return hoja.replace("</worksheet>", '<drawing r:id="rId1"/></worksheet>')


def cache_categorias_xml(categorias):
    puntos = "".join(
        f'<c:pt idx="{indice}"><c:v>{limpiar_valor_xml(valor)}</c:v></c:pt>'
        for indice, valor in enumerate(categorias)
    )
    return f'<c:strCache><c:ptCount val="{len(categorias)}"/>{puntos}</c:strCache>'


def cache_numeros_xml(valores):
    puntos = "".join(
        f'<c:pt idx="{indice}"><c:v>{valor}</c:v></c:pt>'
        for indice, valor in enumerate(valores)
    )
    return (
        f'<c:numCache><c:formatCode>General</c:formatCode>'
        f'<c:ptCount val="{len(valores)}"/>{puntos}</c:numCache>'
    )


def rango_excel(nombre_hoja, columna, fila_inicio, fila_fin):
    return f"'{nombre_hoja}'!${columna}${fila_inicio}:${columna}${fila_fin}"


def crear_grafica_barras_xml(
    titulo,
    titulo_serie,
    hoja_datos,
    columna_categorias,
    columna_valores,
    fila_inicio,
    fila_fin,
    categorias,
    valores,
    eje_x=100001,
    eje_y=100002,
):
    formula_categorias = rango_excel(
        hoja_datos,
        columna_categorias,
        fila_inicio,
        fila_fin,
    )
    formula_valores = rango_excel(
        hoja_datos,
        columna_valores,
        fila_inicio,
        fila_fin,
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<c:chart>'
        '<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r>'
        f'<a:t>{limpiar_valor_xml(titulo)}</a:t>'
        '</a:r></a:p></c:rich></c:tx><c:overlay val="0"/></c:title>'
        '<c:plotArea><c:layout/>'
        '<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>'
        '<c:ser><c:idx val="0"/><c:order val="0"/>'
        f'<c:tx><c:v>{limpiar_valor_xml(titulo_serie)}</c:v></c:tx>'
        '<c:cat><c:strRef>'
        f'<c:f>{limpiar_valor_xml(formula_categorias)}</c:f>'
        f'{cache_categorias_xml(categorias)}'
        '</c:strRef></c:cat>'
        '<c:val><c:numRef>'
        f'<c:f>{limpiar_valor_xml(formula_valores)}</c:f>'
        f'{cache_numeros_xml(valores)}'
        '</c:numRef></c:val>'
        '</c:ser>'
        f'<c:axId val="{eje_x}"/><c:axId val="{eje_y}"/>'
        '</c:barChart>'
        f'<c:catAx><c:axId val="{eje_x}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
        '<c:axPos val="b"/><c:tickLblPos val="nextTo"/>'
        f'<c:crossAx val="{eje_y}"/><c:crosses val="autoZero"/><c:auto val="1"/>'
        '</c:catAx>'
        f'<c:valAx><c:axId val="{eje_y}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
        '<c:axPos val="l"/><c:majorGridlines/><c:numFmt formatCode="General" sourceLinked="1"/>'
        f'<c:tickLblPos val="nextTo"/><c:crossAx val="{eje_x}"/><c:crosses val="autoZero"/>'
        '</c:valAx>'
        '</c:plotArea>'
        '<c:legend><c:legendPos val="r"/><c:overlay val="0"/></c:legend>'
        '<c:plotVisOnly val="1"/>'
        '</c:chart>'
        '</c:chartSpace>'
    )


def ancla_grafica_xml(indice, relacion, columna_inicio, fila_inicio, columna_fin, fila_fin):
    return (
        '<xdr:twoCellAnchor>'
        f'<xdr:from><xdr:col>{columna_inicio}</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>{fila_inicio}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
        f'<xdr:to><xdr:col>{columna_fin}</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>{fila_fin}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
        '<xdr:graphicFrame macro="">'
        '<xdr:nvGraphicFramePr>'
        f'<xdr:cNvPr id="{indice + 1}" name="Grafica {indice}"/>'
        '<xdr:cNvGraphicFramePr/>'
        '</xdr:nvGraphicFramePr>'
        '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        f'<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{relacion}"/>'
        '</a:graphicData></a:graphic>'
        '</xdr:graphicFrame><xdr:clientData/>'
        '</xdr:twoCellAnchor>'
    )


def drawing_graficas_xml():
    anclas = [
        ancla_grafica_xml(1, "rId1", 0, 6, 8, 23),
        ancla_grafica_xml(2, "rId2", 9, 6, 17, 23),
        ancla_grafica_xml(3, "rId3", 0, 25, 8, 42),
        ancla_grafica_xml(4, "rId4", 9, 25, 17, 42),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"{''.join(anclas)}"
        "</xdr:wsDr>"
    )


def crear_reporte_excel(
    publicaciones,
    descartadas,
    filas_conteo,
    filas_comparativo,
    filas_tiempos,
):
    campos_publicacion = campos_publicaciones()
    campos_resultado = campos_resultados()
    campos_conteo = ["banco", "rango_fecha", "publicaciones"]
    campos_comparativo = campos_comparativo_banco_popular()
    campos_tiempos = campos_tiempos_ejecucion()
    filas_tiempos_banco = [
        fila for fila in filas_tiempos if fila.get("tipo_tiempo") == "busqueda"
    ]

    hojas = [
        ("Publicaciones", hoja_datos_excel_xml(publicaciones, campos_publicacion)),
        ("Descartadas", hoja_datos_excel_xml(descartadas, campos_resultado)),
        ("Conteo por banco", hoja_datos_excel_xml(filas_conteo, campos_conteo)),
        (
            "Comparativo Popular",
            hoja_datos_excel_xml(filas_comparativo, campos_comparativo),
        ),
        ("Tiempos ejecucion", hoja_datos_excel_xml(filas_tiempos, campos_tiempos)),
        ("Graficas", hoja_graficas_excel_xml()),
    ]

    total_bancos = len(filas_conteo)
    fila_fin_conteo = total_bancos + 1
    fila_fin_comparativo = len(filas_comparativo) + 1
    fila_fin_tiempos = len(filas_tiempos_banco) + 1
    categorias_conteo = [fila["banco"] for fila in filas_conteo]
    valores_conteo = [fila["publicaciones"] for fila in filas_conteo]
    categorias_comparativo = [fila["banco"] for fila in filas_comparativo]
    valores_participacion = [
        fila["participacion_total_porcentaje"] for fila in filas_comparativo
    ]
    valores_interacciones = [
        fila["interacciones_promedio"] for fila in filas_comparativo
    ]
    categorias_tiempos = [fila["banco"] for fila in filas_tiempos_banco]
    valores_tiempos = [fila["duracion_segundos"] for fila in filas_tiempos_banco]
    graficas = [
        crear_grafica_barras_xml(
            "Denuncias directas por banco",
            "Denuncias",
            "Conteo por banco",
            "A",
            "C",
            2,
            fila_fin_conteo,
            categorias_conteo,
            valores_conteo,
            100001,
            100002,
        ),
        crear_grafica_barras_xml(
            "Participacion porcentual por banco",
            "Participacion %",
            "Comparativo Popular",
            "A",
            "E",
            2,
            fila_fin_comparativo,
            categorias_comparativo,
            valores_participacion,
            100003,
            100004,
        ),
        crear_grafica_barras_xml(
            "Interacciones promedio por banco",
            "Interacciones promedio",
            "Comparativo Popular",
            "A",
            "I",
            2,
            fila_fin_comparativo,
            categorias_comparativo,
            valores_interacciones,
            100005,
            100006,
        ),
        crear_grafica_barras_xml(
            "Tiempo de ejecucion por banco",
            "Segundos",
            "Tiempos ejecucion",
            "B",
            "H",
            2,
            fila_fin_tiempos,
            categorias_tiempos,
            valores_tiempos,
            100007,
            100008,
        ),
    ]

    workbook_sheets = "".join(
        f'<sheet name="{limpiar_valor_xml(nombre)}" sheetId="{indice}" r:id="rId{indice}"/>'
        for indice, (nombre, _) in enumerate(hojas, start=1)
    )
    workbook_rels = "".join(
        '<Relationship '
        f'Id="rId{indice}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{indice}.xml"/>'
        for indice in range(1, len(hojas) + 1)
    )
    workbook_rels += (
        '<Relationship Id="rId99" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    overrides_hojas = "".join(
        f'<Override PartName="/xl/worksheets/sheet{indice}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for indice in range(1, len(hojas) + 1)
    )
    overrides_graficas = "".join(
        f'<Override PartName="/xl/charts/chart{indice}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>'
        for indice in range(1, len(graficas) + 1)
    )
    drawing_rels = "".join(
        '<Relationship '
        f'Id="rId{indice}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" '
        f'Target="../charts/chart{indice}.xml"/>'
        for indice in range(1, len(graficas) + 1)
    )

    with zipfile.ZipFile(RUTA_REPORTE_EXCEL, "w", zipfile.ZIP_DEFLATED) as archivo:
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
            '<Override PartName="/xl/drawings/drawing1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
            '<Override PartName="/docProps/core.xml" '
            'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            f"{overrides_hojas}{overrides_graficas}"
            "</Types>",
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
            "docProps/core.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>Reporte bancos</dc:title>'
            '<dc:creator>Proyecto fraude</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now().isoformat(timespec="seconds")}</dcterms:created>'
            "</cp:coreProperties>",
        )
        archivo.writestr(
            "docProps/app.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<Application>Proyecto fraude</Application>'
            "</Properties>",
        )
        archivo.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets>"
            "</workbook>",
        )
        archivo.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{workbook_rels}"
            "</Relationships>",
        )
        archivo.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '</styleSheet>',
        )

        for indice, (_, xml_hoja) in enumerate(hojas, start=1):
            archivo.writestr(f"xl/worksheets/sheet{indice}.xml", xml_hoja)

        archivo.writestr(
            "xl/worksheets/_rels/sheet6.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" '
            'Target="../drawings/drawing1.xml"/>'
            "</Relationships>",
        )
        archivo.writestr("xl/drawings/drawing1.xml", drawing_graficas_xml())
        archivo.writestr(
            "xl/drawings/_rels/drawing1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{drawing_rels}"
            "</Relationships>",
        )

        for indice, xml_grafica in enumerate(graficas, start=1):
            archivo.writestr(f"xl/charts/chart{indice}.xml", xml_grafica)


def campos_comparativo_banco_popular():
    return [
        "banco",
        "grupo",
        "rango_fecha",
        "denuncias_directas",
        "participacion_total_porcentaje",
        "diferencia_vs_banco_popular",
        "multiplo_vs_banco_popular",
        "interacciones_total",
        "interacciones_promedio",
        "ranking_denuncias",
    ]


def campos_tiempos_ejecucion():
    return [
        "tipo_tiempo",
        "banco",
        "busqueda",
        "indice_busqueda",
        "total_busquedas",
        "inicio",
        "fin",
        "duracion_segundos",
        "duracion_minutos",
        "publicaciones_relevantes",
        "publicaciones_descartadas",
        "resultados_total",
        "estado",
        "detalle_error",
    ]


def guardar_comparativo_banco_popular(publicaciones, conteo, rango_fecha, bancos=None):
    banco_base = "Banco Popular Colombia"
    bancos = bancos or BANCOS_OBJETIVO
    total_general = sum(conteo.values())
    total_base = conteo.get(banco_base, 0) if banco_base in bancos else None
    interacciones_por_banco = {banco: 0 for banco in bancos}

    for publicacion in publicaciones:
        banco = publicacion["banco"]

        try:
            interacciones = int(publicacion.get("interacciones_total") or 0)
        except (TypeError, ValueError):
            interacciones = 0

        interacciones_por_banco[banco] = (
            interacciones_por_banco.get(banco, 0) + interacciones
        )

    ranking = {
        banco: posicion
        for posicion, (banco, _) in enumerate(
            sorted(conteo.items(), key=lambda item: (-item[1], item[0])),
            start=1,
        )
    }

    campos = campos_comparativo_banco_popular()
    filas_comparativo = []

    for banco in bancos:
        total = conteo.get(banco, 0)
        interacciones_total = interacciones_por_banco.get(banco, 0)

        participacion = round((total / total_general) * 100, 2) if total_general else 0
        promedio_interacciones = round(interacciones_total / total, 2) if total else 0
        diferencia = total - total_base if total_base is not None else ""
        multiplo = round(total / total_base, 2) if total_base else ""

        filas_comparativo.append(
            {
                "banco": banco,
                "grupo": "Banco Popular" if banco == banco_base else "Otros bancos",
                "rango_fecha": rango_fecha,
                "denuncias_directas": total,
                "participacion_total_porcentaje": participacion,
                "diferencia_vs_banco_popular": diferencia,
                "multiplo_vs_banco_popular": multiplo,
                "interacciones_total": interacciones_total,
                "interacciones_promedio": promedio_interacciones,
                "ranking_denuncias": ranking.get(banco, ""),
            }
        )

    escribir_csv(RUTA_COMPARATIVO_POPULAR, filas_comparativo, campos)

    return filas_comparativo


def guardar_resultados(publicaciones, descartadas, configuracion, tiempos_ejecucion):
    RUTA_EJECUCION.mkdir(parents=True, exist_ok=True)
    rango_fecha = formatear_rango_fecha(configuracion)
    bancos = configuracion.get("bancos_seleccionados", BANCOS_OBJETIVO)

    campos_publicacion = campos_publicaciones()
    campos = campos_resultados()
    escribir_csv(RUTA_PUBLICACIONES, publicaciones, campos_publicacion)

    if configuracion["guardar_descartadas"]:
        escribir_csv(RUTA_DESCARTADAS, descartadas, campos)

    conteo = contar_publicaciones_por_banco(publicaciones, bancos)
    filas_comparativo = guardar_comparativo_banco_popular(
        publicaciones,
        conteo,
        rango_fecha,
        bancos,
    )
    filas_conteo = [
        {
            "banco": banco,
            "rango_fecha": rango_fecha,
            "publicaciones": total,
        }
        for banco, total in conteo.items()
    ]
    escribir_csv(RUTA_TIEMPOS_EJECUCION, tiempos_ejecucion, campos_tiempos_ejecucion())

    with RUTA_CONTEO_BANCOS.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=["banco", "rango_fecha", "publicaciones"],
        )
        escritor.writeheader()
        escritor.writerows(filas_conteo)

    crear_reporte_excel(
        publicaciones,
        descartadas,
        filas_conteo,
        filas_comparativo,
        tiempos_ejecucion,
    )

    return conteo


def ejecutar_busquedas_linkedin(page, configuracion):
    publicaciones = []
    descartadas = []
    tiempos_ejecucion = []
    contadores_seriales = {}
    claves_vistas_publicaciones = set()
    claves_vistas_descartadas = set()
    limite = configuracion["max_publicaciones_por_busqueda"]
    objetivo_carga = limite * 3 if configuracion["filtrar_por_fecha"] else limite
    bancos = configuracion["bancos_seleccionados"]
    busquedas_linkedin = construir_busquedas_linkedin(bancos)
    total_busquedas = len(busquedas_linkedin)
    inicio_total_perf = time.perf_counter()
    inicio_total = datetime.now()

    print(
        "Rango de fechas configurado: "
        f"{configuracion['fecha_inicio'].isoformat()} a "
        f"{configuracion['fecha_fin'].isoformat()}"
    )
    print(f"Bancos seleccionados ({len(bancos)}): {', '.join(bancos)}")
    print(f"Total de búsquedas: {total_busquedas}")

    for indice, config in enumerate(busquedas_linkedin, start=1):
        banco = config["banco"]
        etiqueta = config.get("etiqueta", "")
        busqueda = config["busqueda"]
        url_busqueda = construir_url_busqueda(busqueda)
        inicio_busqueda_perf = time.perf_counter()
        inicio_busqueda = datetime.now()

        print(f"[{indice}/{total_busquedas}] Buscando: {banco} ({etiqueta})")
        try:
            navegar_linkedin_con_reintentos(
                page,
                url_busqueda,
                f"busqueda de {banco} ({etiqueta})",
                fragmento_esperado="/search/results/content/",
            )
        except Exception as error:
            fin_busqueda = datetime.now()
            duracion_segundos = round(time.perf_counter() - inicio_busqueda_perf, 2)
            detalle_error = resumir_error(error)
            print(
                f"No se pudo cargar la busqueda de {banco} ({etiqueta}) "
                "despues de los reintentos. Se continua con la siguiente busqueda."
            )
            print(f"Detalle navegacion: {detalle_error}")
            tiempos_ejecucion.append(
                {
                    "tipo_tiempo": "busqueda",
                    "banco": banco,
                    "busqueda": busqueda,
                    "indice_busqueda": indice,
                    "total_busquedas": total_busquedas,
                    "inicio": inicio_busqueda.isoformat(timespec="seconds"),
                    "fin": fin_busqueda.isoformat(timespec="seconds"),
                    "duracion_segundos": duracion_segundos,
                    "duracion_minutos": round(duracion_segundos / 60, 2),
                    "publicaciones_relevantes": 0,
                    "publicaciones_descartadas": 0,
                    "resultados_total": 0,
                    "estado": "error_navegacion",
                    "detalle_error": detalle_error,
                }
            )
            continue

        page.wait_for_timeout(5000)

        cargar_mas_resultados(page, objetivo_carga)

        publicaciones_busqueda, descartadas_busqueda = extraer_publicaciones_visibles(
            page,
            banco,
            busqueda,
            limite,
            configuracion,
            contadores_seriales,
            claves_vistas_publicaciones,
            claves_vistas_descartadas,
        )

        print(
            f"Publicaciones recolectadas para {banco}: "
            f"{len(publicaciones_busqueda)}"
        )
        print(
            f"Publicaciones descartadas por relevancia para {banco}: "
            f"{len(descartadas_busqueda)}"
        )
        fin_busqueda = datetime.now()
        duracion_segundos = round(time.perf_counter() - inicio_busqueda_perf, 2)
        tiempos_ejecucion.append(
            {
                "tipo_tiempo": "busqueda",
                "banco": banco,
                "busqueda": busqueda,
                "indice_busqueda": indice,
                "total_busquedas": total_busquedas,
                "inicio": inicio_busqueda.isoformat(timespec="seconds"),
                "fin": fin_busqueda.isoformat(timespec="seconds"),
                "duracion_segundos": duracion_segundos,
                "duracion_minutos": round(duracion_segundos / 60, 2),
                "publicaciones_relevantes": len(publicaciones_busqueda),
                "publicaciones_descartadas": len(descartadas_busqueda),
                "resultados_total": len(publicaciones_busqueda) + len(descartadas_busqueda),
                "estado": "ok",
                "detalle_error": "",
            }
        )

        publicaciones.extend(publicaciones_busqueda)
        descartadas.extend(descartadas_busqueda)
        time.sleep(2)

    publicaciones = deduplicar_publicaciones(publicaciones)
    descartadas = deduplicar_publicaciones(descartadas)
    fin_total = datetime.now()
    duracion_total_segundos = round(time.perf_counter() - inicio_total_perf, 2)
    tiempos_ejecucion.append(
        {
            "tipo_tiempo": "total_proyecto",
            "banco": "TOTAL",
            "busqueda": "TOTAL",
            "indice_busqueda": "",
            "total_busquedas": total_busquedas,
            "inicio": inicio_total.isoformat(timespec="seconds"),
            "fin": fin_total.isoformat(timespec="seconds"),
            "duracion_segundos": duracion_total_segundos,
            "duracion_minutos": round(duracion_total_segundos / 60, 2),
            "publicaciones_relevantes": len(publicaciones),
            "publicaciones_descartadas": len(descartadas),
            "resultados_total": len(publicaciones) + len(descartadas),
            "estado": "ok",
            "detalle_error": "",
        }
    )
    conteo = guardar_resultados(
        publicaciones,
        descartadas,
        configuracion,
        tiempos_ejecucion,
    )

    print(f"Archivo de publicaciones: {RUTA_PUBLICACIONES}")
    print(f"Archivo de descartadas: {RUTA_DESCARTADAS}")
    print(f"Archivo de conteo por banco: {RUTA_CONTEO_BANCOS}")
    print(f"Archivo comparativo Banco Popular: {RUTA_COMPARATIVO_POPULAR}")
    print(f"Archivo de tiempos: {RUTA_TIEMPOS_EJECUCION}")
    print(f"Reporte Excel: {RUTA_REPORTE_EXCEL}")
    print(f"Carpeta de capturas: {RUTA_CAPTURAS}")
    print(f"Total descartadas por relevancia: {len(descartadas)}")

    return publicaciones, conteo


# ----------------------------------------------
# Función para llenar solo inputs visibles
# ----------------------------------------------
def escribir_texto_como_humano(elemento, valor):
    elemento.click()
    elemento.press("Control+A")
    elemento.press("Backspace")

    for caracter in valor:
        elemento.type(caracter, delay=random.randint(45, 135))

        if caracter in {"@", ".", "_", "-", " "}:
            time.sleep(random.uniform(0.05, 0.18))

    time.sleep(random.uniform(0.2, 0.45))


def llenar_input_visible(page, selector, valor, nombre_campo):
    """
    Busca todos los elementos que coincidan con el selector,
    revisa cuál está visible y llena ese.
    """

    elementos = page.locator(selector)
    cantidad = elementos.count()

    print(f"Elementos encontrados para {nombre_campo}: {cantidad}")

    for i in range(cantidad):
        elemento = elementos.nth(i)

        try:
            if elemento.is_visible():
                print(f"{nombre_campo}: usando elemento visible #{i}")
                escribir_texto_como_humano(elemento, valor)
                return
        except Exception:
            pass

    raise Exception(f"No se encontró un campo visible para {nombre_campo}")


def obtener_input_visible(page, selector):
    elementos = page.locator(selector)

    for i in range(elementos.count()):
        elemento = elementos.nth(i)

        try:
            if elemento.is_visible() and elemento.is_enabled():
                return elemento
        except Exception:
            pass

    return None


def pagina_parece_sesion_linkedin_activa(page):
    """
    Detecta una sesion ya autenticada sin depender de una sola clase de LinkedIn.
    LinkedIn cambia etiquetas y rutas con frecuencia, por eso se combinan URL y
    senales visibles de navegacion/busqueda.
    """
    try:
        url_actual = page.url.lower()
        if any(
            ruta in url_actual
            for ruta in (
                "/feed",
                "/mynetwork",
                "/notifications",
                "/messaging",
                "/jobs",
                "/search/results",
            )
        ):
            return True
    except Exception:
        pass

    selectores_sesion = [
        "input[placeholder*='Buscar']",
        "input[aria-label*='Buscar']",
        "input[placeholder*='Search']",
        "input[aria-label*='Search']",
        "nav[aria-label*='Principal']",
        "nav[aria-label*='Primary']",
        "a[href*='/feed/']",
        "a[href*='/mynetwork/']",
        "a[href*='/notifications/']",
    ]

    for selector in selectores_sesion:
        try:
            elementos = page.locator(selector)
            for indice in range(min(elementos.count(), 5)):
                if elementos.nth(indice).is_visible():
                    return True
        except Exception:
            continue

    return False


def preparar_sesion_linkedin(page, usuario, contrasena):
    """
    Deja la pagina en un estado listo para buscar.

    Si LinkedIn muestra el formulario de login, llena credenciales y envia el
    formulario. Si el perfil persistente ya esta autenticado, o si aparece una
    pantalla de verificacion/captcha, no se considera error: se entrega el
    control al usuario y ENTER continua con las busquedas.
    """
    selector_usuario = "input[type='email'], input[autocomplete='username']"
    selector_contrasena = "input[type='password'], input[autocomplete='current-password']"

    print("Buscando campo de usuario...")
    campo_usuario = obtener_input_visible(page, selector_usuario)

    if campo_usuario is None:
        try:
            titulo = page.title()
        except Exception:
            titulo = "No disponible"

        print("No se encontro un formulario de inicio de sesion visible.")
        print(f"URL actual de LinkedIn: {page.url}")
        print(f"Titulo de la pagina: {titulo}")

        if pagina_parece_sesion_linkedin_activa(page):
            print("Parece que ya hay una sesion de LinkedIn iniciada.")
        else:
            print(
                "Si LinkedIn muestra captcha, codigo o una pantalla intermedia, "
                "completala en Chromium."
            )

        esperar_confirmacion_manual(page)
        return

    print("usuario: usando elemento visible")
    escribir_texto_como_humano(campo_usuario, usuario)
    print("Usuario escrito correctamente.")

    print("Buscando campo de contraseña...")
    llenar_input_visible(
        page,
        selector_contrasena,
        contrasena,
        "contraseña"
    )

    print("Contraseña escrita correctamente.")
    time.sleep(1)

    click_boton_iniciar_sesion(page)

    time.sleep(8)

    print("Login enviado.")
    print("Si LinkedIn pide código, captcha o verificación, complétalo manualmente.")
    esperar_confirmacion_manual(page)


# ----------------------------------------------
# Función para dar clic en el botón correcto
# ----------------------------------------------
def click_boton_iniciar_sesion(page):
    """
    Da clic únicamente en el botón final que dice exactamente:
    Iniciar sesión

    Evita botones como:
    - Iniciar sesión con Microsoft
    - Iniciar sesión con Apple
    """

    print("Buscando botón azul de iniciar sesión...")

    # Buscar todos los botones de la página
    botones = page.locator("button")
    cantidad = botones.count()

    print(f"Botones encontrados: {cantidad}")

    for i in range(cantidad):
        boton = botones.nth(i)

        try:
            texto = boton.inner_text().strip()
            visible = boton.is_visible()

            print(f"Botón #{i}: '{texto}' | visible: {visible}")

            # Clic SOLO si el texto es exactamente Iniciar sesión
            if visible and texto == "Iniciar sesión":
                boton.click()
                print("Clic en botón Iniciar sesión realizado.")
                return

        except Exception:
            pass

    # Plan B: por si LinkedIn no lo detecta como button normal
    print("Intentando clic por texto exacto...")

    elementos_texto = page.get_by_text("Iniciar sesión", exact=True)
    cantidad_texto = elementos_texto.count()

    print(f"Elementos con texto exacto encontrados: {cantidad_texto}")

    for i in range(cantidad_texto):
        elemento = elementos_texto.nth(i)

        try:
            texto = elemento.inner_text().strip()
            visible = elemento.is_visible()

            print(f"Elemento texto #{i}: '{texto}' | visible: {visible}")

            if visible:
                elemento.click()
                print("Clic en Iniciar sesión realizado por texto exacto.")
                return

        except Exception:
            pass

    raise Exception("No se encontró el botón final de Iniciar sesión")


def hacer_visible_ventana_chromium(page):
    """
    Fuerza la ventana de Chromium de Playwright a estar visible.

    En algunos escritorios Linux/Ubuntu la ventana existe, pero queda detras de
    otra aplicacion o no se muestra claramente al usuario. Este helper usa tres
    mecanismos complementarios:
    - page.bring_to_front(), que pide foco desde Playwright;
    - CDP Browser.setWindowBounds(), que mueve y maximiza la ventana real;
    - set_viewport_size(), que mantiene una superficie amplia para capturas y
      para que LinkedIn muestre formularios completos.
    """
    try:
        page.bring_to_front()
    except Exception as exc:
        print(f"Aviso: no se pudo traer Chromium al frente con Playwright: {exc}")

    try:
        sesion = page.context.new_cdp_session(page)
        ventana = sesion.send("Browser.getWindowForTarget")
        window_id = ventana["windowId"]
        sesion.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "windowState": "normal",
                    "left": 60,
                    "top": 40,
                    "width": 1440,
                    "height": 920,
                },
            },
        )
        sesion.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {"windowState": "maximized"},
            },
        )
        print("Ventana de Chromium maximizada para ver LinkedIn.")
    except Exception as exc:
        print(f"Aviso: no se pudo maximizar Chromium con CDP: {exc}")

    try:
        page.set_viewport_size({"width": 1366, "height": 820})
    except Exception as exc:
        print(f"Aviso: no se pudo ajustar el viewport: {exc}")


def intentar_click_confirmacion_codigo(page):
    textos_boton = (
        "Enviar",
        "Verificar",
        "Continuar",
        "Submit",
        "Verify",
        "Continue",
        "Siguiente",
    )

    for texto in textos_boton:
        try:
            boton = page.get_by_role("button", name=re.compile(texto, re.IGNORECASE))
            if boton.count() and boton.first.is_visible():
                boton.first.click()
                return True
        except Exception:
            pass

    try:
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def ingresar_codigo_verificacion(page, codigo):
    """
    Intenta colocar en LinkedIn el codigo que el usuario escribio en la interfaz.

    El codigo no se imprime ni se guarda en archivos. Solo se usa para llenar el
    campo visible de verificacion y continuar el login.
    """
    codigo = str(codigo or "").strip()
    if not codigo:
        print("No se recibio codigo de verificacion.")
        return False

    hacer_visible_ventana_chromium(page)

    selectores = [
        "input[autocomplete='one-time-code']",
        "input[name='pin']",
        "input[name='challengeAnswer']",
        "input[id*='verification']",
        "input[id*='challenge']",
        "input[id*='pin']",
        "input[type='tel']",
        "input[type='number']",
        "input[type='text']",
    ]

    for selector in selectores:
        try:
            entradas = page.locator(selector)
            for indice in range(entradas.count()):
                entrada = entradas.nth(indice)
                if not entrada.is_visible() or not entrada.is_enabled():
                    continue

                entrada.click()
                try:
                    entrada.fill(codigo)
                except Exception:
                    entrada.press("Control+A")
                    entrada.type(codigo, delay=80)

                intentar_click_confirmacion_codigo(page)
                print("Codigo de verificacion enviado a LinkedIn.")
                return True
        except Exception:
            continue

    try:
        page.keyboard.type(codigo, delay=80)
        intentar_click_confirmacion_codigo(page)
        print("Codigo de verificacion enviado por teclado a LinkedIn.")
        return True
    except Exception as exc:
        print(f"No se pudo enviar el codigo de verificacion: {exc}")
        return False


def esperar_confirmacion_manual(page):
    """
    Espera instrucciones desde la interfaz o consola.

    - ENTER vacio: indica que la sesion ya esta lista y empieza busquedas.
    - CODIGO:123456: intenta escribir ese codigo en la pagina de LinkedIn y
      sigue esperando hasta que el usuario envie ENTER.
    """
    while True:
        texto = input(
            "Cuando la sesión esté lista, presiona ENTER para iniciar las búsquedas..."
        ).strip()

        if not texto:
            return

        if texto.upper().startswith("CODIGO:"):
            ingresar_codigo_verificacion(page, texto.split(":", 1)[1])
            continue

        print("Comando no reconocido. Usa CODIGO:123456 o ENTER para continuar.")


# ----------------------------------------------
# Bot principal LinkedIn
# ----------------------------------------------
def main():
    url = "https://www.linkedin.com/login"

    configuracion = preparar_rutas_ejecucion(cargar_configuracion())
    usuario, contrasena = cargar_credenciales()

    print("Credenciales cargadas correctamente.")
    print("Usuario: ********")
    print("Contraseña: ********")
    print(f"Fecha de ejecución: {configuracion['fecha_ejecucion_archivo']}")
    print(f"Carpeta de ejecución: {RUTA_EJECUCION}")
    print(
        "Rango de búsqueda: "
        f"{configuracion['fecha_inicio'].isoformat()} a "
        f"{configuracion['fecha_fin'].isoformat()}"
    )

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(RUTA_PERFIL_CHROMIUM),
            headless=False,
            slow_mo=300,
            no_viewport=True,
            args=[
                "--start-maximized",
                "--window-position=60,40",
                "--window-size=1440,920",
            ],
        )

        page = context.pages[0] if context.pages else context.new_page()
        hacer_visible_ventana_chromium(page)

        try:
            # ----------------------------------------------
            # Abrir LinkedIn
            # ----------------------------------------------
            print("Abriendo LinkedIn...")
            navegar_linkedin_con_reintentos(
                page,
                url,
                "pagina inicial de LinkedIn",
                fragmento_esperado="linkedin.com",
            )
            hacer_visible_ventana_chromium(page)
            time.sleep(5)

            preparar_sesion_linkedin(page, usuario, contrasena)

            publicaciones, conteo = ejecutar_busquedas_linkedin(page, configuracion)

            print("Recolección finalizada.")
            print(f"Total de publicaciones únicas: {len(publicaciones)}")
            print("Conteo por banco:")

            for banco, total in conteo.items():
                print(f"- {banco}: {total}")

            print("El navegador quedará abierto.")
            input("Presiona ENTER en esta consola cuando quieras cerrar el navegador...")

        except PlaywrightTimeoutError as e:
            print("Error: una navegacion, campo o boton supero el tiempo esperado.")
            print("Detalle del error:")
            print(e)
            print("El navegador quedará abierto para revisar qué pantalla apareció.")
            input("Presiona ENTER para cerrar el navegador...")
            raise

        except Exception as e:
            print("Ocurrió un error inesperado:")
            print(e)
            print("El navegador quedará abierto para revisar qué pantalla apareció.")
            input("Presiona ENTER para cerrar el navegador...")
            raise

        finally:
            context.close()


# ----------------------------------------------
# Ejecutar bot
# ----------------------------------------------
if __name__ == "__main__":
    main()

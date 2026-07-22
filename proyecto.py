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
  descartadas, interacciones y ranking.
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
from collections import Counter
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
RUTA_METADATA = RUTA_RESULTADOS / "metadata.json"
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

DOLOR_CLIENTE_CATEGORIAS = {
    "falsificacion": [
        ("falsificacion", 3),
        ("falsificaciones", 3),
        ("falsificaron", 3),
        ("falsificaron mi firma", 4),
        ("firma falsa", 4),
        ("documento falso", 4),
        ("documentos falsos", 4),
        ("cedula falsa", 4),
        ("suplantacion", 3),
        ("suplantaron", 3),
        ("suplantaron mi identidad", 4),
        ("mi nombre", 2),
        ("a mi nombre", 3),
        ("credito a mi nombre", 4),
        ("credito a tu nombre", 4),
        ("credito no solicitado", 4),
        ("credito nunca fue solicitado", 4),
        ("no solicite", 3),
        ("nunca solicite", 3),
        ("productos fraudulentos", 3),
    ],
    "estafa": [
        ("estafa", 3),
        ("estafas", 3),
        ("me estafaron", 4),
        ("nos estafaron", 4),
        ("estafaron", 3),
        ("estafador", 3),
        ("estafadores", 3),
        ("fraude", 1),
        ("fraudulento", 2),
        ("fraudulenta", 2),
        ("engano", 3),
        ("enganaron", 3),
        ("me enganaron", 4),
        ("pague y no recibi", 4),
        ("transferi", 2),
        ("transferencia fraudulenta", 4),
        ("qr falso", 3),
        ("cuenta falsa", 3),
        ("llamada fraudulenta", 3),
        ("whatsapp falso", 3),
        ("correo falso", 3),
        ("correos falsos", 3),
        ("phishing", 3),
        ("vishing", 3),
        ("smishing", 3),
    ],
    "robo_datos": [
        ("robo de datos", 4),
        ("robaron mis datos", 4),
        ("me robaron los datos", 4),
        ("robaron mis datos personales", 5),
        ("datos personales", 3),
        ("mis datos", 2),
        ("informacion personal", 3),
        ("hackearon", 4),
        ("me hackearon", 5),
        ("hackearon mi cuenta", 5),
        ("cuenta hackeada", 5),
        ("accedieron a mi cuenta", 5),
        ("acceso no autorizado", 4),
        ("clave principal", 3),
        ("clave dinamica", 3),
        ("contrasena", 3),
        ("codigo de seguridad", 3),
        ("codigos de seguridad", 3),
        ("codigo otp", 4),
        ("otp", 3),
        ("token", 2),
        ("robaron mi clave", 5),
        ("robaron mi contrasena", 5),
    ],
    "tarjeta": [
        ("tarjeta", 2),
        ("tarjetas", 2),
        ("mi tarjeta", 3),
        ("mis tarjetas", 3),
        ("tarjeta de credito", 4),
        ("tarjeta credito", 4),
        ("tarjeta de debito", 4),
        ("tarjeta debito", 4),
        ("cvv", 4),
        ("clonaron", 3),
        ("clonaron mi tarjeta", 5),
        ("clonacion", 3),
        ("compra no reconocida", 5),
        ("compras no reconocidas", 5),
        ("compra que no realice", 5),
        ("compra que no hice", 5),
        ("compra que no reconozco", 5),
        ("no realice la compra", 5),
        ("cargo no reconocido", 5),
        ("cargos no reconocidos", 5),
        ("transaccion no reconocida", 4),
        ("transaccion no autorizada", 4),
        ("movimiento no reconocido", 4),
        ("movimiento no autorizado", 4),
        ("avance", 2),
        ("cajero", 2),
        ("retiro no reconocido", 4),
        ("retiro no autorizado", 4),
    ],
    "transaccion_no_autorizada": [
        ("transaccion no autorizada", 5),
        ("transacciones no autorizadas", 5),
        ("operacion no autorizada", 5),
        ("operaciones no autorizadas", 5),
        ("movimiento no autorizado", 5),
        ("movimientos no autorizados", 5),
        ("transferencia no autorizada", 5),
        ("transferencias no autorizadas", 5),
        ("transferencias sin autorizacion", 5),
        ("sin haber autorizado", 4),
        ("sin autorizacion", 3),
        ("sin mi autorizacion", 4),
        ("sin mi previa autorizacion", 5),
        ("jamas autorizo", 4),
        ("nunca autorizo", 4),
        ("no autorice", 4),
        ("no autorizado", 4),
        ("no autorizada", 4),
        ("transferencias fueron generadas", 4),
        ("generaron transacciones", 4),
        ("hicieron un pago", 3),
        ("pago a pse", 3),
        ("telefono robado", 4),
        ("celular robado", 4),
        ("telefono hurtado", 4),
        ("dinero hurtado", 4),
        ("dinero reversado", 3),
        ("dinero desaparecido", 4),
        ("desaparecio dinero", 4),
        ("se me desaparecio dinero", 5),
        ("no fue devuelta", 4),
        ("nunca fue devuelta", 4),
        ("saldo en cero", 4),
        ("reajustado el canje", 4),
        ("canje", 2),
    ],
    "contacto_no_oficial": [
        ("suplantador", 5),
        ("asesor falso", 5),
        ("falso asesor", 5),
        ("mensaje de un asesor", 4),
        ("chat no empresarial", 5),
        ("chat no oficial", 5),
        ("canal no oficial", 5),
        ("sin verificacion", 4),
        ("sin validacion", 4),
        ("documento de identidad", 4),
        ("dato sensible", 4),
        ("datos sensibles", 4),
        ("subir documento", 4),
        ("solicitaba subir documento", 5),
        ("abrir una cuenta", 3),
        ("cuenta de ahorro empresarial", 3),
        ("requerimientos se hacen presencial", 3),
    ],
}

DOLOR_CLIENTE_ETIQUETAS = {
    "falsificacion": "Falsificacion",
    "estafa": "Estafa",
    "robo_datos": "Robo de datos",
    "tarjeta": "Fraude con tarjeta",
    "transaccion_no_autorizada": "Transaccion no autorizada",
    "contacto_no_oficial": "Contacto no oficial",
    "queja_bancaria_general": "Queja bancaria general",
    "servicio_tramite_bancario": "Servicio o tramite bancario",
    "sin_clasificar": "Casos por revisar",
    "sin_publicaciones": "Sin publicaciones",
}

SUBMODALIDAD_CLIENTE_CATEGORIAS = {
    "compra_no_reconocida_tarjeta": [
        ("compra no reconocida", 5),
        ("compras no reconocidas", 5),
        ("compra que no realice", 5),
        ("compra que no hice", 5),
        ("compra que no reconozco", 5),
        ("no realice la compra", 5),
        ("cargo no reconocido", 5),
        ("cargos no reconocidos", 5),
        ("tarjeta de credito", 2),
        ("tarjeta de debito", 2),
    ],
    "clonacion_tarjeta": [
        ("clonaron mi tarjeta", 5),
        ("clonaron", 4),
        ("clonacion", 4),
        ("cvv", 3),
    ],
    "retiro_cajero_no_reconocido": [
        ("retiro no reconocido", 5),
        ("retiro no autorizado", 5),
        ("cajero", 3),
        ("cajeros", 3),
    ],
    "uso_fraudulento_tarjeta": [
        ("tarjeta", 2),
        ("tarjetas", 2),
        ("mi tarjeta", 3),
        ("mis tarjetas", 3),
        ("tarjeta de credito", 4),
        ("tarjeta credito", 4),
        ("tarjeta de debito", 4),
        ("tarjeta debito", 4),
    ],
    "credito_no_solicitado": [
        ("credito no solicitado", 5),
        ("credito nunca fue solicitado", 5),
        ("credito a mi nombre", 5),
        ("credito a tu nombre", 5),
        ("sacaron un credito", 5),
        ("no solicite", 4),
        ("nunca solicite", 4),
    ],
    "falsificacion_documental": [
        ("falsificaron mi firma", 5),
        ("firma falsa", 5),
        ("documento falso", 5),
        ("documentos falsos", 5),
        ("cedula falsa", 5),
        ("falsificaron", 4),
    ],
    "suplantacion_identidad": [
        ("suplantaron mi identidad", 5),
        ("suplantacion", 4),
        ("suplantaron", 4),
        ("a mi nombre", 3),
        ("mi nombre", 2),
        ("productos fraudulentos", 3),
    ],
    "phishing_correo_enlace": [
        ("phishing", 5),
        ("correo falso", 4),
        ("correos falsos", 4),
        ("correo sospechoso", 4),
        ("correos sospechosos", 4),
        ("enlace falso", 8),
        ("link falso", 4),
        ("fraude digital", 5),
    ],
    "whatsapp_llamada_falsa": [
        ("whatsapp falso", 5),
        ("llamada fraudulenta", 5),
        ("vishing", 4),
        ("smishing", 4),
    ],
    "qr_o_cuenta_falsa": [
        ("qr falso", 5),
        ("cuenta falsa", 5),
    ],
    "robo_credenciales_otp": [
        ("codigo otp", 5),
        ("otp", 4),
        ("clave dinamica", 5),
        ("clave principal", 4),
        ("codigo de seguridad", 4),
        ("codigos de seguridad", 4),
        ("token", 3),
        ("contrasena", 3),
        ("robaron mi clave", 5),
        ("robaron mi contrasena", 5),
    ],
    "acceso_no_autorizado_cuenta": [
        ("hackearon mi cuenta", 5),
        ("cuenta hackeada", 5),
        ("accedieron a mi cuenta", 5),
        ("acceso no autorizado", 5),
        ("vulneracion de seguridad de mi cuenta", 5),
        ("vulneracion de seguridad", 4),
        ("ciberseguridad", 3),
        ("me hackearon", 4),
        ("hackearon", 4),
    ],
    "debito_sin_consentimiento": [
        ("cobros ilegales", 5),
        ("debitado sin mi consentimiento", 5),
        ("debitados sin mi consentimiento", 5),
        ("dineros debitados", 4),
        ("debitado de mi cuenta", 4),
        ("debito no autorizado", 5),
        ("debitos no autorizados", 5),
    ],
    "transacciones_desconocidas_autenticacion": [
        ("transacciones desconocidas", 5),
        ("transaccion desconocida", 5),
        ("fallas en los mecanismos de autenticacion", 5),
        ("mecanismos de autenticacion", 4),
        ("consumidor financiero", 2),
        ("usuarios del sistema financiero", 2),
    ],
    "dinero_desaparecido_saldo_no_reintegrado": [
        ("dinero desaparecido", 5),
        ("desaparecio dinero", 5),
        ("se me desaparecio dinero", 6),
        ("dinero de la cuenta", 4),
        ("no fue devuelta", 5),
        ("nunca fue devuelta", 5),
        ("saldo en cero", 5),
        ("reajustado el canje", 5),
        ("canje", 3),
    ],
    "demora_tramite_credito_leasing": [
        ("leasing habitacional", 6),
        ("solicitud de credito de vivienda", 6),
        ("credito de vivienda", 5),
        ("remodelacion", 4),
        ("falta de respuesta", 5),
        ("agotado todos los canales", 5),
        ("agote todos los canales", 5),
        ("tramite con una solicitud", 4),
        ("meses en tramite", 4),
    ],
    "transferencia_no_autorizada": [
        ("transferencia no autorizada", 5),
        ("transferencias no autorizadas", 5),
        ("transferencias sin autorizacion", 5),
        ("transaccion no autorizada", 4),
        ("transacciones no autorizadas", 4),
        ("operaciones no autorizadas", 4),
        ("sin haber autorizado", 4),
        ("jamas autorizo", 4),
        ("nunca autorizo", 4),
        ("no autorice", 4),
        ("sin mi autorizacion", 4),
        ("sin mi previa autorizacion", 5),
        ("transferencias fueron generadas", 4),
        ("generaron transacciones", 4),
    ],
    "pago_pse_no_reconocido": [
        ("pago a pse", 5),
        ("pago pse", 5),
        ("hicieron un pago", 4),
        ("pse", 3),
    ],
    "operacion_por_celular_robado": [
        ("telefono robado", 5),
        ("celular robado", 5),
        ("telefono hurtado", 5),
        ("telefono movil", 3),
        ("hurto con arma", 4),
        ("dinero hurtado", 4),
        ("dinero reversado", 3),
    ],
    "pago_qr_comercio_falso": [
        ("pagos por qr", 5),
        ("pago por qr", 5),
        ("codigo qr", 4),
        ("punto de venta", 3),
        ("latam airlines", 4),
        ("no recibe pagos por qr", 5),
        ("dejaron de respondernos", 4),
    ],
    "asesor_falso_chat_no_oficial": [
        ("suplantador", 5),
        ("asesor falso", 5),
        ("falso asesor", 5),
        ("mensaje de un asesor", 4),
        ("chat no empresarial", 5),
        ("chat no oficial", 5),
        ("canal no oficial", 5),
        ("sin verificacion", 4),
    ],
    "solicitud_documentos_canal_no_oficial": [
        ("documento de identidad", 5),
        ("dato sensible", 5),
        ("datos sensibles", 5),
        ("subir documento", 4),
        ("solicitaba subir documento", 5),
        ("cuenta de ahorro empresarial", 3),
        ("requerimientos se hacen presencial", 3),
    ],
    "proceso_juridico_reintegro": [
        ("sentencia favorable", 5),
        ("sentencia anticipada", 5),
        ("declaratoria de responsabilidad", 4),
        ("responsabilidad contractual", 4),
        ("reintegro total", 5),
        ("reintegro de", 4),
        ("accion de proteccion", 5),
        ("proteccion al consumidor", 4),
        ("superintendencia financiera", 3),
        ("delegatura", 3),
    ],
    "queja_bancaria_general": [
        ("millones de quejas", 5),
        ("quejas relacionadas", 4),
        ("atencion y operacion bancaria", 4),
        ("operacion bancaria", 3),
        ("record historico de quejas", 5),
        ("malestar", 2),
    ],
    "estafa_por_transferencia_o_pago": [
        ("me estafaron", 5),
        ("nos estafaron", 5),
        ("estafaron", 4),
        ("pague y no recibi", 5),
        ("transferi", 3),
        ("transferencia fraudulenta", 4),
    ],
    "estafa_canal_no_identificado": [
        ("estafa", 3),
        ("estafas", 3),
        ("estafador", 3),
        ("estafadores", 3),
        ("fraude", 1),
        ("fraudulento", 2),
        ("fraudulenta", 2),
        ("victima", 2),
        ("victimas", 2),
    ],
}

SUBMODALIDAD_CLIENTE_ETIQUETAS = {
    "compra_no_reconocida_tarjeta": "Compra no reconocida con tarjeta",
    "clonacion_tarjeta": "Clonacion de tarjeta",
    "retiro_cajero_no_reconocido": "Retiro en cajero no reconocido",
    "uso_fraudulento_tarjeta": "Uso fraudulento de tarjeta",
    "credito_no_solicitado": "Credito no solicitado",
    "falsificacion_documental": "Falsificacion documental",
    "suplantacion_identidad": "Suplantacion de identidad",
    "phishing_correo_enlace": "Phishing, correo o enlace falso",
    "whatsapp_llamada_falsa": "WhatsApp o llamada falsa",
    "qr_o_cuenta_falsa": "QR o cuenta falsa",
    "robo_credenciales_otp": "Robo de credenciales u OTP",
    "acceso_no_autorizado_cuenta": "Acceso no autorizado a cuenta",
    "debito_sin_consentimiento": "Debito sin consentimiento",
    "transacciones_desconocidas_autenticacion": "Transacciones desconocidas por autenticacion",
    "dinero_desaparecido_saldo_no_reintegrado": "Dinero desaparecido o saldo no reintegrado",
    "demora_tramite_credito_leasing": "Demora o falta de respuesta en credito/leasing",
    "transferencia_no_autorizada": "Transferencia no autorizada",
    "pago_pse_no_reconocido": "Pago PSE no reconocido",
    "operacion_por_celular_robado": "Operacion por celular robado",
    "pago_qr_comercio_falso": "Pago QR a comercio falso",
    "asesor_falso_chat_no_oficial": "Asesor falso o chat no oficial",
    "solicitud_documentos_canal_no_oficial": "Solicitud de documentos por canal no oficial",
    "proceso_juridico_reintegro": "Proceso juridico o reintegro por fraude",
    "queja_bancaria_general": "Queja bancaria general",
    "estafa_por_transferencia_o_pago": "Estafa por transferencia o pago",
    "estafa_canal_no_identificado": "Estafa reportada sin canal identificado",
    "caso_fraude_por_clasificar": "Casos por revisar",
}

SUBMODALIDAD_GRUPO_DOLOR = {
    "compra_no_reconocida_tarjeta": "tarjeta",
    "clonacion_tarjeta": "tarjeta",
    "retiro_cajero_no_reconocido": "tarjeta",
    "uso_fraudulento_tarjeta": "tarjeta",
    "credito_no_solicitado": "falsificacion",
    "falsificacion_documental": "falsificacion",
    "suplantacion_identidad": "falsificacion",
    "phishing_correo_enlace": "estafa",
    "whatsapp_llamada_falsa": "estafa",
    "qr_o_cuenta_falsa": "estafa",
    "robo_credenciales_otp": "robo_datos",
    "acceso_no_autorizado_cuenta": "robo_datos",
    "debito_sin_consentimiento": "transaccion_no_autorizada",
    "transacciones_desconocidas_autenticacion": "transaccion_no_autorizada",
    "dinero_desaparecido_saldo_no_reintegrado": "transaccion_no_autorizada",
    "transferencia_no_autorizada": "transaccion_no_autorizada",
    "pago_pse_no_reconocido": "transaccion_no_autorizada",
    "operacion_por_celular_robado": "transaccion_no_autorizada",
    "pago_qr_comercio_falso": "estafa",
    "asesor_falso_chat_no_oficial": "contacto_no_oficial",
    "solicitud_documentos_canal_no_oficial": "contacto_no_oficial",
    "proceso_juridico_reintegro": "queja_bancaria_general",
    "queja_bancaria_general": "queja_bancaria_general",
    "demora_tramite_credito_leasing": "servicio_tramite_bancario",
}

MODALIDAD_FALLBACK_ETIQUETAS = {
    "falsificacion": "Posible falsificacion o suplantacion documental",
    "estafa": "Estafa reportada sin canal identificado",
    "robo_datos": "Compromiso de datos o credenciales",
    "tarjeta": "Uso fraudulento de tarjeta",
    "transaccion_no_autorizada": "Operacion bancaria no autorizada",
    "contacto_no_oficial": "Contacto por canal no oficial",
}

ETIQUETAS_GRAFICAS_BANCOS = {
    "Banco Popular Colombia": "Popular",
    "Banco Davivienda": "Davivienda",
    "Bancolombia": "Bancolombia",
    "Banco de Bogotá": "Bogota",
    "BBVA Colombia": "BBVA",
    "Banco Agrario de Colombia": "Agrario",
    "Scotiabank Colpatria": "Scotiabank",
    "Banco de Occidente": "Occidente",
    "Banco AV Villas": "AV Villas",
    "Banco Caja Social": "Caja Social",
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


def clasificar_por_diccionario(texto_normalizado, categorias):
    resultados = []

    for categoria, terminos_pesos in categorias.items():
        puntaje = 0
        encontrados = []

        for termino, peso in terminos_pesos:
            termino_normalizado = normalizar_texto_busqueda(termino)

            if termino_normalizado and f" {termino_normalizado} " in texto_normalizado:
                puntaje += peso
                encontrados.append(termino)

        if puntaje:
            resultados.append(
                {
                    "categoria": categoria,
                    "puntaje": puntaje,
                    "terminos": encontrados,
                }
            )

    resultados.sort(key=lambda item: item["puntaje"], reverse=True)

    return resultados


def modalidad_especifica_desde_resultados(resultados_submodalidad, categoria_general):
    if resultados_submodalidad:
        return SUBMODALIDAD_CLIENTE_ETIQUETAS.get(
            resultados_submodalidad[0]["categoria"],
            resultados_submodalidad[0]["categoria"],
        )

    if categoria_general and categoria_general != "sin_clasificar":
        return MODALIDAD_FALLBACK_ETIQUETAS.get(
            categoria_general,
            DOLOR_CLIENTE_ETIQUETAS.get(categoria_general, categoria_general),
        )

    return SUBMODALIDAD_CLIENTE_ETIQUETAS["caso_fraude_por_clasificar"]


def clasificar_dolor_cliente(texto):
    texto_normalizado = f" {normalizar_texto_busqueda(texto)} "
    resultados = clasificar_por_diccionario(
        texto_normalizado,
        DOLOR_CLIENTE_CATEGORIAS,
    )
    resultados_submodalidad = clasificar_por_diccionario(
        texto_normalizado,
        SUBMODALIDAD_CLIENTE_CATEGORIAS,
    )

    if not resultados and resultados_submodalidad:
        principal_submodalidad = resultados_submodalidad[0]
        grupo_inferido = SUBMODALIDAD_GRUPO_DOLOR.get(
            principal_submodalidad["categoria"],
            "sin_clasificar",
        )
        terminos_detectados = combinar_terminos(
            *[resultado["terminos"] for resultado in resultados_submodalidad],
        )
        confianza = min(0.9, 0.45 + principal_submodalidad["puntaje"] * 0.08)

        return {
            "dolor_cliente": grupo_inferido,
            "dolor_cliente_secundario": "",
            "modalidad_especifica": modalidad_especifica_desde_resultados(
                resultados_submodalidad,
                grupo_inferido,
            ),
            "confianza_dolor": round(confianza, 2),
            "palabras_dolor_detectadas": ", ".join(terminos_detectados),
        }

    if not resultados:
        return {
            "dolor_cliente": "sin_clasificar",
            "dolor_cliente_secundario": "",
            "modalidad_especifica": modalidad_especifica_desde_resultados(
                resultados_submodalidad,
                "sin_clasificar",
            ),
            "confianza_dolor": 0,
            "palabras_dolor_detectadas": "",
        }

    principal = resultados[0]
    secundario = ""

    if len(resultados) > 1:
        candidato = resultados[1]
        if candidato["puntaje"] >= 2 and candidato["puntaje"] >= principal["puntaje"] * 0.45:
            secundario = candidato["categoria"]

    puntaje_secundario = resultados[1]["puntaje"] if len(resultados) > 1 else 0
    margen = principal["puntaje"] - puntaje_secundario
    confianza = min(0.95, 0.45 + principal["puntaje"] * 0.08 + margen * 0.04)
    terminos_detectados = combinar_terminos(
        *[resultado["terminos"] for resultado in resultados],
        *[resultado["terminos"] for resultado in resultados_submodalidad],
    )

    return {
        "dolor_cliente": principal["categoria"],
        "dolor_cliente_secundario": secundario,
        "modalidad_especifica": modalidad_especifica_desde_resultados(
            resultados_submodalidad,
            principal["categoria"],
        ),
        "confianza_dolor": round(confianza, 2),
        "palabras_dolor_detectadas": ", ".join(terminos_detectados),
    }


def agregar_dolor_cliente_a_filas(filas):
    for fila in filas:
        clasificacion = clasificar_dolor_cliente(fila.get("texto", ""))
        modalidad_actual = (fila.get("dolor_cliente") or "").strip()
        especifica_actual = (fila.get("modalidad_especifica") or "").strip()
        modalidades_genericas = set(DOLOR_CLIENTE_ETIQUETAS.values())

        if (
            not modalidad_actual
            or modalidad_actual == "sin_clasificar"
            or not especifica_actual
            or especifica_actual in modalidades_genericas
        ):
            fila.update(clasificacion)
            continue

        for clave, valor in clasificacion.items():
            if not fila.get(clave):
                fila[clave] = valor


def marcar_descartadas_sin_modalidad(filas):
    for fila in filas:
        fila["dolor_cliente"] = "descartada"
        fila["dolor_cliente_secundario"] = ""
        fila["modalidad_especifica"] = "No aplica - publicacion descartada"
        fila["confianza_dolor"] = ""
        fila["palabras_dolor_detectadas"] = ""


def campos_dolor_cliente():
    return [
        "grupo_modalidad",
        "modalidad_reportada",
        "publicaciones",
        "participacion_porcentaje",
        "bancos_impactados",
        "palabras_detectadas",
    ]


def filas_resumen_dolor_cliente(publicaciones):
    total = len(publicaciones)

    if not publicaciones:
        return [
            {
                "grupo_modalidad": DOLOR_CLIENTE_ETIQUETAS["sin_publicaciones"],
                "modalidad_reportada": DOLOR_CLIENTE_ETIQUETAS["sin_publicaciones"],
                "publicaciones": 0,
                "participacion_porcentaje": 0,
                "bancos_impactados": "",
                "palabras_detectadas": "",
            }
        ]

    acumulados = {}

    for publicacion in publicaciones:
        clasificacion = clasificar_dolor_cliente(publicacion.get("texto", ""))
        grupo = (
            publicacion.get("dolor_cliente")
            or clasificacion["dolor_cliente"]
            or "sin_clasificar"
        )
        modalidad = (
            publicacion.get("modalidad_especifica")
            or clasificacion["modalidad_especifica"]
        )
        palabras = (
            publicacion.get("palabras_dolor_detectadas")
            or clasificacion["palabras_dolor_detectadas"]
        )

        if modalidad not in acumulados:
            acumulados[modalidad] = {
                "grupo": grupo,
                "modalidad": modalidad,
                "publicaciones": 0,
                "palabras": Counter(),
                "bancos": Counter(),
            }

        acumulados[modalidad]["publicaciones"] += 1
        acumulados[modalidad]["bancos"][publicacion.get("banco") or "Sin banco"] += 1

        for palabra in palabras.split(","):
            palabra = limpiar_linea(palabra)
            if palabra:
                acumulados[modalidad]["palabras"][palabra] += 1

    filas = []

    for acumulado in acumulados.values():
        publicaciones_categoria = acumulado["publicaciones"]
        palabras_detectadas = ", ".join(
            palabra
            for palabra, _ in acumulado["palabras"].most_common(8)
        )
        bancos_impactados = ", ".join(
            f"{banco} ({total_banco})"
            for banco, total_banco in acumulado["bancos"].most_common()
        )
        filas.append(
            {
                "grupo_modalidad": DOLOR_CLIENTE_ETIQUETAS.get(
                    acumulado["grupo"],
                    acumulado["grupo"],
                ),
                "modalidad_reportada": acumulado["modalidad"],
                "publicaciones": publicaciones_categoria,
                "participacion_porcentaje": round(
                    (publicaciones_categoria / total) * 100,
                    2,
                ),
                "bancos_impactados": bancos_impactados,
                "palabras_detectadas": palabras_detectadas,
            }
        )

    return sorted(
        filas,
        key=lambda fila: (-fila["publicaciones"], fila["modalidad_reportada"]),
    )


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


def slug_plataforma_ejecucion(configuracion):
    """Devuelve el identificador seguro de red usado en carpetas de resultados."""
    plataforma = str(configuracion.get("plataforma", "linkedin")).strip().lower()
    permitidas = {"linkedin", "instagram", "facebook"}
    return plataforma if plataforma in permitidas else "linkedin"


def preparar_rutas_ejecucion(configuracion):
    global RUTA_EJECUCION
    global RUTA_PUBLICACIONES
    global RUTA_DESCARTADAS
    global RUTA_CONTEO_BANCOS
    global RUTA_COMPARATIVO_POPULAR
    global RUTA_TIEMPOS_EJECUCION
    global RUTA_REPORTE_EXCEL
    global RUTA_CAPTURAS
    global RUTA_METADATA

    fecha_ejecucion = datetime.now()
    fecha_archivo = formatear_fecha_ejecucion(fecha_ejecucion)
    marca_ejecucion = fecha_ejecucion.strftime("%d-%m-%Y_%H-%M-%S")
    plataforma_slug = slug_plataforma_ejecucion(configuracion)
    RUTA_RESULTADOS.mkdir(exist_ok=True)

    nombre_ejecucion = f"ejecucion_{plataforma_slug}_{marca_ejecucion}"
    ruta_ejecucion = RUTA_RESULTADOS / nombre_ejecucion
    contador = 2

    while ruta_ejecucion.exists():
        ruta_ejecucion = RUTA_RESULTADOS / f"{nombre_ejecucion}_{contador}"
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
    RUTA_METADATA = ruta_ejecucion / "metadata.json"

    configuracion = configuracion.copy()
    configuracion["fecha_ejecucion"] = fecha_ejecucion
    configuracion["fecha_ejecucion_archivo"] = fecha_archivo
    configuracion["ruta_ejecucion"] = ruta_ejecucion
    escribir_metadata_ejecucion(configuracion)

    return configuracion


def plataforma_visible(plataforma):
    etiquetas = {
        "linkedin": "LinkedIn",
        "instagram": "Instagram",
        "facebook": "Facebook",
    }

    return etiquetas.get(plataforma, plataforma or "Desconocida")


def valor_json_metadata(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Path):
        return valor.name
    if isinstance(valor, list):
        return [valor_json_metadata(item) for item in valor]
    if isinstance(valor, dict):
        return {clave: valor_json_metadata(item) for clave, item in valor.items()}

    return valor


def metadata_desde_configuracion(configuracion):
    plataforma = configuracion.get("plataforma", "linkedin")

    return {
        "version": 1,
        "plataforma": plataforma,
        "plataforma_label": plataforma_visible(plataforma),
        "fecha_inicio": valor_json_metadata(configuracion.get("fecha_inicio")),
        "fecha_fin": valor_json_metadata(configuracion.get("fecha_fin")),
        "rango_fecha": formatear_rango_fecha(configuracion),
        "fecha_ejecucion": valor_json_metadata(configuracion.get("fecha_ejecucion")),
        "fecha_ejecucion_archivo": configuracion.get("fecha_ejecucion_archivo", ""),
        "carpeta": Path(configuracion.get("ruta_ejecucion", RUTA_EJECUCION)).name,
        "bancos_seleccionados": valor_json_metadata(
            configuracion.get("bancos_seleccionados", [])
        ),
        "max_publicaciones_por_busqueda": configuracion.get(
            "max_publicaciones_por_busqueda"
        ),
        "max_publicaciones_por_banco": configuracion.get(
            "max_publicaciones_por_banco"
        ),
        "max_comentarios_por_publicacion": configuracion.get(
            "max_comentarios_por_publicacion"
        ),
        "filtrar_por_fecha": bool(configuracion.get("filtrar_por_fecha", True)),
        "filtrar_por_relevancia": bool(
            configuracion.get("filtrar_por_relevancia", True)
        ),
        "guardar_descartadas": bool(configuracion.get("guardar_descartadas", True)),
    }


def escribir_metadata_ejecucion(configuracion, extras=None):
    metadata = metadata_desde_configuracion(configuracion)

    if RUTA_METADATA.exists():
        try:
            with RUTA_METADATA.open("r", encoding="utf-8") as archivo:
                metadata_guardada = json.load(archivo)
        except (OSError, json.JSONDecodeError):
            metadata_guardada = {}
        metadata_guardada.update(metadata)
        metadata = metadata_guardada

    if extras:
        metadata.update(valor_json_metadata(extras))

    with RUTA_METADATA.open("w", encoding="utf-8") as archivo:
        json.dump(metadata, archivo, indent=2, ensure_ascii=False)
        archivo.write("\n")


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


def extraer_metricas(texto_visible, texto_metricas=""):
    metricas = {
        "reacciones": "",
        "comentarios": "",
        "compartidos": "",
    }
    texto = "\n".join(
        parte for parte in (texto_metricas, texto_visible) if parte
    )
    numero = r"(\d[\d.,]*(?:\s*(?:mil|k))?)"

    patrones = {
        "reacciones": [
            rf"{numero}\s+reacciones?",
            rf"{numero}\s+likes?",
        ],
        "comentarios": [
            rf"{numero}\s+comentarios?",
            rf"{numero}\s+comments?",
        ],
        "compartidos": [
            rf"{numero}\s+(?:veces\s+)?compartid[oa]s?",
            rf"compartid[oa]\s+{numero}\s+veces",
            rf"{numero}\s+reposts?",
            rf"{numero}\s+republicaciones?",
            rf"{numero}\s+shares?",
        ],
    }

    for nombre, patrones_nombre in patrones.items():
        for patron in patrones_nombre:
            coincidencia = re.search(patron, texto or "", flags=re.IGNORECASE)
            if coincidencia:
                metricas[nombre] = limpiar_linea(coincidencia.group(1))
                break

    if not metricas["reacciones"]:
        coincidencia = re.search(
            rf"\by\s+{numero}\s+personas?\s+m[aá]s\b",
            texto or "",
            flags=re.IGNORECASE,
        )
        if coincidencia:
            metricas["reacciones"] = str(convertir_metrica_a_entero(coincidencia.group(1)) + 1)

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
            const limpiar = (valor) => (
                valor || ''
            ).replace(/\\s+/g, ' ').trim();
            const textosMetricas = [];
            const patronMetricas = /reacci|coment|compart|repost|like|comment|share/i;
            const candidatosMetricas = Array.from(
                el.querySelectorAll('[aria-label], [title], button, a, span, li')
            ).slice(0, 220);

            for (const nodo of candidatosMetricas) {
                const valores = [
                    nodo.innerText,
                    nodo.textContent,
                    nodo.getAttribute('aria-label'),
                    nodo.getAttribute('title')
                ].map(limpiar).filter(Boolean);

                for (const valor of valores) {
                    if (patronMetricas.test(valor) && !textosMetricas.includes(valor)) {
                        textosMetricas.push(valor);
                    }
                }
            }

            return {
                texto: (textoEl.innerText || '').trim(),
                autor: autor,
                url_autor: urlAutor,
                url_publicacion: postLink ? postLink.href : '',
                texto_visible: el.innerText || '',
                texto_metricas: textosMetricas.join('\\n')
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
        metricas = extraer_metricas(texto_visible, datos.get("texto_metricas", ""))
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
        "dolor_cliente",
        "dolor_cliente_secundario",
        "modalidad_especifica",
        "confianza_dolor",
        "palabras_dolor_detectadas",
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


def celda_excel_xml(fila, columna, valor, estilo=None):
    referencia = f"{letra_columna_excel(columna)}{fila}"
    atributos = f' r="{referencia}"'

    if estilo is not None:
        atributos += f' s="{estilo}"'

    if es_numero_excel(valor):
        return f"<c{atributos}><v>{valor}</v></c>"

    return (
        f'<c{atributos} t="inlineStr">'
        f'<is><t xml:space="preserve">{limpiar_valor_xml(valor)}</t></is>'
        f"</c>"
    )


def ancho_columna_excel(campo):
    anchos = {
        "banco": 28,
        "etiqueta_grafica": 18,
        "busqueda": 32,
        "autor": 28,
        "texto": 72,
        "url": 42,
        "motivo_relevancia": 36,
        "detalle_error": 48,
        "imagen_publicacion": 44,
        "archivo_imagen": 34,
        "rango_fecha": 24,
        "rango_fecha_inicio": 18,
        "rango_fecha_fin": 18,
        "fecha_recoleccion": 24,
        "fecha_publicacion_estimada": 24,
        "dolor_cliente": 20,
        "dolor_cliente_secundario": 24,
        "modalidad_especifica": 36,
        "confianza_dolor": 18,
        "palabras_dolor_detectadas": 42,
        "participacion_total_porcentaje": 26,
        "diferencia_vs_banco_popular": 28,
        "interacciones_total": 20,
        "ranking_denuncias": 20,
        "denuncias_directas": 20,
        "denuncias_descartadas": 22,
        "modalidad_reportada": 24,
        "participacion_porcentaje": 24,
        "palabras_detectadas": 42,
    }

    return anchos.get(campo, 18)


def etiqueta_grafica_banco(banco):
    return ETIQUETAS_GRAFICAS_BANCOS.get(banco, banco or "Sin banco")


def agregar_etiqueta_grafica_banco(filas):
    return [
        {
            **fila,
            "etiqueta_grafica": etiqueta_grafica_banco(fila.get("banco")),
        }
        for fila in filas
    ]


def hoja_datos_excel_xml(filas, campos):
    filas_excel = [campos]

    for fila in filas:
        filas_excel.append([fila.get(campo, "") for campo in campos])

    ancho = len(campos)
    alto = max(len(filas_excel), 1)
    dimension = f"A1:{letra_columna_excel(ancho)}{alto}"
    columnas = "".join(
        f'<col min="{indice}" max="{indice}" '
        f'width="{ancho_columna_excel(campo)}" customWidth="1"/>'
        for indice, campo in enumerate(campos, start=1)
    )
    filas_xml = []

    for numero_fila, valores in enumerate(filas_excel, start=1):
        if numero_fila == 1:
            estilo = 1
        else:
            estilo = 3 if (numero_fila - 1) % 2 == 0 else 2

        celdas = "".join(
            celda_excel_xml(numero_fila, indice, valor, estilo)
            for indice, valor in enumerate(valores, start=1)
        )
        filas_xml.append(f'<row r="{numero_fila}">{celdas}</row>')

    filtro = f'<autoFilter ref="{dimension}"/>' if len(filas_excel) > 1 else ""

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        f"<cols>{columnas}</cols>"
        f"<sheetData>{''.join(filas_xml)}</sheetData>"
        f"{filtro}"
        "</worksheet>"
    )


def hoja_graficas_excel_xml():
    filas = [
        {"seccion": "Graficas", "descripcion": "Denuncias, modalidad reportada, participacion, ranking y tiempos"},
        {"seccion": "1", "descripcion": "Denuncias directas por banco"},
        {"seccion": "2", "descripcion": "Participacion porcentual por banco"},
        {"seccion": "3", "descripcion": "Ranking de denuncias por banco"},
        {"seccion": "4", "descripcion": "Tiempo de ejecucion por banco"},
        {"seccion": "5", "descripcion": "Modalidad reportada"},
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


def layout_grafica_xml(direccion):
    if direccion == "bar":
        return (
            '<c:layout><c:manualLayout>'
            '<c:layoutTarget val="inner"/>'
            '<c:xMode val="factor"/><c:yMode val="factor"/>'
            '<c:wMode val="factor"/><c:hMode val="factor"/>'
            '<c:x val="0.22"/><c:y val="0.08"/>'
            '<c:w val="0.72"/><c:h val="0.78"/>'
            '</c:manualLayout></c:layout>'
        )

    return (
        '<c:layout><c:manualLayout>'
        '<c:layoutTarget val="inner"/>'
        '<c:xMode val="factor"/><c:yMode val="factor"/>'
        '<c:wMode val="factor"/><c:hMode val="factor"/>'
        '<c:x val="0.07"/><c:y val="0.08"/>'
        '<c:w val="0.88"/><c:h val="0.58"/>'
        '</c:manualLayout></c:layout>'
    )


def texto_eje_categorias_xml():
    return (
        '<c:txPr>'
        '<a:bodyPr rot="-2700000"/><a:lstStyle/>'
        '<a:p><a:pPr><a:defRPr sz="900"/></a:pPr>'
        '<a:endParaRPr lang="es-CO"/></a:p>'
        '</c:txPr>'
    )


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
    direccion="col",
    color="2F80ED",
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

    posicion_categoria = "l" if direccion == "bar" else "b"
    posicion_valor = "b" if direccion == "bar" else "l"

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<c:style val="10"/>'
        '<c:chart>'
        '<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r>'
        f'<a:t>{limpiar_valor_xml(titulo)}</a:t>'
        '</a:r></a:p></c:rich></c:tx><c:overlay val="0"/></c:title>'
        f'<c:plotArea>{layout_grafica_xml(direccion)}'
        f'<c:barChart><c:barDir val="{direccion}"/><c:grouping val="clustered"/>'
        '<c:varyColors val="0"/>'
        '<c:ser><c:idx val="0"/><c:order val="0"/>'
        f'<c:tx><c:v>{limpiar_valor_xml(titulo_serie)}</c:v></c:tx>'
        f'<c:spPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        '<a:ln><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></a:ln></c:spPr>'
        '<c:cat><c:strRef>'
        f'<c:f>{limpiar_valor_xml(formula_categorias)}</c:f>'
        f'{cache_categorias_xml(categorias)}'
        '</c:strRef></c:cat>'
        '<c:val><c:numRef>'
        f'<c:f>{limpiar_valor_xml(formula_valores)}</c:f>'
        f'{cache_numeros_xml(valores)}'
        '</c:numRef></c:val>'
        '</c:ser>'
        '<c:dLbls><c:showLegendKey val="0"/><c:showVal val="1"/>'
        '<c:showCatName val="0"/><c:showSerName val="0"/><c:showPercent val="0"/>'
        '</c:dLbls>'
        f'<c:axId val="{eje_x}"/><c:axId val="{eje_y}"/>'
        '</c:barChart>'
        f'<c:catAx><c:axId val="{eje_x}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
        f'<c:delete val="0"/><c:axPos val="{posicion_categoria}"/>'
        '<c:majorTickMark val="none"/><c:minorTickMark val="none"/>'
        '<c:tickLblPos val="nextTo"/>'
        f'{texto_eje_categorias_xml()}'
        f'<c:crossAx val="{eje_y}"/><c:crosses val="autoZero"/><c:auto val="1"/>'
        '<c:lblAlgn val="ctr"/><c:lblOffset val="100"/><c:noMultiLvlLbl val="1"/>'
        '</c:catAx>'
        f'<c:valAx><c:axId val="{eje_y}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
        f'<c:delete val="0"/><c:axPos val="{posicion_valor}"/><c:majorGridlines/><c:numFmt formatCode="General" sourceLinked="1"/>'
        f'<c:tickLblPos val="nextTo"/><c:crossAx val="{eje_x}"/><c:crosses val="autoZero"/>'
        '</c:valAx>'
        '</c:plotArea>'
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
        ancla_grafica_xml(1, "rId1", 0, 6, 17, 25),
        ancla_grafica_xml(2, "rId2", 0, 27, 17, 46),
        ancla_grafica_xml(3, "rId3", 0, 48, 17, 67),
        ancla_grafica_xml(4, "rId4", 0, 69, 17, 88),
        ancla_grafica_xml(5, "rId5", 0, 90, 17, 109),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"{''.join(anclas)}"
        "</xdr:wsDr>"
    )


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
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF4F7FA"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border/>'
        '<border><left style="thin"><color rgb="FFD8DEE6"/></left>'
        '<right style="thin"><color rgb="FFD8DEE6"/></right>'
        '<top style="thin"><color rgb="FFD8DEE6"/></top>'
        '<bottom style="thin"><color rgb="FFD8DEE6"/></bottom></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="4">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1">'
        '<alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1">'
        '<alignment vertical="top" wrapText="1"/></xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>'
        '</styleSheet>'
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
    campos_dolor = campos_dolor_cliente()
    campos_tiempos = campos_tiempos_ejecucion()
    campos_conteo_excel = ["banco", "etiqueta_grafica", "rango_fecha", "publicaciones"]
    campos_comparativo_excel = ["banco", "etiqueta_grafica"] + campos_comparativo[1:]
    campos_tiempos_excel = (
        ["tipo_tiempo", "banco", "etiqueta_grafica"]
        + [campo for campo in campos_tiempos if campo not in {"tipo_tiempo", "banco"}]
    )
    filas_conteo_excel = agregar_etiqueta_grafica_banco(filas_conteo)
    filas_comparativo_excel = agregar_etiqueta_grafica_banco(filas_comparativo)
    filas_tiempos_excel = agregar_etiqueta_grafica_banco(filas_tiempos)
    filas_dolor_cliente = filas_resumen_dolor_cliente(publicaciones)
    filas_tiempos_banco = [
        fila for fila in filas_tiempos_excel if fila.get("tipo_tiempo") == "busqueda"
    ]

    hojas = [
        ("Publicaciones", hoja_datos_excel_xml(publicaciones, campos_publicacion)),
        ("Descartadas", hoja_datos_excel_xml(descartadas, campos_resultado)),
        ("Conteo por banco", hoja_datos_excel_xml(filas_conteo_excel, campos_conteo_excel)),
        (
            "Comparativo Popular",
            hoja_datos_excel_xml(filas_comparativo_excel, campos_comparativo_excel),
        ),
        (
            "Modalidad reportada",
            hoja_datos_excel_xml(filas_dolor_cliente, campos_dolor),
        ),
        ("Tiempos ejecucion", hoja_datos_excel_xml(filas_tiempos_excel, campos_tiempos_excel)),
        ("Graficas", hoja_graficas_excel_xml()),
    ]

    total_bancos = len(filas_conteo)
    fila_fin_conteo = total_bancos + 1
    fila_fin_comparativo = len(filas_comparativo) + 1
    fila_fin_dolor = len(filas_dolor_cliente) + 1
    fila_fin_tiempos = len(filas_tiempos_banco) + 1
    categorias_conteo = [fila["etiqueta_grafica"] for fila in filas_conteo_excel]
    valores_conteo = [fila["publicaciones"] for fila in filas_conteo]
    categorias_comparativo = [fila["etiqueta_grafica"] for fila in filas_comparativo_excel]
    valores_participacion = [
        fila["participacion_total_porcentaje"] for fila in filas_comparativo
    ]
    valores_ranking = [
        fila["ranking_denuncias"] or 0 for fila in filas_comparativo
    ]
    categorias_dolor = [fila["modalidad_reportada"] for fila in filas_dolor_cliente]
    valores_dolor = [fila["publicaciones"] for fila in filas_dolor_cliente]
    categorias_tiempos = [fila["etiqueta_grafica"] for fila in filas_tiempos_banco]
    valores_tiempos = [fila["duracion_segundos"] for fila in filas_tiempos_banco]
    graficas = [
        crear_grafica_barras_xml(
            "Denuncias directas por banco",
            "Denuncias",
            "Conteo por banco",
            "B",
            "D",
            2,
            fila_fin_conteo,
            categorias_conteo,
            valores_conteo,
            100001,
            100002,
            color="1F7A4D",
        ),
        crear_grafica_barras_xml(
            "Participacion porcentual por banco",
            "Participacion %",
            "Comparativo Popular",
            "B",
            "G",
            2,
            fila_fin_comparativo,
            categorias_comparativo,
            valores_participacion,
            100003,
            100004,
            color="2F80ED",
        ),
        crear_grafica_barras_xml(
            "Ranking de denuncias por banco",
            "Ranking",
            "Comparativo Popular",
            "B",
            "J",
            2,
            fila_fin_comparativo,
            categorias_comparativo,
            valores_ranking,
            100005,
            100006,
            color="8A63D2",
        ),
        crear_grafica_barras_xml(
            "Tiempo de ejecucion por banco",
            "Segundos",
            "Tiempos ejecucion",
            "C",
            "I",
            2,
            fila_fin_tiempos,
            categorias_tiempos,
            valores_tiempos,
            100007,
            100008,
            color="F2994A",
        ),
        crear_grafica_barras_xml(
            "Modalidad reportada",
            "Publicaciones",
            "Modalidad reportada",
            "A",
            "B",
            2,
            fila_fin_dolor,
            categorias_dolor,
            valores_dolor,
            100009,
            100010,
            color="D64545",
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
            estilos_excel_xml(),
        )

        for indice, (_, xml_hoja) in enumerate(hojas, start=1):
            archivo.writestr(f"xl/worksheets/sheet{indice}.xml", xml_hoja)

        archivo.writestr(
            f"xl/worksheets/_rels/sheet{len(hojas)}.xml.rels",
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
        "denuncias_descartadas",
        "participacion_total_porcentaje",
        "diferencia_vs_banco_popular",
        "interacciones_total",
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


def guardar_comparativo_banco_popular(
    publicaciones,
    descartadas,
    conteo,
    rango_fecha,
    bancos=None,
):
    banco_base = "Banco Popular Colombia"
    bancos = bancos or BANCOS_OBJETIVO
    total_general = sum(conteo.values())
    total_base = conteo.get(banco_base, 0) if banco_base in bancos else None
    interacciones_por_banco = {banco: 0 for banco in bancos}
    conteo_descartadas = contar_publicaciones_por_banco(descartadas, bancos)

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
        total_descartadas = conteo_descartadas.get(banco, 0)
        interacciones_total = interacciones_por_banco.get(banco, 0)

        participacion = round((total / total_general) * 100, 2) if total_general else 0
        diferencia = total - total_base if total_base is not None else ""

        filas_comparativo.append(
            {
                "banco": banco,
                "grupo": "Banco Popular" if banco == banco_base else "Otros bancos",
                "rango_fecha": rango_fecha,
                "denuncias_directas": total,
                "denuncias_descartadas": total_descartadas,
                "participacion_total_porcentaje": participacion,
                "diferencia_vs_banco_popular": diferencia,
                "interacciones_total": interacciones_total,
                "ranking_denuncias": ranking.get(banco, ""),
            }
        )

    escribir_csv(RUTA_COMPARATIVO_POPULAR, filas_comparativo, campos)

    return filas_comparativo


def guardar_resultados(publicaciones, descartadas, configuracion, tiempos_ejecucion):
    RUTA_EJECUCION.mkdir(parents=True, exist_ok=True)
    rango_fecha = formatear_rango_fecha(configuracion)
    bancos = configuracion.get("bancos_seleccionados", BANCOS_OBJETIVO)
    guardar_descartadas = configuracion["guardar_descartadas"]
    descartadas_reporte = descartadas if guardar_descartadas else []

    agregar_dolor_cliente_a_filas(publicaciones)
    marcar_descartadas_sin_modalidad(descartadas_reporte)

    campos_publicacion = campos_publicaciones()
    campos = campos_resultados()
    escribir_csv(RUTA_PUBLICACIONES, publicaciones, campos_publicacion)

    if guardar_descartadas:
        escribir_csv(RUTA_DESCARTADAS, descartadas_reporte, campos)

    conteo = contar_publicaciones_por_banco(publicaciones, bancos)
    filas_comparativo = guardar_comparativo_banco_popular(
        publicaciones,
        descartadas_reporte,
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
        descartadas_reporte,
        filas_conteo,
        filas_comparativo,
        tiempos_ejecucion,
    )
    escribir_metadata_ejecucion(
        configuracion,
        {
            "publicaciones": len(publicaciones),
            "descartadas": len(descartadas_reporte),
            "bancos_con_resultados": sum(1 for total in conteo.values() if total > 0),
            "total_busquedas": sum(
                1 for fila in tiempos_ejecucion if fila.get("tipo_tiempo") == "busqueda"
            ),
            "finalizada_en": datetime.now().isoformat(timespec="seconds"),
        },
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

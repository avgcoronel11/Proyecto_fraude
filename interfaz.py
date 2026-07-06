"""
Dashboard local del proyecto de fraude bancario.

Este archivo es el punto de entrada recomendado para ejecutar el proyecto desde
Visual Studio Code o desde una terminal:

    .venv/bin/python interfaz.py

Despues de ejecutarlo, abre en el navegador:

    http://127.0.0.1:8000

Que hace este archivo
---------------------
1. Levanta un servidor HTTP local con ThreadingHTTPServer.
2. Sirve una interfaz web embebida en la constante HTML.
3. Permite editar la configuracion de busqueda:
   - rango de fechas;
   - maximo de publicaciones por consulta;
   - maximo de publicaciones por banco para Instagram/Facebook;
   - maximo de comentarios por publicacion para Instagram/Facebook;
   - filtros de fecha y relevancia;
   - bancos seleccionados.
4. Guarda esa configuracion en configuracion_busqueda.json.
5. Lanza proyecto.py como subproceso cuando el usuario presiona
   "Ejecutar proyecto".
6. Lee la salida del bot en tiempo real y la muestra como log.
7. Permite enviar ENTER o codigo al bot cuando una red requiere verificacion manual.
8. Permite detener la ejecucion y limpiar el log visible.
9. Lee los CSV/XLSX de resultados para mostrar metricas, tablas, graficas y
   capturas en el dashboard.

Como se relaciona con proyecto.py
---------------------------------
interfaz.py no hace scraping directamente. Su responsabilidad es controlar la
ejecucion, persistir configuracion, mostrar resultados y exponer endpoints API.
El trabajo de abrir LinkedIn, iniciar sesion, buscar, filtrar y guardar archivos
lo realiza proyecto.py.

Para que sirve configuracion_busqueda.json
------------------------------------------
Es el archivo de parametros editables. La interfaz lo lee al cargar y lo
reescribe al guardar. proyecto.py lo lee al iniciar cada ejecucion. Asi se puede
cambiar la busqueda sin tocar codigo.

Campos principales del JSON:
- fecha_inicio / fecha_fin: rango de fechas que se desea analizar.
- max_publicaciones_por_busqueda: limite por cada combinacion banco + termino.
- max_publicaciones_por_banco: limite de publicaciones de perfil para IG/FB.
- max_comentarios_por_publicacion: limite de comentarios publicos por post.
- filtrar_por_fecha: activa o desactiva el filtro de rango de fechas.
- filtrar_por_relevancia: activa o desactiva el filtro semantico/reglas.
- guardar_descartadas: guarda auditoria de publicaciones descartadas.
- bancos_seleccionados: lista de bancos que se ejecutaran y se usaran como
  filtro visual del dashboard.

Mapa general del archivo
------------------------
- Constantes: rutas, puerto, bancos, valores por defecto y nombres de archivos.
- HTML: interfaz completa, CSS y JavaScript del dashboard.
- Configuracion: lectura, normalizacion y guardado del JSON.
- Estado de ejecucion: RUN_STATE, log, inicio/detencion del subproceso.
- Resultados: lectura de CSV, calculo de resumen, filtros por banco y capturas.
- HTTP handler: rutas GET/POST que usa el dashboard.
- main(): arranca el servidor local.

Inventario de funciones y clases
--------------------------------
- EjecucionEnCurso: excepcion para bloquear ejecuciones simultaneas.
- leer_csv(): abre un CSV de resultados y devuelve filas como diccionarios.
- leer_configuracion(): mezcla CONFIG_DEFAULT con configuracion_busqueda.json.
- normalizar_configuracion(): valida fechas, maximo, filtros y bancos.
- guardar_configuracion(): persiste la configuracion normalizada en JSON.
- ahora_texto(): genera timestamps legibles para el estado de ejecucion.
- agregar_log()/agregar_salida(): almacenan el log visible del subproceso.
- estado_ejecucion(): expone estado, tiempos, codigo de salida y log.
- entorno_proyecto(): prepara variables de entorno para ejecutar proyecto.py.
- leer_salida_proceso(): lee stdout del bot en tiempo real.
- iniciar_ejecucion(): crea el subproceso que corre proyecto.py.
- enviar_entrada_ejecucion(): envia ENTER u otro texto al bot.
- detener_ejecucion(): termina una ejecucion activa.
- limpiar_log_ejecucion(): borra solo el log visible, no resultados.
- respuesta_json()/respuesta_texto(): escriben respuestas HTTP.
- ejecuciones_disponibles(): lista carpetas resultados/ejecucion_*.
- obtener_ejecucion(): valida y resuelve una carpeta de ejecucion.
- archivo_en_ejecucion(): convierte claves API a rutas de archivos permitidos.
- bancos_desde_parametros(): interpreta el filtro visual de bancos del dashboard.
- filtrar_filas_por_bancos()/filtrar_tabla_por_bancos(): aplican ese filtro.
- tiempos_por_banco(): agrupa duraciones de busquedas por banco.
- resumen_ejecucion(): calcula metricas, tablas base, graficas y archivos.
- ruta_imagen_segura(): valida que una captura pertenezca a la ejecucion.
- InterfazHandler: controlador HTTP con rutas GET/POST del dashboard.
- main(): levanta el servidor en 127.0.0.1, puerto 8000 o disponible.
"""

import csv
import json
import mimetypes
import os
import signal
import subprocess
import sys
import threading
import time
from collections import Counter, deque
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
RESULTADOS_DIR = BASE_DIR / "resultados"
CONFIG_PATH = BASE_DIR / "configuracion_busqueda.json"
PROYECTO_PATH = BASE_DIR / "proyecto.py"
INSTAGRAM_PATH = BASE_DIR / "instagram_bot.py"
FACEBOOK_PATH = BASE_DIR / "facebook_bot.py"
RUTA_LOGO = BASE_DIR / "Logo" / "LINDA.png"
PYTHON_VENV = BASE_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LIBS_PATH = BASE_DIR / ".local-libs" / "usr" / "lib" / "x86_64-linux-gnu"
HOST = "127.0.0.1"
PORT = 8000
PORT_MAX = 8099

PLATAFORMAS = {
    "linkedin": {
        "label": "LinkedIn",
        "script": PROYECTO_PATH,
    },
    "instagram": {
        "label": "Instagram",
        "script": INSTAGRAM_PATH,
    },
    "facebook": {
        "label": "Facebook",
        "script": FACEBOOK_PATH,
    },
}

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

PERFILES_INSTAGRAM = {
    "Banco Popular Colombia": "https://www.instagram.com/bcopopular/",
    "Banco Davivienda": "https://www.instagram.com/davivienda/",
    "Bancolombia": "https://www.instagram.com/bancolombia/",
    "Banco de Bogotá": "https://www.instagram.com/bancodebogota/",
    "BBVA Colombia": "https://www.instagram.com/bbva_colombia/",
    "Banco Agrario de Colombia": "https://www.instagram.com/bancoagrario/",
    "Banco de Occidente": "https://www.instagram.com/bco_occidente/",
    "Banco AV Villas": "https://www.instagram.com/avvillas/",
    "Banco Caja Social": "https://www.instagram.com/bancocajasocial/",
}

PERFILES_FACEBOOK = {
    "Banco Popular Colombia": "https://web.facebook.com/BancoPopular",
    "Banco Davivienda": "https://web.facebook.com/BancoDavivienda",
    "Bancolombia": "https://web.facebook.com/Bancolombia",
    "Banco de Bogotá": "https://web.facebook.com/BancodeBogota",
    "Banco Agrario de Colombia": "https://web.facebook.com/bancoagrario",
    "Banco de Occidente": "https://web.facebook.com/BcoOccidente",
    "Banco Caja Social": "https://web.facebook.com/BancoCajaSocial",
}

BANCOS_DISPONIBLES_PLATAFORMA = {
    "linkedin": BANCOS_OBJETIVO.copy(),
    "instagram": [
        banco for banco in BANCOS_OBJETIVO if banco in PERFILES_INSTAGRAM
    ],
    "facebook": [
        banco for banco in BANCOS_OBJETIVO if banco in PERFILES_FACEBOOK
    ],
}

CONFIG_DEFAULT = {
    "plataforma": "linkedin",
    "fecha_inicio": "2026-04-01",
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


ARCHIVOS_TABLAS = {
    "publicaciones": "publicaciones_linkedin.csv",
    "descartadas": "publicaciones_descartadas.csv",
    "conteo": "conteo_por_banco.csv",
    "comparativo": "comparativo_banco_popular.csv",
    "tiempos": "tiempos_ejecucion.csv",
}


class EjecucionEnCurso(Exception):
    pass


RUN_LOCK = threading.Lock()
RUN_STATE = {
    "process": None,
    "status": "idle",
    "started_at": None,
    "started_monotonic": None,
    "finished_at": None,
    "finished_monotonic": None,
    "returncode": None,
    "log": deque(maxlen=600),
    "partial": "",
}


HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LINDA</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #1d2733;
      --muted: #637083;
      --line: #d9e0e7;
      --accent: #0f6b63;
      --accent-2: #275d9f;
      --warn: #b7791f;
      --bad: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      background: #17202a;
      color: #fff;
      border-bottom: 1px solid #0c1117;
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 12px;
      align-items: center;
      max-width: 1440px;
      margin: 0 auto;
      padding: 12px 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .brand-logo {
      width: 62px;
      height: 48px;
      object-fit: contain;
      border-radius: 6px;
      flex: 0 0 auto;
      background: #071426;
    }
    .brand-text {
      display: grid;
      gap: 2px;
      min-width: 0;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .brand-subtitle {
      color: #c8d5e2;
      font-size: 12px;
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    select, input, button {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      height: 36px;
      padding: 0 10px;
    }
    button {
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 650;
    }
    button:disabled {
      cursor: not-allowed;
      opacity: .55;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
      border-color: var(--accent);
    }
    button.danger {
      background: var(--bad);
      border-color: var(--bad);
      color: #fff;
    }
    main {
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel.pad { padding: 14px; }
    .metric .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .metric .value {
      margin-top: 4px;
      font-size: 28px;
      font-weight: 750;
    }
    .metric .sub {
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
    }
    .section {
      margin-top: 16px;
    }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .section-head h2 {
      margin: 0;
      font-size: 16px;
      line-height: 1.25;
    }
    .bars {
      display: grid;
      gap: 8px;
      padding: 14px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 190px 1fr 58px;
      align-items: center;
      gap: 10px;
    }
    .bar-label {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: #263445;
    }
    .bar-track {
      height: 14px;
      background: #eef2f5;
      border-radius: 3px;
      overflow: hidden;
    }
    .bar-fill {
      height: 100%;
      background: var(--accent-2);
      min-width: 2px;
    }
    .bar-fill.popular-bank {
      background: var(--accent);
    }
    .bar-label.popular-bank {
      font-weight: 700;
      color: var(--accent);
    }
    .bar-value {
      text-align: right;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    #countBars {
      gap: 10px;
    }
    #countBars .bar-row {
      grid-template-columns: 250px 1fr 72px;
      gap: 14px;
    }
    #countBars .bar-label,
    #countBars .bar-value {
      font-size: 17px;
      line-height: 1.25;
    }
    #countBars .bar-track {
      height: 20px;
    }
    .pain-row {
      display: grid;
      gap: 8px;
    }
    .pain-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }
    .pain-title {
      color: #263445;
      font-weight: 700;
    }
    .pain-note {
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    #painBars {
      gap: 13px;
    }
    #painBars .pain-title,
    #painBars .bar-value {
      font-size: 17px;
      line-height: 1.25;
    }
    #painBars .pain-note {
      font-size: 13px;
    }
    #painBars .bar-track {
      height: 18px;
    }
    .modality-dashboard {
      display: grid;
      grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
      gap: 32px;
      align-items: center;
      margin-bottom: 26px;
    }
    .modality-donut-area {
      display: grid;
      justify-items: center;
      gap: 12px;
      min-width: 0;
    }
    .modality-donut {
      position: relative;
      width: min(100%, 300px);
      aspect-ratio: 1;
      border-radius: 50%;
      background: #eef2f6;
      box-shadow: inset 0 0 0 1px rgba(23, 32, 42, .08);
    }
    .modality-donut::after {
      content: "";
      position: absolute;
      inset: 25%;
      border-radius: 50%;
      background: var(--panel);
      box-shadow: 0 0 0 1px rgba(23, 32, 42, .08);
    }
    .donut-center {
      position: absolute;
      inset: 27%;
      z-index: 1;
      display: grid;
      place-items: center;
      align-content: center;
      text-align: center;
      border-radius: 50%;
    }
    .donut-total {
      font-size: 44px;
      line-height: 1;
      font-weight: 800;
      color: #17202a;
      font-variant-numeric: tabular-nums;
    }
    .donut-label {
      margin-top: 6px;
      color: var(--muted);
      font-size: 16px;
      font-weight: 650;
      line-height: 1.15;
    }
    .modality-legend {
      display: grid;
      gap: 12px;
      min-width: 0;
    }
    .legend-item {
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr) minmax(112px, auto);
      gap: 12px;
      align-items: start;
      padding: 10px 0;
      border-bottom: 1px solid var(--line);
    }
    .legend-item:last-child {
      border-bottom: 0;
    }
    .legend-swatch {
      width: 16px;
      height: 16px;
      margin-top: 4px;
      border-radius: 3px;
      background: var(--legend-color);
    }
    .legend-text {
      min-width: 0;
    }
    .legend-title {
      color: #263445;
      font-weight: 700;
      font-size: 18px;
      line-height: 1.25;
    }
    .legend-note {
      margin-top: 3px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.25;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .legend-value {
      color: #17202a;
      font-weight: 800;
      font-size: 18px;
      line-height: 1.25;
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .tabs {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .tab {
      height: 34px;
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    .tab.active {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .table-tools {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .table-wrap {
      max-height: 520px;
      overflow: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #fff;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      min-width: 110px;
      font-size: 13px;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #17202a;
      font-size: 12px;
      color: #fff;
      text-transform: uppercase;
      letter-spacing: .03em;
    }
    tbody tr:nth-child(even) td { background: #f7f9fb; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover td { background: #edf6ff; }
    td.long {
      min-width: 360px;
      max-width: 520px;
      white-space: pre-wrap;
    }
    .split {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 12px;
    }
    .preview {
      display: grid;
      gap: 10px;
      align-content: start;
      padding: 14px;
      min-height: 260px;
    }
    .preview img {
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    .muted { color: var(--muted); }
    .links {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .config-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
      padding: 14px;
    }
    .field {
      display: grid;
      gap: 5px;
    }
    .field label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .check-field {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 36px;
      color: #2f3c4d;
    }
    .check-field input {
      width: 16px;
      height: 16px;
      padding: 0;
    }
    .config-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .bank-selector {
      display: grid;
      gap: 10px;
      padding: 0 14px 14px;
    }
    .bank-selector-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }
    .bank-selector-head label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .bank-selector-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    button.compact {
      height: 30px;
      padding: 0 8px;
      font-size: 12px;
    }
    .bank-options {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
    }
    .bank-option {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: #2f3c4d;
    }
    .bank-option input {
      width: 16px;
      height: 16px;
      padding: 0;
      flex: 0 0 auto;
    }
    .config-message {
      padding: 0 14px 14px;
      color: var(--muted);
      min-height: 20px;
    }
    .hidden {
      display: none !important;
    }
    .run-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .run-body {
      display: grid;
      gap: 12px;
      padding: 14px;
    }
    .run-row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .run-code {
      display: grid;
      grid-template-columns: minmax(180px, 260px) auto;
      gap: 8px;
      align-items: center;
    }
    .run-badge {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 3px 10px;
      border-radius: 999px;
      background: #eef2f5;
      color: #2f3c4d;
      font-weight: 700;
    }
    .run-badge.running,
    .run-badge.starting,
    .run-badge.stopping {
      background: #e7f4f2;
      color: var(--accent);
    }
    .run-badge.finished {
      background: #e8f5ee;
      color: #166534;
    }
    .run-badge.error,
    .run-badge.stopped {
      background: #fdecec;
      color: var(--bad);
    }
    .run-log {
      margin: 0;
      min-height: 180px;
      max-height: 320px;
      overflow: auto;
      padding: 12px;
      border-radius: 6px;
      background: #101820;
      color: #dfe8ef;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
    }
    .link-button {
      display: inline-flex;
      align-items: center;
      height: 34px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      text-decoration: none;
      color: var(--text);
      background: #fff;
    }
    .status {
      min-height: 20px;
      color: var(--muted);
    }
    @media (max-width: 980px) {
      .topbar { grid-template-columns: 1fr; }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .config-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .bank-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .split { grid-template-columns: 1fr; }
      .modality-dashboard { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 130px 1fr 44px; }
    }
    @media (max-width: 640px) {
      main { padding: 10px; }
      .brand-subtitle { white-space: normal; }
      .grid { grid-template-columns: 1fr; }
      .config-grid { grid-template-columns: 1fr; }
      .bank-options { grid-template-columns: 1fr; }
      .run-code { grid-template-columns: 1fr; }
      .section-head { align-items: stretch; flex-direction: column; }
      .table-tools { flex-direction: column; align-items: stretch; }
      .modality-donut { width: min(100%, 260px); }
      .legend-item { grid-template-columns: 16px minmax(0, 1fr); }
      .legend-value {
        grid-column: 2;
        text-align: left;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="brand">
        <img class="brand-logo" src="/assets/logo" alt="Logo LINDA">
        <div class="brand-text">
          <h1>LINDA</h1>
          <div class="brand-subtitle">LinkedIn de Investigación de Denuncias y Alertas</div>
        </div>
      </div>
      <select id="executionSelect" aria-label="Ejecucion"></select>
      <button id="refreshBtn">Actualizar</button>
    </div>
  </header>
  <main>
    <div class="status" id="status">Cargando...</div>

    <section class="grid section" id="metrics"></section>

    <section class="section panel">
      <div class="section-head">
        <h2>Configuración de búsqueda</h2>
        <div class="muted">Aplica a la próxima ejecución del bot</div>
      </div>
      <div class="config-grid">
        <div class="field">
          <label for="plataforma">Red social</label>
          <select id="plataforma">
            <option value="linkedin">LinkedIn</option>
            <option value="instagram">Instagram</option>
            <option value="facebook">Facebook</option>
          </select>
        </div>
        <div class="field">
          <label for="fechaInicio">Fecha inicio</label>
          <input id="fechaInicio" type="date">
        </div>
        <div class="field">
          <label for="fechaFin">Fecha fin</label>
          <input id="fechaFin" type="date">
        </div>
        <div class="field" id="linkedinMaxField">
          <label for="maxPublicaciones">Máx. por consulta</label>
          <input id="maxPublicaciones" type="number" min="1" step="1">
        </div>
        <div class="field hidden" id="socialPostsField">
          <label for="maxPublicacionesBanco">Máx. publicaciones por banco</label>
          <input id="maxPublicacionesBanco" type="number" min="1" step="1">
        </div>
        <div class="field hidden" id="socialCommentsField">
          <label for="maxComentariosPublicacion">Máx. comentarios por publicación</label>
          <input id="maxComentariosPublicacion" type="number" min="1" step="1">
        </div>
        <label class="check-field">
          <input id="filtrarFecha" type="checkbox">
          Filtrar fecha
        </label>
        <label class="check-field">
          <input id="filtrarRelevancia" type="checkbox">
          Filtrar relevancia
        </label>
        <div class="config-actions">
          <button id="saveConfigBtn">Guardar</button>
          <button class="secondary" id="reloadConfigBtn">Recargar</button>
        </div>
      </div>
      <div class="bank-selector">
        <div class="bank-selector-head">
          <label>Bancos a buscar</label>
          <div class="bank-selector-actions">
            <button class="secondary compact" id="selectAllBanks" type="button">Todos</button>
            <button class="secondary compact" id="clearBanks" type="button">Ninguno</button>
          </div>
        </div>
        <div class="bank-options" id="bankOptions"></div>
      </div>
      <div class="config-message" id="configMessage"></div>
    </section>

    <section class="section panel">
      <div class="section-head">
        <h2>Ejecución del proyecto</h2>
        <div class="run-actions">
          <button id="runStartBtn">Ejecutar proyecto</button>
          <button class="secondary" id="runEnterBtn">Enviar ENTER</button>
          <button class="secondary" id="runClearLogBtn">Limpiar log</button>
          <button class="danger" id="runStopBtn">Detener</button>
        </div>
      </div>
      <div class="run-body">
        <div class="run-row">
          <span class="run-badge" id="runBadge">Inactivo</span>
          <span class="muted" id="runDetail">Sin ejecución activa.</span>
        </div>
        <div class="run-code">
          <input id="linkedinCode" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="Código de verificación">
          <button class="secondary" id="runCodeBtn">Enviar código</button>
        </div>
        <pre class="run-log" id="runLog"></pre>
      </div>
    </section>

    <section class="section panel">
      <div class="section-head">
        <h2>Archivos</h2>
        <div class="links" id="fileLinks"></div>
      </div>
    </section>

    <section class="section split">
      <div class="panel">
        <div class="section-head"><h2 id="countChartTitle">Denuncias directas por banco</h2></div>
        <div class="bars" id="countBars"></div>
      </div>
      <div class="panel">
        <div class="section-head"><h2 id="timeChartTitle">Tiempo por banco</h2></div>
        <div class="bars" id="timeBars"></div>
      </div>
    </section>

    <section class="section panel">
      <div class="section-head"><h2 id="modalityChartTitle">Modalidad reportada</h2></div>
      <div class="modality-dashboard">
        <div class="modality-donut-area">
          <div class="modality-donut" id="modalityDonut">
            <div class="donut-center">
              <div class="donut-total" id="modalityDonutTotal">0</div>
              <div class="donut-label">publicaciones</div>
            </div>
          </div>
        </div>
        <div class="modality-legend" id="modalityLegend"></div>
      </div>
      <div class="bars" id="painBars"></div>
    </section>

    <section class="section panel">
      <div class="section-head">
        <div class="tabs" id="tabs"></div>
        <div class="table-tools">
          <input id="filterInput" placeholder="Filtrar tabla">
          <button class="secondary" id="clearFilter">Limpiar</button>
        </div>
      </div>
      <div class="split">
        <div class="table-wrap"><table id="dataTable"></table></div>
        <aside class="preview" id="preview">
          <strong>Vista de captura</strong>
          <div class="muted">Selecciona una fila de publicaciones o descartadas.</div>
        </aside>
      </div>
    </section>
  </main>

  <script>
    const state = {
      execution: "",
      table: "publicaciones",
      rows: [],
      summary: null,
      runRunning: false,
      runPoll: null
    };

    const tableLabels = {
      publicaciones: "Publicaciones",
      descartadas: "Descartadas",
      conteo: "Conteo",
      comparativo: "Comparativo",
      tiempos: "Tiempos"
    };

    const fileLabels = {
      publicaciones_linkedin: "Publicaciones CSV",
      publicaciones_descartadas: "Descartadas CSV",
      conteo_por_banco: "Conteo CSV",
      comparativo_banco_popular: "Comparativo CSV",
      tiempos_ejecucion: "Tiempos CSV",
      reporte_bancos: "Reporte Excel consolidado"
    };

    const runLabels = {
      idle: "Inactivo",
      starting: "Iniciando",
      running: "En ejecución",
      stopping: "Deteniendo",
      stopped: "Detenido",
      finished: "Finalizado",
      error: "Error"
    };

    const painLabels = {
      falsificacion: "Falsificación",
      estafa: "Estafa",
      robo_datos: "Robo de datos",
      tarjeta: "Fraude con tarjeta",
      transaccion_no_autorizada: "Transacción no autorizada",
      contacto_no_oficial: "Contacto no oficial",
      queja_bancaria_general: "Queja bancaria general",
      servicio_tramite_bancario: "Servicio o trámite bancario",
      sin_clasificar: "Casos por revisar",
      sin_publicaciones: "Sin publicaciones"
    };

    const columnLabels = {
      dolor_cliente: "modalidad_reportada",
      dolor_cliente_secundario: "modalidad_secundaria",
      modalidad_especifica: "modalidad_especifica",
      confianza_dolor: "confianza_modalidad",
      palabras_dolor_detectadas: "palabras_detectadas"
    };

    const availableBanks = [
      "Banco Popular Colombia",
      "Banco Davivienda",
      "Bancolombia",
      "Banco de Bogotá",
      "BBVA Colombia",
      "Banco Agrario de Colombia",
      "Scotiabank Colpatria",
      "Banco de Occidente",
      "Banco AV Villas",
      "Banco Caja Social"
    ];

    const availableBanksByPlatform = {
      linkedin: availableBanks,
      instagram: [
        "Banco Popular Colombia",
        "Banco Davivienda",
        "Bancolombia",
        "Banco de Bogotá",
        "BBVA Colombia",
        "Banco Agrario de Colombia",
        "Banco de Occidente",
        "Banco AV Villas",
        "Banco Caja Social"
      ],
      facebook: [
        "Banco Popular Colombia",
        "Banco Davivienda",
        "Bancolombia",
        "Banco de Bogotá",
        "Banco Agrario de Colombia",
        "Banco de Occidente",
        "Banco Caja Social"
      ]
    };

    const popularBank = "Banco Popular Colombia";
    const modalityColors = [
      "#0F6B63",
      "#275D9F",
      "#B44E5A",
      "#8A63D2",
      "#C77818",
      "#2C7A9B",
      "#59636F"
    ];

    function status(text) {
      document.getElementById("status").textContent = text || "";
    }

    async function getJson(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    async function postJson(url, payload) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }

    function configStatus(text) {
      document.getElementById("configMessage").textContent = text || "";
    }

    function number(value) {
      const parsed = Number(value || 0);
      return Number.isFinite(parsed) ? parsed : 0;
    }

    function currentPlatform() {
      return document.getElementById("plataforma").value || "linkedin";
    }

    function platformBanks(platform) {
      return availableBanksByPlatform[platform] || availableBanks;
    }

    function visibleSelectedBanks(selectedBanks, platform) {
      const available = platformBanks(platform);
      const selected = (selectedBanks || available).filter(bank => available.includes(bank));
      return selected.length ? selected : available;
    }

    function renderBankOptions(selectedBanks, platform) {
      const platformKey = platform || currentPlatform();
      const available = platformBanks(platformKey);
      const selected = new Set(visibleSelectedBanks(selectedBanks, platformKey));
      const html = available.map(bank => {
        const checked = selected.has(bank) ? " checked" : "";
        return `<label class="bank-option">
          <input type="checkbox" name="bancosSeleccionados" value="${bank}"${checked}>
          ${bank}
        </label>`;
      }).join("");
      document.getElementById("bankOptions").innerHTML = html;
    }

    function updatePlatformControls() {
      const platform = currentPlatform();
      const filtroRelevancia = document.getElementById("filtrarRelevancia");
      document.getElementById("linkedinMaxField").classList.toggle("hidden", platform !== "linkedin");
      document.getElementById("socialPostsField").classList.toggle("hidden", platform === "linkedin");
      document.getElementById("socialCommentsField").classList.toggle("hidden", platform === "linkedin");
      if (platform === "linkedin") {
        filtroRelevancia.checked = true;
        filtroRelevancia.disabled = true;
      } else {
        filtroRelevancia.disabled = false;
      }
      renderBankOptions(selectedBanks(), platform);
    }

    function selectedBanks() {
      return Array.from(document.querySelectorAll("input[name='bancosSeleccionados']:checked"))
        .map(input => input.value);
    }

    function setAllBanks(checked) {
      document.querySelectorAll("input[name='bancosSeleccionados']").forEach(input => {
        input.checked = checked;
      });
    }

    function bancosFiltroQuery() {
      return selectedBanks().map(bank => encodeURIComponent(bank)).join(",");
    }

    function withBankFilter(url) {
      const separator = url.includes("?") ? "&" : "?";
      return `${url}${separator}banks=${bancosFiltroQuery()}`;
    }

    async function refreshDashboardForBankFilter() {
      if (!state.execution) return;
      await loadDashboard();
    }

    function metric(label, value, sub) {
      return `<div class="panel pad metric">
        <div class="label">${label}</div>
        <div class="value">${value}</div>
        <div class="sub">${sub || ""}</div>
      </div>`;
    }

    function renderMetrics() {
      const s = state.summary || {};
      document.getElementById("metrics").innerHTML = [
        metric("Denuncias directas", s.publicaciones || 0, "publicaciones relevantes"),
        metric("Descartadas", s.descartadas || 0, "auditoria del filtro"),
        metric("Bancos", s.bancos_con_resultados || 0, "con al menos una denuncia"),
        metric("Tiempo total", `${s.duracion_total_minutos || 0} min`, `${s.total_busquedas || 0} consultas`)
      ].join("");
    }

    function summaryDateRange() {
      const s = state.summary || {};
      const rows = [
        ...(s.conteo || []),
        ...(s.comparativo || []),
        ...(state.rows || [])
      ];
      const row = rows.find(item => item && item.rango_fecha);
      return row ? row.rango_fecha : "";
    }

    function titleWithRange(title) {
      const range = summaryDateRange();
      return range ? `${title} | ${range}` : title;
    }

    function renderChartTitles() {
      document.getElementById("countChartTitle").textContent = titleWithRange("Denuncias directas por banco");
      document.getElementById("timeChartTitle").textContent = titleWithRange("Tiempo por banco");
      document.getElementById("modalityChartTitle").textContent = titleWithRange("Modalidad reportada");
    }

    async function loadConfig() {
      const config = await getJson("/api/config");
      document.getElementById("plataforma").value = config.plataforma || "linkedin";
      document.getElementById("fechaInicio").value = config.fecha_inicio || "";
      document.getElementById("fechaFin").value = config.fecha_fin || "";
      document.getElementById("maxPublicaciones").value = config.max_publicaciones_por_busqueda || 20;
      document.getElementById("maxPublicacionesBanco").value = config.max_publicaciones_por_banco || 50;
      document.getElementById("maxComentariosPublicacion").value = config.max_comentarios_por_publicacion || 200;
      document.getElementById("filtrarFecha").checked = Boolean(config.filtrar_por_fecha);
      document.getElementById("filtrarRelevancia").checked = Boolean(config.filtrar_por_relevancia);
      renderBankOptions(config.bancos_seleccionados || platformBanks(currentPlatform()), currentPlatform());
      updatePlatformControls();
      configStatus("Configuración cargada.");
    }

    async function saveConfig() {
      configStatus("Guardando configuración...");
      const bancosSeleccionados = selectedBanks();
      if (!bancosSeleccionados.length) {
        configStatus("Selecciona al menos un banco.");
        throw new Error("Selecciona al menos un banco.");
      }
      const payload = {
        plataforma: document.getElementById("plataforma").value,
        fecha_inicio: document.getElementById("fechaInicio").value,
        fecha_fin: document.getElementById("fechaFin").value,
        max_publicaciones_por_busqueda: Number(document.getElementById("maxPublicaciones").value),
        max_publicaciones_por_banco: Number(document.getElementById("maxPublicacionesBanco").value),
        max_comentarios_por_publicacion: Number(document.getElementById("maxComentariosPublicacion").value),
        leer_respuestas_comentarios: false,
        filtrar_por_fecha: document.getElementById("filtrarFecha").checked,
        filtrar_por_relevancia: currentPlatform() === "linkedin"
          ? true
          : document.getElementById("filtrarRelevancia").checked,
        guardar_descartadas: true,
        bancos_seleccionados: bancosSeleccionados
      };
      await postJson("/api/config", payload);
      configStatus("Configuración guardada. Se usará en la próxima ejecución.");
    }

    function formatElapsed(seconds) {
      const total = Math.max(0, Math.round(Number(seconds || 0)));
      const minutes = Math.floor(total / 60);
      const rest = total % 60;
      return `${minutes}:${String(rest).padStart(2, "0")}`;
    }

    function renderRunStatus(data) {
      const badge = document.getElementById("runBadge");
      const detail = document.getElementById("runDetail");
      const log = document.getElementById("runLog");
      const statusKey = data.status || "idle";

      badge.className = `run-badge ${statusKey}`;
      badge.textContent = runLabels[statusKey] || statusKey;

      const pieces = [`Tiempo: ${formatElapsed(data.elapsed_seconds)}`];
      if (data.started_at) pieces.push(`Inicio: ${data.started_at}`);
      if (data.finished_at) pieces.push(`Fin: ${data.finished_at}`);
      if (data.returncode !== null && data.returncode !== undefined) {
        pieces.push(`Código: ${data.returncode}`);
      }
      detail.textContent = pieces.join(" | ");

      log.textContent = (data.log || []).join("\n");
      log.scrollTop = log.scrollHeight;

      document.getElementById("runStartBtn").disabled = Boolean(data.running);
      document.getElementById("runEnterBtn").disabled = !data.running;
      document.getElementById("runStopBtn").disabled = !data.running;
      document.getElementById("runCodeBtn").disabled = !data.running;
    }

    async function refreshRunStatus() {
      const wasRunning = state.runRunning;
      const data = await getJson("/api/run/status");
      renderRunStatus(data);
      state.runRunning = Boolean(data.running);

      if (wasRunning && !state.runRunning) {
        await loadExecutions();
      }

      if (state.runRunning && !state.runPoll) {
        state.runPoll = setInterval(() => {
          refreshRunStatus().catch(error => status(`Error: ${error.message}`));
        }, 2500);
      }

      if (!state.runRunning && state.runPoll) {
        clearInterval(state.runPoll);
        state.runPoll = null;
      }
    }

    async function startRun() {
      await saveConfig();
      status("Iniciando ejecución del proyecto...");
      const data = await postJson("/api/run/start", {});
      renderRunStatus(data);
      state.runRunning = Boolean(data.running);
      await refreshRunStatus();
    }

    async function sendEnterToRun() {
      const data = await postJson("/api/run/input", { text: "\n" });
      renderRunStatus(data);
    }

    async function sendLinkedInCode() {
      const input = document.getElementById("linkedinCode");
      const code = input.value.trim();
      if (!code) {
        status("Escribe el código de verificación antes de enviarlo.");
        return;
      }
      const data = await postJson("/api/run/input", { text: `CODIGO:${code}\n` });
      input.value = "";
      status("Código enviado al navegador.");
      renderRunStatus(data);
    }

    async function stopRun() {
      const data = await postJson("/api/run/stop", {});
      renderRunStatus(data);
      await refreshRunStatus();
    }

    async function clearRunLog() {
      const data = await postJson("/api/run/log/clear", {});
      renderRunStatus(data);
    }

    function renderFileLinks() {
      const files = (state.summary && state.summary.archivos) || {};
      const links = Object.entries(files)
        .filter(([key, exists]) => exists && key === "reporte_bancos")
        .map(([key]) => {
          const url = `/api/file?exec=${encodeURIComponent(state.execution)}&file=${encodeURIComponent(key)}`;
          return `<a class="link-button" href="${url}">${fileLabels[key] || key}</a>`;
        });
      document.getElementById("fileLinks").innerHTML = links.join("");
    }

    function sortBankChartRows(rows, valueKey) {
      const copied = [...rows];
      const popular = copied.filter(row => (row.banco || "") === popularBank);
      const others = copied
        .filter(row => (row.banco || "") !== popularBank)
        .sort((a, b) => {
          const diff = number(b[valueKey]) - number(a[valueKey]);
          return diff || String(a.banco || "").localeCompare(String(b.banco || ""));
        });
      return [...popular, ...others];
    }

    function renderBars(id, rows, labelKey, valueKey, formatValue, highlightLabel) {
      const max = Math.max(1, ...rows.map(row => number(row[valueKey])));
      const html = rows.map(row => {
        const value = number(row[valueKey]);
        const width = Math.max(2, Math.round((value / max) * 100));
        const displayValue = formatValue ? formatValue(value, row) : value;
        const label = row[labelKey] || "";
        const highlight = label === highlightLabel ? " popular-bank" : "";
        return `<div class="bar-row">
          <div class="bar-label${highlight}" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
          <div class="bar-track"><div class="bar-fill${highlight}" style="width:${width}%"></div></div>
          <div class="bar-value">${displayValue}</div>
        </div>`;
      }).join("");
      document.getElementById(id).innerHTML = html || `<div class="muted">Sin datos.</div>`;
    }

    function renderBankBars(rows) {
      renderBars(
        "countBars",
        sortBankChartRows(rows || [], "publicaciones"),
        "banco",
        "publicaciones",
        null,
        popularBank
      );
    }

    function formatDuration(seconds) {
      if (seconds >= 60) return `${(seconds / 60).toFixed(1)} min`;
      return `${seconds.toFixed(0)} s`;
    }

    function topModalityRows(rows, limit = 6) {
      const ordered = [...(rows || [])]
        .filter(row => number(row.publicaciones) > 0)
        .sort((a, b) => {
          const diff = number(b.publicaciones) - number(a.publicaciones);
          return diff || String(a.modalidad_reportada || "").localeCompare(String(b.modalidad_reportada || ""));
        });

      const topRows = ordered.slice(0, limit);
      const remaining = ordered.slice(limit);

      if (!remaining.length) return topRows;

      const otrasPublicaciones = remaining.reduce((total, row) => total + number(row.publicaciones), 0);
      const otrasPorcentaje = remaining.reduce((total, row) => total + number(row.participacion_porcentaje), 0);

      return [
        ...topRows,
        {
          modalidad_reportada: "Otras modalidades",
          publicaciones: otrasPublicaciones,
          participacion_porcentaje: otrasPorcentaje,
          bancos_impactados: "",
          palabras_detectadas: ""
        }
      ];
    }

    function renderModalityDonut(rows) {
      const donutRows = topModalityRows(rows);
      const total = donutRows.reduce((sum, row) => sum + number(row.publicaciones), 0);
      const donut = document.getElementById("modalityDonut");
      const totalNode = document.getElementById("modalityDonutTotal");
      const legend = document.getElementById("modalityLegend");

      totalNode.textContent = total;

      if (!total || !donutRows.length) {
        donut.style.background = "#eef2f6";
        legend.innerHTML = `<div class="muted">Sin datos.</div>`;
        return;
      }

      let cursor = 0;
      const segments = donutRows.map((row, index) => {
        const value = number(row.publicaciones);
        const start = cursor;
        const end = cursor + (value / total) * 100;
        cursor = end;
        const color = modalityColors[index % modalityColors.length];
        return `${color} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
      });

      donut.style.background = `conic-gradient(${segments.join(", ")})`;

      legend.innerHTML = donutRows.map((row, index) => {
        const value = number(row.publicaciones);
        const percent = total ? ((value / total) * 100).toFixed(1) : "0.0";
        const label = row.modalidad_reportada || "Sin modalidad";
        const banks = row.bancos_impactados
          ? `<div class="legend-note" title="${escapeHtml(row.bancos_impactados)}">${escapeHtml(row.bancos_impactados)}</div>`
          : "";
        return `<div class="legend-item" style="--legend-color:${modalityColors[index % modalityColors.length]}">
          <div class="legend-swatch"></div>
          <div class="legend-text">
            <div class="legend-title">${escapeHtml(label)}</div>
            ${banks}
          </div>
          <div class="legend-value">${value} · ${percent}%</div>
        </div>`;
      }).join("");
    }

    function renderPainBars(rows) {
      const max = Math.max(1, ...rows.map(row => number(row.publicaciones)));
      const html = rows.map(row => {
        const value = number(row.publicaciones);
        const width = Math.max(2, Math.round((value / max) * 100));
        const key = row.dolor_cliente || "sin_clasificar";
        const label = row.modalidad_reportada || painLabels[key] || key;
        const percent = number(row.participacion_porcentaje).toFixed(1);
        const words = row.palabras_detectadas
          ? `<div class="pain-note" title="${escapeHtml(row.palabras_detectadas)}">${escapeHtml(row.palabras_detectadas)}</div>`
          : "";
        const banks = row.bancos_impactados
          ? `<div class="pain-note" title="${escapeHtml(row.bancos_impactados)}">${escapeHtml(row.bancos_impactados)}</div>`
          : "";
        return `<div class="pain-row">
          <div class="pain-head">
            <div class="pain-title">${escapeHtml(label)}</div>
            <div class="bar-value">${value} (${percent}%)</div>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          ${banks}
          ${words}
        </div>`;
      }).join("");
      document.getElementById("painBars").innerHTML = html || `<div class="muted">Sin datos.</div>`;
    }

    function renderTabs() {
      const tabs = Object.keys(tableLabels).map(key => {
        const active = key === state.table ? " active" : "";
        return `<button class="tab${active}" data-tab="${key}">${tableLabels[key]}</button>`;
      }).join("");
      document.getElementById("tabs").innerHTML = tabs;
      document.querySelectorAll(".tab").forEach(button => {
        button.addEventListener("click", () => {
          state.table = button.dataset.tab;
          document.getElementById("filterInput").value = "";
          loadTable();
        });
      });
    }

    function cellClass(key) {
      return ["texto", "motivo_relevancia", "terminos_contexto", "terminos_exclusion"].includes(key)
        ? "long"
        : "";
    }

    function resetPreview() {
      document.getElementById("preview").innerHTML = `
        <strong>Vista de captura</strong>
        <div class="muted">Selecciona una fila de publicaciones o descartadas.</div>
      `;
    }

    function renderTable() {
      resetPreview();
      const filter = document.getElementById("filterInput").value.trim().toLowerCase();
      const rows = filter
        ? state.rows.filter(row => Object.values(row).join(" ").toLowerCase().includes(filter))
        : state.rows;
      const table = document.getElementById("dataTable");
      if (!rows.length) {
        table.innerHTML = `<tbody><tr><td class="muted">Sin filas para mostrar.</td></tr></tbody>`;
        return;
      }
      const headers = Object.keys(rows[0]);
      const thead = `<thead><tr>${headers.map(h => `<th>${columnLabels[h] || h}</th>`).join("")}</tr></thead>`;
      const tbody = rows.map((row, index) => {
        const cls = ["publicaciones", "descartadas"].includes(state.table) ? " class=\"clickable\"" : "";
        const cells = headers.map(h => `<td class="${cellClass(h)}">${escapeHtml(row[h] || "")}</td>`).join("");
        return `<tr${cls} data-index="${index}">${cells}</tr>`;
      }).join("");
      table.innerHTML = `${thead}<tbody>${tbody}</tbody>`;
      table.querySelectorAll("tr.clickable").forEach(tr => {
        tr.addEventListener("click", () => showPreview(rows[Number(tr.dataset.index)]));
      });
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function showPreview(row) {
      const preview = document.getElementById("preview");
      const path = row.imagen_publicacion || "";
      const image = path
        ? `<img src="/api/image?exec=${encodeURIComponent(state.execution)}&path=${encodeURIComponent(path)}" alt="Captura">`
        : `<div class="muted">Esta fila no tiene imagen asociada.</div>`;
      preview.innerHTML = `
        <strong>${escapeHtml(row.banco || "Publicacion")}</strong>
        <div class="muted">${escapeHtml(row.autor || "")}</div>
        ${image}
        <div>${escapeHtml((row.texto || "").slice(0, 900))}</div>
      `;
    }

    async function loadExecutions() {
      const data = await getJson("/api/executions");
      const select = document.getElementById("executionSelect");
      const previous = state.execution;
      select.innerHTML = data.executions.map(item => {
        return `<option value="${item.name}">${item.name}</option>`;
      }).join("");
      if (!data.executions.length) {
        state.execution = "";
        state.summary = null;
        status("No hay ejecuciones en resultados/.");
        return;
      }
      const exists = data.executions.some(item => item.name === previous);
      state.execution = exists ? previous : data.executions[0].name;
      select.value = state.execution;
      select.onchange = () => {
        state.execution = select.value;
        loadDashboard();
      };
      await loadDashboard();
    }

    async function loadDashboard() {
      if (!state.execution) return;
      status("Cargando ejecucion...");
      state.summary = await getJson(withBankFilter(`/api/summary?exec=${encodeURIComponent(state.execution)}`));
      renderMetrics();
      renderChartTitles();
      renderFileLinks();
      renderBankBars(state.summary.conteo || []);
      renderBars("timeBars", state.summary.tiempos_banco || [], "banco", "duracion_segundos", formatDuration);
      renderModalityDonut(state.summary.dolor_cliente || []);
      renderPainBars(state.summary.dolor_cliente || []);
      renderTabs();
      await loadTable();
      status(`Ejecucion cargada: ${state.execution}`);
    }

    async function loadTable() {
      const data = await getJson(withBankFilter(`/api/table?exec=${encodeURIComponent(state.execution)}&table=${encodeURIComponent(state.table)}`));
      state.rows = data.rows || [];
      renderTabs();
      renderTable();
    }

    document.getElementById("refreshBtn").addEventListener("click", loadDashboard);
    document.getElementById("filterInput").addEventListener("input", renderTable);
    document.getElementById("clearFilter").addEventListener("click", () => {
      document.getElementById("filterInput").value = "";
      renderTable();
    });

    document.getElementById("saveConfigBtn").addEventListener("click", () => {
      saveConfig().catch(error => configStatus(`Error: ${error.message}`));
    });
    document.getElementById("reloadConfigBtn").addEventListener("click", () => {
      loadConfig().catch(error => configStatus(`Error: ${error.message}`));
    });
    document.getElementById("plataforma").addEventListener("change", () => {
      updatePlatformControls();
      refreshDashboardForBankFilter().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("bankOptions").addEventListener("change", () => {
      refreshDashboardForBankFilter().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("selectAllBanks").addEventListener("click", () => {
      setAllBanks(true);
      refreshDashboardForBankFilter().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("clearBanks").addEventListener("click", () => {
      setAllBanks(false);
      refreshDashboardForBankFilter().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("runStartBtn").addEventListener("click", () => {
      startRun().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("runEnterBtn").addEventListener("click", () => {
      sendEnterToRun().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("runCodeBtn").addEventListener("click", () => {
      sendLinkedInCode().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("linkedinCode").addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        sendLinkedInCode().catch(error => status(`Error: ${error.message}`));
      }
    });
    document.getElementById("runClearLogBtn").addEventListener("click", () => {
      clearRunLog().catch(error => status(`Error: ${error.message}`));
    });
    document.getElementById("runStopBtn").addEventListener("click", () => {
      stopRun().catch(error => status(`Error: ${error.message}`));
    });

    loadConfig()
      .then(() => Promise.all([
        loadExecutions(),
        refreshRunStatus()
      ]))
      .catch(error => status(`Error: ${error.message}`));
  </script>
</body>
</html>
"""


def leer_csv(ruta):
    if not ruta.exists():
        return []

    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def leer_configuracion():
    configuracion = CONFIG_DEFAULT.copy()

    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        configuracion.update(datos)

    return normalizar_configuracion(configuracion)


def entero_configuracion(configuracion, clave, defecto, mensaje):
    try:
        valor = int(configuracion.get(clave, defecto))
    except (TypeError, ValueError) as exc:
        raise ValueError(mensaje) from exc

    if valor <= 0:
        raise ValueError(mensaje)

    return valor


def normalizar_configuracion(configuracion):
    plataforma = str(configuracion.get("plataforma", "linkedin")).strip().lower()
    if plataforma not in PLATAFORMAS:
        raise ValueError("La red social seleccionada no es válida.")

    fecha_inicio = str(configuracion.get("fecha_inicio", "")).strip()
    fecha_fin = str(configuracion.get("fecha_fin", "")).strip()

    try:
        fecha_inicio_date = date.fromisoformat(fecha_inicio)
        fecha_fin_date = date.fromisoformat(fecha_fin)
    except ValueError as exc:
        raise ValueError("Las fechas deben tener formato AAAA-MM-DD.") from exc

    if fecha_inicio_date > fecha_fin_date:
        raise ValueError("La fecha inicial no puede ser mayor que la fecha final.")

    max_publicaciones = entero_configuracion(
        configuracion,
        "max_publicaciones_por_busqueda",
        20,
        "El máximo por consulta debe ser un número entero mayor que cero.",
    )
    max_publicaciones_banco = entero_configuracion(
        configuracion,
        "max_publicaciones_por_banco",
        50,
        "El máximo de publicaciones por banco debe ser un número entero mayor que cero.",
    )
    max_comentarios = entero_configuracion(
        configuracion,
        "max_comentarios_por_publicacion",
        200,
        "El máximo de comentarios por publicación debe ser un número entero mayor que cero.",
    )

    bancos_raw = configuracion.get("bancos_seleccionados", BANCOS_OBJETIVO)
    if isinstance(bancos_raw, str):
        bancos_raw = [bancos_raw]
    if not isinstance(bancos_raw, list):
        raise ValueError("La selección de bancos debe ser una lista.")

    bancos_disponibles = BANCOS_DISPONIBLES_PLATAFORMA[plataforma]
    bancos_seleccionados = []
    for banco in bancos_raw:
        banco = str(banco).strip()
        if banco in bancos_disponibles and banco not in bancos_seleccionados:
            bancos_seleccionados.append(banco)

    if not bancos_seleccionados:
        bancos_seleccionados = bancos_disponibles.copy()

    filtrar_por_relevancia = bool(configuracion.get("filtrar_por_relevancia", True))
    if plataforma == "linkedin":
        filtrar_por_relevancia = True

    return {
        "plataforma": plataforma,
        "fecha_inicio": fecha_inicio_date.isoformat(),
        "fecha_fin": fecha_fin_date.isoformat(),
        "max_publicaciones_por_busqueda": max_publicaciones,
        "max_publicaciones_por_banco": max_publicaciones_banco,
        "max_comentarios_por_publicacion": max_comentarios,
        "leer_respuestas_comentarios": False,
        "filtrar_por_fecha": bool(configuracion.get("filtrar_por_fecha", True)),
        "filtrar_por_relevancia": filtrar_por_relevancia,
        "guardar_descartadas": bool(configuracion.get("guardar_descartadas", True)),
        "bancos_seleccionados": bancos_seleccionados,
    }


def guardar_configuracion(configuracion):
    normalizada = normalizar_configuracion(configuracion)

    with CONFIG_PATH.open("w", encoding="utf-8") as archivo:
        json.dump(normalizada, archivo, indent=2, ensure_ascii=False)
        archivo.write("\n")

    return normalizada


def ahora_texto():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def agregar_log(linea):
    with RUN_LOCK:
        parcial = RUN_STATE.get("partial", "")
        if parcial:
            RUN_STATE["log"].append(parcial)
            RUN_STATE["partial"] = ""
        RUN_STATE["log"].append(linea)


def agregar_salida(fragmento):
    with RUN_LOCK:
        parcial = RUN_STATE.get("partial", "")
        for caracter in fragmento:
            if caracter == "\r":
                continue
            if caracter == "\n":
                RUN_STATE["log"].append(parcial)
                parcial = ""
                continue

            parcial += caracter
            if len(parcial) >= 500:
                RUN_STATE["log"].append(parcial)
                parcial = ""

        RUN_STATE["partial"] = parcial


def estado_ejecucion():
    with RUN_LOCK:
        proceso = RUN_STATE.get("process")
        ejecutando = bool(proceso and proceso.poll() is None)
        inicio = RUN_STATE.get("started_monotonic")
        fin = RUN_STATE.get("finished_monotonic")

        if inicio is None:
            transcurrido = 0
        elif ejecutando:
            transcurrido = time.monotonic() - inicio
        elif fin is not None:
            transcurrido = fin - inicio
        else:
            transcurrido = 0

        log = list(RUN_STATE["log"])
        parcial = RUN_STATE.get("partial", "")
        if parcial:
            log.append(parcial)

        return {
            "running": ejecutando,
            "status": RUN_STATE["status"],
            "started_at": RUN_STATE["started_at"],
            "finished_at": RUN_STATE["finished_at"],
            "elapsed_seconds": round(transcurrido, 1),
            "returncode": RUN_STATE["returncode"],
            "log": log,
        }


def entorno_proyecto():
    entorno = os.environ.copy()
    entorno["PYTHONUNBUFFERED"] = "1"
    entorno["PYTHONIOENCODING"] = "utf-8"
    entorno["PW_TEST_SCREENSHOT_NO_FONTS_READY"] = "1"

    if LIBS_PATH.exists():
        ld_library_path = entorno.get("LD_LIBRARY_PATH", "")
        rutas = [str(LIBS_PATH)]
        if ld_library_path:
            rutas.append(ld_library_path)
        entorno["LD_LIBRARY_PATH"] = os.pathsep.join(rutas)

    return entorno


def leer_salida_proceso(proceso):
    try:
        while True:
            fragmento = proceso.stdout.read(1)
            if fragmento:
                agregar_salida(fragmento)
                continue

            if proceso.poll() is not None:
                break

            time.sleep(0.1)
    finally:
        codigo = proceso.wait()
        with RUN_LOCK:
            parcial = RUN_STATE.get("partial", "")
            if parcial:
                RUN_STATE["log"].append(parcial)
                RUN_STATE["partial"] = ""

            RUN_STATE["process"] = None
            RUN_STATE["returncode"] = codigo
            RUN_STATE["finished_at"] = ahora_texto()
            RUN_STATE["finished_monotonic"] = time.monotonic()

            if RUN_STATE["status"] == "stopping":
                RUN_STATE["status"] = "stopped"
            elif codigo == 0:
                RUN_STATE["status"] = "finished"
            else:
                RUN_STATE["status"] = "error"

            RUN_STATE["log"].append(
                f"[interfaz] Proceso finalizado con codigo {codigo}."
            )


def iniciar_ejecucion():
    configuracion = leer_configuracion()
    plataforma = configuracion.get("plataforma", "linkedin")
    definicion_plataforma = PLATAFORMAS[plataforma]
    script_path = definicion_plataforma["script"]

    if not script_path.exists():
        raise FileNotFoundError(f"No se encontro {script_path.name}.")

    with RUN_LOCK:
        proceso_actual = RUN_STATE.get("process")
        if proceso_actual and proceso_actual.poll() is None:
            raise EjecucionEnCurso("Ya hay una ejecucion en curso.")

        RUN_STATE.update(
            {
                "process": None,
                "status": "starting",
                "started_at": ahora_texto(),
                "started_monotonic": time.monotonic(),
                "finished_at": None,
                "finished_monotonic": None,
                "returncode": None,
                "log": deque(maxlen=600),
                "partial": "",
            }
        )

    python = PYTHON_VENV if PYTHON_VENV.exists() else Path(sys.executable)
    comando = [str(python), str(script_path)]
    kwargs = {
        "cwd": str(BASE_DIR),
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "env": entorno_proyecto(),
    }

    if os.name != "nt":
        kwargs["start_new_session"] = True

    try:
        proceso = subprocess.Popen(comando, **kwargs)
    except Exception:
        with RUN_LOCK:
            RUN_STATE["status"] = "error"
            RUN_STATE["finished_at"] = ahora_texto()
            RUN_STATE["finished_monotonic"] = time.monotonic()
        raise

    with RUN_LOCK:
        RUN_STATE["process"] = proceso
        RUN_STATE["status"] = "running"
        RUN_STATE["log"].append(
            f"[interfaz] Ejecucion iniciada: {definicion_plataforma['label']}."
        )

    hilo = threading.Thread(target=leer_salida_proceso, args=(proceso,), daemon=True)
    hilo.start()

    return estado_ejecucion()


def enviar_entrada_ejecucion(texto):
    with RUN_LOCK:
        proceso = RUN_STATE.get("process")
        if not proceso or proceso.poll() is not None:
            raise ValueError("No hay una ejecucion activa.")
        stdin = proceso.stdin

    if texto is None:
        texto = "\n"
    if texto == "":
        texto = "\n"

    try:
        stdin.write(texto)
        stdin.flush()
    except BrokenPipeError as exc:
        raise ValueError("El proceso ya no acepta entrada.") from exc

    etiqueta = "ENTER enviado" if texto == "\n" else "Entrada enviada"
    agregar_log(f"[interfaz] {etiqueta}.")
    return estado_ejecucion()


def forzar_detencion_si_sigue(proceso):
    time.sleep(8)
    if proceso.poll() is not None:
        return

    agregar_log("[interfaz] Forzando cierre del proceso.")
    try:
        if os.name != "nt":
            os.killpg(proceso.pid, signal.SIGKILL)
        else:
            proceso.kill()
    except ProcessLookupError:
        return


def detener_ejecucion():
    with RUN_LOCK:
        proceso = RUN_STATE.get("process")
        if not proceso or proceso.poll() is not None:
            raise ValueError("No hay una ejecucion activa.")

        RUN_STATE["status"] = "stopping"
        RUN_STATE["log"].append("[interfaz] Deteniendo ejecucion...")

    try:
        if os.name != "nt":
            os.killpg(proceso.pid, signal.SIGTERM)
        else:
            proceso.terminate()
    except ProcessLookupError:
        pass

    hilo = threading.Thread(target=forzar_detencion_si_sigue, args=(proceso,), daemon=True)
    hilo.start()

    return estado_ejecucion()


def limpiar_log_ejecucion():
    with RUN_LOCK:
        RUN_STATE["log"] = deque(maxlen=600)
        RUN_STATE["partial"] = ""

    return estado_ejecucion()


def respuesta_json(handler, datos, codigo=200):
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    handler.send_response(codigo)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(cuerpo)))
    handler.end_headers()
    handler.wfile.write(cuerpo)


def respuesta_texto(handler, texto, codigo=200, tipo="text/plain; charset=utf-8"):
    cuerpo = texto.encode("utf-8")
    handler.send_response(codigo)
    handler.send_header("Content-Type", tipo)
    handler.send_header("Content-Length", str(len(cuerpo)))
    handler.end_headers()
    handler.wfile.write(cuerpo)


def ejecuciones_disponibles():
    if not RESULTADOS_DIR.exists():
        return []

    ejecuciones = [
        ruta
        for ruta in RESULTADOS_DIR.iterdir()
        if ruta.is_dir() and ruta.name.startswith("ejecucion_")
    ]
    ejecuciones.sort(key=lambda ruta: ruta.stat().st_mtime, reverse=True)

    return ejecuciones


def obtener_ejecucion(nombre):
    if not nombre:
        ejecuciones = ejecuciones_disponibles()
        if not ejecuciones:
            raise FileNotFoundError("No hay ejecuciones disponibles.")
        return ejecuciones[0]

    ruta = (RESULTADOS_DIR / Path(nombre).name).resolve()
    resultados = RESULTADOS_DIR.resolve()

    if resultados not in ruta.parents or not ruta.is_dir():
        raise FileNotFoundError("Ejecucion no encontrada.")

    return ruta


def archivo_en_ejecucion(ejecucion, clave):
    if clave in ARCHIVOS_TABLAS:
        return ejecucion / ARCHIVOS_TABLAS[clave]

    mapa_archivos = {
        "publicaciones_linkedin": "publicaciones_linkedin.csv",
        "publicaciones_descartadas": "publicaciones_descartadas.csv",
        "conteo_por_banco": "conteo_por_banco.csv",
        "comparativo_banco_popular": "comparativo_banco_popular.csv",
        "tiempos_ejecucion": "tiempos_ejecucion.csv",
        "reporte_bancos": "reporte_bancos.xlsx",
    }

    if clave not in mapa_archivos:
        raise FileNotFoundError("Archivo no permitido.")

    return ejecucion / mapa_archivos[clave]


def numero(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0


def bancos_desde_parametros(params):
    if "banks" not in params:
        return None

    valor = params.get("banks", [""])[0]
    if not valor.strip():
        return []

    bancos = []
    for banco in valor.split(","):
        banco = banco.strip()
        if banco in BANCOS_OBJETIVO and banco not in bancos:
            bancos.append(banco)

    return bancos


def filtrar_filas_por_bancos(filas, bancos):
    if bancos is None:
        return filas

    bancos_set = set(bancos)
    return [
        fila
        for fila in filas
        if (fila.get("banco") or "").strip() in bancos_set
    ]


def filtrar_tabla_por_bancos(tabla, filas, bancos):
    if bancos is None:
        return filas

    if tabla == "tiempos":
        bancos_set = set(bancos)
        return [
            fila
            for fila in filas
            if fila.get("tipo_tiempo") == "busqueda"
            and (fila.get("banco") or "").strip() in bancos_set
        ]

    return filtrar_filas_por_bancos(filas, bancos)


def tiempos_por_banco(tiempos_busqueda):
    acumulados = {}

    for fila in tiempos_busqueda:
        banco = fila.get("banco") or "Sin banco"

        if banco not in acumulados:
            acumulados[banco] = {
                "banco": banco,
                "duracion_segundos": 0,
                "duracion_minutos": 0,
                "total_busquedas": 0,
                "publicaciones_relevantes": 0,
                "publicaciones_descartadas": 0,
                "resultados_total": 0,
            }

        acumulado = acumulados[banco]
        duracion = numero(fila.get("duracion_segundos"))
        acumulado["duracion_segundos"] += duracion
        acumulado["duracion_minutos"] = round(acumulado["duracion_segundos"] / 60, 2)
        acumulado["total_busquedas"] += 1
        acumulado["publicaciones_relevantes"] += int(numero(fila.get("publicaciones_relevantes")))
        acumulado["publicaciones_descartadas"] += int(numero(fila.get("publicaciones_descartadas")))
        acumulado["resultados_total"] += int(numero(fila.get("resultados_total")))

    return [
        {
            **fila,
            "duracion_segundos": round(fila["duracion_segundos"], 2),
        }
        for fila in acumulados.values()
    ]


def pain_label(clave):
    etiquetas = {
        "falsificacion": "Falsificación",
        "estafa": "Estafa",
        "robo_datos": "Robo de datos",
        "tarjeta": "Fraude con tarjeta",
        "transaccion_no_autorizada": "Transacción no autorizada",
        "contacto_no_oficial": "Contacto no oficial",
        "queja_bancaria_general": "Queja bancaria general",
        "servicio_tramite_bancario": "Servicio o trámite bancario",
        "sin_clasificar": "Casos por revisar",
        "sin_publicaciones": "Sin publicaciones",
    }

    return etiquetas.get(clave, clave or "Casos por revisar")


def resumen_dolor_cliente(publicaciones):
    total = len(publicaciones)

    if not publicaciones:
        return [
            {
                "grupo_modalidad": "sin_publicaciones",
                "modalidad_reportada": "Sin publicaciones",
                "dolor_cliente": "sin_publicaciones",
                "publicaciones": 0,
                "participacion_porcentaje": 0,
                "bancos_impactados": "",
                "palabras_detectadas": "",
            }
        ]

    acumulados = {}

    for fila in publicaciones:
        grupo = (fila.get("dolor_cliente") or "sin_clasificar").strip()
        modalidad = (
            fila.get("modalidad_especifica")
            or pain_label(grupo)
        ).strip()
        palabras = fila.get("palabras_dolor_detectadas") or ""

        if modalidad not in acumulados:
            acumulados[modalidad] = {
                "grupo_modalidad": grupo,
                "modalidad_reportada": modalidad,
                "dolor_cliente": grupo,
                "publicaciones": 0,
                "palabras": Counter(),
                "bancos": Counter(),
            }

        acumulados[modalidad]["publicaciones"] += 1
        acumulados[modalidad]["bancos"][fila.get("banco") or "Sin banco"] += 1

        for palabra in palabras.split(","):
            palabra = palabra.strip()
            if palabra:
                acumulados[modalidad]["palabras"][palabra] += 1

    resumen = []

    for acumulado in acumulados.values():
        publicaciones_categoria = acumulado["publicaciones"]
        resumen.append(
            {
                "grupo_modalidad": acumulado["grupo_modalidad"],
                "modalidad_reportada": acumulado["modalidad_reportada"],
                "dolor_cliente": acumulado["dolor_cliente"],
                "publicaciones": publicaciones_categoria,
                "participacion_porcentaje": round(
                    (publicaciones_categoria / total) * 100,
                    2,
                ),
                "bancos_impactados": ", ".join(
                    f"{banco} ({total_banco})"
                    for banco, total_banco in acumulado["bancos"].most_common()
                ),
                "palabras_detectadas": ", ".join(
                    palabra
                    for palabra, _ in acumulado["palabras"].most_common(8)
                ),
            }
        )

    return sorted(
        resumen,
        key=lambda fila: (-fila["publicaciones"], fila["modalidad_reportada"]),
    )


def resumen_ejecucion(ejecucion, bancos=None):
    publicaciones = leer_csv(ejecucion / "publicaciones_linkedin.csv")
    descartadas = leer_csv(ejecucion / "publicaciones_descartadas.csv")
    conteo = leer_csv(ejecucion / "conteo_por_banco.csv")
    comparativo = leer_csv(ejecucion / "comparativo_banco_popular.csv")
    tiempos = leer_csv(ejecucion / "tiempos_ejecucion.csv")
    tiempos_busqueda = [
        fila for fila in tiempos if fila.get("tipo_tiempo") == "busqueda"
    ]

    publicaciones = filtrar_filas_por_bancos(publicaciones, bancos)
    descartadas = filtrar_filas_por_bancos(descartadas, bancos)
    conteo = filtrar_filas_por_bancos(conteo, bancos)
    comparativo = filtrar_filas_por_bancos(comparativo, bancos)
    tiempos_busqueda = filtrar_filas_por_bancos(tiempos_busqueda, bancos)

    bancos_con_resultados = sum(1 for fila in conteo if numero(fila.get("publicaciones")) > 0)
    duracion_total_segundos = round(
        sum(numero(fila.get("duracion_segundos")) for fila in tiempos_busqueda),
        2,
    )
    archivos = {
        "publicaciones_linkedin": (ejecucion / "publicaciones_linkedin.csv").exists(),
        "publicaciones_descartadas": (ejecucion / "publicaciones_descartadas.csv").exists(),
        "conteo_por_banco": (ejecucion / "conteo_por_banco.csv").exists(),
        "comparativo_banco_popular": (ejecucion / "comparativo_banco_popular.csv").exists(),
        "tiempos_ejecucion": (ejecucion / "tiempos_ejecucion.csv").exists(),
        "reporte_bancos": (ejecucion / "reporte_bancos.xlsx").exists(),
    }

    return {
        "ejecucion": ejecucion.name,
        "publicaciones": len(publicaciones),
        "descartadas": len(descartadas),
        "conteo": conteo,
        "comparativo": comparativo,
        "tiempos_busqueda": tiempos_busqueda,
        "tiempos_banco": tiempos_por_banco(tiempos_busqueda),
        "dolor_cliente": resumen_dolor_cliente(publicaciones),
        "bancos_con_resultados": bancos_con_resultados,
        "duracion_total_segundos": duracion_total_segundos,
        "duracion_total_minutos": round(duracion_total_segundos / 60, 2),
        "total_busquedas": len(tiempos_busqueda),
        "archivos": archivos,
    }


def ruta_imagen_segura(ejecucion, valor):
    if not valor:
        raise FileNotFoundError("Imagen no indicada.")

    ruta = Path(unquote(valor))
    if not ruta.is_absolute():
        ruta = BASE_DIR / ruta

    ruta = ruta.resolve()
    ejecucion_resuelta = ejecucion.resolve()

    if ejecucion_resuelta not in ruta.parents:
        raise FileNotFoundError("Imagen fuera de la ejecucion.")

    if not ruta.exists() or not ruta.is_file():
        raise FileNotFoundError("Imagen no encontrada.")

    return ruta


class InterfazHandler(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):
        return

    def do_GET(self):
        try:
            self.rutar_get()
        except FileNotFoundError as exc:
            respuesta_json(self, {"error": str(exc)}, 404)
        except ValueError as exc:
            respuesta_json(self, {"error": str(exc)}, 400)
        except Exception as exc:
            respuesta_json(self, {"error": str(exc)}, 500)

    def do_POST(self):
        try:
            self.rutar_post()
        except FileNotFoundError as exc:
            respuesta_json(self, {"error": str(exc)}, 404)
        except EjecucionEnCurso as exc:
            respuesta_json(self, {"error": str(exc)}, 409)
        except ValueError as exc:
            respuesta_json(self, {"error": str(exc)}, 400)
        except Exception as exc:
            respuesta_json(self, {"error": str(exc)}, 500)

    def rutar_get(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/":
            respuesta_texto(self, HTML, tipo="text/html; charset=utf-8")
            return

        if parsed.path == "/api/executions":
            ejecuciones = [
                {
                    "name": ruta.name,
                    "mtime": ruta.stat().st_mtime,
                }
                for ruta in ejecuciones_disponibles()
            ]
            respuesta_json(self, {"executions": ejecuciones})
            return

        if parsed.path == "/api/config":
            respuesta_json(self, leer_configuracion())
            return

        if parsed.path == "/api/run/status":
            respuesta_json(self, estado_ejecucion())
            return

        if parsed.path == "/assets/logo":
            if not RUTA_LOGO.exists():
                raise FileNotFoundError("Logo no encontrado.")

            cuerpo = RUTA_LOGO.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        ejecucion = obtener_ejecucion(params.get("exec", [""])[0])

        if parsed.path == "/api/summary":
            respuesta_json(
                self,
                resumen_ejecucion(ejecucion, bancos_desde_parametros(params)),
            )
            return

        if parsed.path == "/api/table":
            tabla = params.get("table", ["publicaciones"])[0]
            ruta = archivo_en_ejecucion(ejecucion, tabla)
            filas = filtrar_tabla_por_bancos(
                tabla,
                leer_csv(ruta),
                bancos_desde_parametros(params),
            )
            respuesta_json(self, {"rows": filas})
            return

        if parsed.path == "/api/file":
            clave = params.get("file", [""])[0]
            ruta = archivo_en_ejecucion(ejecucion, clave)

            if not ruta.exists():
                raise FileNotFoundError("Archivo no encontrado.")

            tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
            cuerpo = ruta.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{quote(ruta.name)}"',
            )
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        if parsed.path == "/api/image":
            ruta = ruta_imagen_segura(ejecucion, params.get("path", [""])[0])
            tipo = mimetypes.guess_type(ruta.name)[0] or "image/png"
            cuerpo = ruta.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        raise FileNotFoundError("Ruta no encontrada.")

    def rutar_post(self):
        parsed = urlparse(self.path)

        longitud = int(self.headers.get("Content-Length", "0") or 0)
        cuerpo = self.rfile.read(longitud).decode("utf-8")
        datos = json.loads(cuerpo or "{}")

        if parsed.path == "/api/config":
            respuesta_json(self, guardar_configuracion(datos))
            return

        if parsed.path == "/api/run/start":
            respuesta_json(self, iniciar_ejecucion(), 202)
            return

        if parsed.path == "/api/run/input":
            respuesta_json(self, enviar_entrada_ejecucion(datos.get("text", "\n")))
            return

        if parsed.path == "/api/run/stop":
            respuesta_json(self, detener_ejecucion())
            return

        if parsed.path == "/api/run/log/clear":
            respuesta_json(self, limpiar_log_ejecucion())
            return

        raise FileNotFoundError("Ruta no encontrada.")


def main():
    servidor = None
    puerto = PORT

    for candidato in range(PORT, PORT_MAX + 1):
        try:
            servidor = ThreadingHTTPServer((HOST, candidato), InterfazHandler)
            puerto = candidato
            break
        except OSError:
            continue

    if servidor is None:
        servidor = ThreadingHTTPServer((HOST, 0), InterfazHandler)
        puerto = servidor.server_address[1]

    print(f"Interfaz disponible en http://{HOST}:{puerto}")
    print("Presiona Ctrl+C para detener el servidor.")
    servidor.serve_forever()


if __name__ == "__main__":
    main()

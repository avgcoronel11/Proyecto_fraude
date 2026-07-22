# LINDA - Documentacion tecnica y operativa

Fecha de documentacion: 2026-07-21

## 1. Resumen ejecutivo

LINDA es una herramienta local para monitorear publicaciones visibles en redes
sociales relacionadas con posibles denuncias de fraude bancario en Colombia. El
proyecto permite configurar una red social, un rango de fechas, bancos objetivo
y limites de recoleccion. Luego ejecuta un bot semiautomatico con Playwright,
clasifica publicaciones o comentarios, genera resultados en archivos locales y
muestra un dashboard con metricas, tablas, graficas y evidencias visuales.

El proyecto esta pensado para operar en una estacion de trabajo controlada. No
publica informacion en internet, no expone una API externa y no requiere una
base de datos. Los datos quedan en carpetas locales bajo `resultados/`.

## 2. Objetivo del proyecto

El objetivo es construir una muestra auditada de publicaciones visibles que
contengan senales de denuncia o posible fraude bancario asociado a bancos
seleccionados. El resultado sirve para comparar volumen de denuncias directas,
modalidades reportadas, tiempos de ejecucion, publicaciones descartadas y
evidencias visuales.

El proyecto no mide todo el fraude real del sistema financiero. Mide hallazgos
visibles bajo reglas de busqueda, fechas, bancos y relevancia configuradas.

## 3. Alcance funcional

- Ejecutar monitoreo en LinkedIn, Instagram y Facebook.
- Configurar red, fechas, bancos y limites desde una interfaz local.
- Leer credenciales desde `.env` sin exponerlas en el codigo.
- Abrir navegador Chromium con Playwright.
- Permitir login o verificacion manual cuando la red lo solicite.
- Extraer publicaciones, comentarios, fechas visibles, metricas y URL.
- Clasificar contenido relevante y descartado.
- Guardar CSV, Excel, metadata y capturas por ejecucion.
- Mostrar resumen, graficas y tablas en un dashboard local.
- Exportar un dashboard estatico para entrega sin Python ni servidor.
- Generar un Excel consolidado por red para reducir archivos entregables.

## 4. Redes soportadas

LinkedIn usa busquedas por banco y terminos relacionados con fraude. Para cada
banco seleccionado se construyen consultas como fraude, estafa y denuncia junto
al nombre del banco.

Instagram y Facebook usan una estrategia distinta. Entran al perfil oficial del
banco, revisan publicaciones dentro del rango y leen comentarios publicos. Una
publicacion se cuenta como denuncia cuando contiene al menos un comentario
publico con senales de fraude o denuncia bancaria.

## 5. Arquitectura general

La arquitectura es local y por archivos:

- Interfaz local: `interfaz.py`.
- Bots de recoleccion: `proyecto.py`, `instagram_bot.py`, `facebook_bot.py`.
- Logica compartida para redes sociales: `social_media_bot.py`.
- Configuracion: `configuracion_busqueda.json`.
- Secretos locales: `.env`.
- Resultados: `resultados/ejecucion_*`.
- Exportacion estatica: `dashboard_exportado/`.
- Documentacion: `README.md` y `docs/`.

No hay servidor remoto, base de datos, colas, contenedores ni servicios cloud
obligatorios. La interfaz corre en `127.0.0.1`.

## 6. Estructura de archivos

`interfaz.py`: levanta el dashboard local, guarda configuracion, lanza bots como
subprocesos, lee resultados y sirve endpoints internos para graficas, tablas,
capturas y descargas.

`proyecto.py`: contiene el bot de LinkedIn, reglas de relevancia, normalizacion
de fechas/textos, captura de evidencias, escritura de CSV, generacion de Excel
y metadata de ejecucion.

`social_media_bot.py`: contiene funciones comunes para Instagram y Facebook:
login generico, navegacion por perfiles, deteccion de publicaciones, lectura de
comentarios, validacion de URL, captura de evidencia y guardado final usando el
motor de `proyecto.py`.

`instagram_bot.py`: define credenciales requeridas, URL de login, perfiles
oficiales y patrones de publicaciones para Instagram.

`facebook_bot.py`: define credenciales requeridas, URL de login, perfiles
oficiales y patrones de publicaciones para Facebook.

`exportar_dashboard.py`: consolida ejecuciones del mismo rango de fechas y
genera una carpeta estatica con dashboard, capturas y un unico Excel llamado
`consolidado_por_red.xlsx`.

`configuracion_busqueda.json`: archivo editable con plataforma, rango de fechas,
limites, filtros y bancos seleccionados.

`.env`: archivo local de credenciales. Debe existir en cada equipo donde se
ejecute el bot y no debe subirse a Git.

## 7. Flujo de ejecucion

1. El usuario ejecuta `interfaz.py`.
2. La interfaz abre un servidor local en `http://127.0.0.1:8000`.
3. El usuario selecciona red, fechas, bancos y limites.
4. La interfaz guarda la configuracion en `configuracion_busqueda.json`.
5. La interfaz lanza el script correspondiente a la red seleccionada.
6. El bot crea una carpeta en `resultados/` identificada por red y fecha.
7. El bot carga credenciales desde `.env`.
8. Playwright abre Chromium con un perfil local persistente.
9. El usuario completa verificaciones manuales si la red las solicita.
10. El bot recolecta publicaciones o comentarios visibles.
11. El bot filtra por fecha y relevancia.
12. El bot guarda resultados, capturas, metadata y reporte.
13. La interfaz lee los archivos generados y actualiza el dashboard.

## 8. Nombres de carpetas de ejecucion

Las nuevas ejecuciones quedan identificadas por red:

- `resultados/ejecucion_linkedin_DD-MM-AAAA_HH-MM-SS`
- `resultados/ejecucion_instagram_DD-MM-AAAA_HH-MM-SS`
- `resultados/ejecucion_facebook_DD-MM-AAAA_HH-MM-SS`

Las carpetas antiguas con formato `ejecucion_DD-MM-AAAA_HH-MM-SS` siguen siendo
compatibles. El dashboard infiere la red desde metadata, nombre de carpeta o
contenido de los archivos.

## 9. Configuracion

El archivo `configuracion_busqueda.json` controla:

- `plataforma`: `linkedin`, `instagram` o `facebook`.
- `fecha_inicio`: fecha inicial en formato `AAAA-MM-DD`.
- `fecha_fin`: fecha final en formato `AAAA-MM-DD`.
- `max_publicaciones_por_busqueda`: limite por consulta de LinkedIn.
- `max_publicaciones_por_banco`: limite por perfil para Instagram/Facebook.
- `max_comentarios_por_publicacion`: limite de comentarios por publicacion.
- `leer_respuestas_comentarios`: reservado para ampliar profundidad de lectura.
- `filtrar_por_fecha`: excluye contenido fuera del rango configurado.
- `filtrar_por_relevancia`: aplica reglas de denuncia/fraude.
- `guardar_descartadas`: conserva auditoria de contenido descartado.
- `bancos_seleccionados`: bancos que se ejecutan y se muestran en dashboard.

## 10. Credenciales

Las credenciales se leen desde `.env`. Variables esperadas:

```text
LINKEDIN_USUARIO=...
LINKEDIN_CONTRASENA=...
INSTAGRAM_USUARIO=...
INSTAGRAM_CONTRASENA=...
FACEBOOK_USUARIO=...
FACEBOOK_CONTRASENA=...
```

El archivo `.env` esta ignorado por Git. En consola se imprimen valores
enmascarados para evitar exponer usuario o contrasena.

## 11. Reglas de relevancia

El motor busca senales de:

- fraude;
- estafa;
- robo;
- suplantacion;
- phishing, vishing o smishing;
- movimientos no reconocidos;
- transferencias no autorizadas;
- tarjetas, claves, codigos, PSE, QR, app o cuenta bancaria;
- expresiones de denuncia directa como fui victima, me robaron o no autorice.

El filtro descarta contenido cuando:

- no menciona el banco objetivo;
- no hay senales de fraude o denuncia;
- el texto es educativo o preventivo sin caso concreto;
- el texto es comercial, promocional o no bancario;
- el contenido queda fuera del rango de fechas configurado.

Las descartadas se guardan para auditoria si `guardar_descartadas` esta activo.

## 12. Salidas por ejecucion

Cada carpeta de ejecucion puede contener:

- `publicaciones_linkedin.csv`: publicaciones relevantes. El nombre se conserva
  por compatibilidad aunque la ejecucion sea de Instagram o Facebook.
- `publicaciones_descartadas.csv`: contenido descartado y motivo.
- `conteo_por_banco.csv`: conteo de publicaciones relevantes por banco.
- `comparativo_banco_popular.csv`: comparativo frente a Banco Popular Colombia.
- `tiempos_ejecucion.csv`: tiempos por busqueda, banco o perfil.
- `reporte_bancos.xlsx`: reporte Excel de esa ejecucion.
- `metadata.json`: configuracion, red, fechas, bancos y estado.
- `capturas_publicaciones/`: capturas PNG para evidencia visual.

## 13. Dashboard local

El dashboard permite:

- editar configuracion;
- iniciar y detener ejecuciones;
- ver log en tiempo real;
- enviar ENTER o codigos cuando la red pida verificacion;
- seleccionar ejecuciones historicas;
- filtrar por banco y red;
- revisar publicaciones, descartadas, conteos, comparativos y tiempos;
- abrir capturas de evidencia;
- descargar archivos de la ejecucion.

La interfaz usa `http.server` de Python para evitar dependencias como Flask,
Django o FastAPI.

## 14. Dashboard estatico exportado

`exportar_dashboard.py` genera una carpeta que se puede entregar a otra persona
sin instalar Python. La exportacion incluye:

- `index.html`;
- `abrir_dashboard.bat`;
- `datos.json`;
- `assets/LINDA.png`;
- `capturas/`;
- `archivos/consolidado_por_red.xlsx`.

El HTML permite filtrar por `Todas las redes`, `Facebook`, `LinkedIn` e
`Instagram`. El Excel consolidado contiene hojas de resumen, red, publicaciones,
descartadas y tiempos.

## 15. Requisitos tecnicos

Requisitos principales:

- Python 3 con entorno virtual.
- Playwright instalado.
- Chromium administrado por Playwright.
- Acceso de red a LinkedIn, Instagram o Facebook segun aplique.
- Permiso de escritura local en la carpeta del proyecto.
- Navegador permitido por las politicas del equipo.

En Windows restringido se debe validar con seguridad:

- ejecucion de `python.exe`;
- ejecucion del navegador Chromium de Playwright;
- lectura de `.env`;
- escritura en `resultados/`, `dashboard_exportado/` y perfiles Chromium;
- acceso HTTPS a las redes sociales usadas;
- descarga o instalacion previa de dependencias si el equipo no tiene internet.

## 16. Instalacion base

Crear o activar entorno virtual:

```bash
python -m venv .venv
```

Instalar Playwright:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
```

En Windows el ejecutable equivalente suele estar en:

```text
.venv\Scripts\python.exe
```

## 17. Ejecucion recomendada

Levantar dashboard:

```bash
.venv/bin/python interfaz.py
```

Generar exportacion estatica:

```bash
.venv/bin/python exportar_dashboard.py --output dashboard_exportado/dashboard_consolidado_redes
```

Abrir resultado exportado en Windows:

```text
dashboard_exportado\dashboard_consolidado_redes\abrir_dashboard.bat
```

## 18. Consideraciones de seguridad

- No subir `.env` a Git.
- No compartir credenciales en capturas, documentos o tickets.
- No guardar datos sensibles innecesarios de personas.
- Mantener la recoleccion limitada a contenido visible para la cuenta usada.
- Usar cuentas autorizadas por la entidad.
- Revisar terminos y politicas internas antes de automatizar redes sociales.
- Entregar preferiblemente el dashboard estatico y no credenciales.

## 19. Limitaciones conocidas

- Las redes sociales cambian su HTML y pueden romper selectores.
- LinkedIn, Instagram y Facebook pueden pedir verificacion manual.
- Las fechas visibles pueden ser relativas o incompletas.
- El conteo depende del contenido visible para la cuenta usada.
- Algunas publicaciones pueden no exponer URL, metricas o comentarios completos.
- La clasificacion es por reglas y requiere auditoria humana en casos sensibles.

## 20. Mantenimiento

Para mantener el proyecto:

- revisar selectores cuando una red cambie su interfaz;
- auditar `publicaciones_descartadas.csv` para mejorar reglas;
- mantener perfiles oficiales de bancos actualizados;
- validar que el Excel consolidado conserve columnas esperadas;
- ejecutar pruebas de sintaxis antes de entregar cambios;
- no versionar salidas generadas ni credenciales.

## 21. Codigo documentado

El codigo principal incluye docstrings de modulo en `interfaz.py`, `proyecto.py`,
`social_media_bot.py`, `instagram_bot.py`, `facebook_bot.py` y
`exportar_dashboard.py`. Tambien se agregaron docstrings en funciones clave de
exportacion y creacion de carpetas para explicar decisiones operativas como:

- seleccion de ejecucion por defecto;
- agrupacion de ejecuciones por rango de fechas;
- generacion de Excel consolidado;
- exportacion estatica;
- identificacion de carpetas por red social.

## 22. Entregables documentales

Los entregables de documentacion son:

- `README.md`: guia rapida del repositorio.
- `docs/Documentacion_Proyecto_LINDA.md`: documentacion fuente editable.
- `docs/Documentacion_Proyecto_LINDA.docx`: documento Word para entrega.
- `docs/generar_documentacion_word.py`: generador reproducible del Word.

# LINDA - Monitoreo de fraude bancario en redes sociales

LINDA es un dashboard local y conjunto de bots semiautomaticos para recolectar,
clasificar y consolidar publicaciones visibles relacionadas con posibles
denuncias de fraude bancario en Colombia.

El proyecto trabaja con tres redes:

- LinkedIn: busqueda por banco y palabras clave.
- Instagram: revision de perfiles oficiales y comentarios publicos.
- Facebook: revision de perfiles oficiales y comentarios publicos.

## Entradas principales

- `interfaz.py`: dashboard local para configurar, ejecutar y consultar resultados.
- `proyecto.py`: bot principal de LinkedIn y motor comun de reporte.
- `social_media_bot.py`: logica compartida para Instagram y Facebook.
- `instagram_bot.py`: definicion de perfiles y login de Instagram.
- `facebook_bot.py`: definicion de perfiles y login de Facebook.
- `exportar_dashboard.py`: genera un dashboard estatico entregable con un Excel consolidado.
- `configuracion_busqueda.json`: parametros de red, fechas, limites, filtros y bancos.
- `.env`: credenciales locales. No debe subirse a Git.

## Ejecucion local

```bash
.venv/bin/python interfaz.py
```

Despues abre:

```text
http://127.0.0.1:8000
```

Desde el dashboard se configura la red, el rango de fechas, los bancos y los
limites de recoleccion. Luego se inicia el bot desde la interfaz.

## Exportacion para entrega

```bash
.venv/bin/python exportar_dashboard.py --output dashboard_exportado/dashboard_consolidado_redes
```

La carpeta generada se puede entregar como resultado estatico. Incluye:

- `index.html`: dashboard sin servidor.
- `abrir_dashboard.bat`: abre el HTML en Windows.
- `datos.json`: datos usados por el dashboard.
- `archivos/consolidado_por_red.xlsx`: unico Excel consolidado por red.
- `capturas/`: evidencias visuales cuando existen.

## Documentacion

La documentacion completa esta en:

- `docs/Documentacion_Proyecto_LINDA.md`
- `docs/Documentacion_Proyecto_LINDA.docx`
- `docs/Requerimientos_Windows_Sector_Bancario.md`
- `docs/Requerimientos_Windows_Sector_Bancario.docx`

Para regenerar el Word desde la fuente Markdown:

```bash
.venv/bin/python docs/generar_documentacion_word.py
.venv/bin/python docs/generar_documentacion_word.py docs/Requerimientos_Windows_Sector_Bancario.md -o docs/Requerimientos_Windows_Sector_Bancario.docx
```

## Seguridad

El proyecto no debe almacenar credenciales en codigo. Las claves se cargan desde
`.env`, archivo excluido de Git. En equipos restringidos se debe solicitar
permiso para ejecutar Python, Playwright/Chromium, lectura y escritura local en
la carpeta del proyecto, y acceso web a las redes que se vayan a monitorear.

# Requerimientos para ejecutar o entregar LINDA en equipo Windows bancario

Fecha: 2026-07-21

## 1. Objetivo de esta lista

Esta lista resume los accesos, permisos y validaciones que se deben solicitar
antes de pasar el proyecto LINDA a un equipo Windows de una entidad bancaria.
Se separan dos escenarios porque tienen niveles de riesgo y permisos muy
distintos:

- Escenario A: solo visualizar resultados exportados.
- Escenario B: ejecutar el bot completo y recolectar datos desde redes sociales.

La recomendacion para ambientes altamente restringidos es aprobar primero el
Escenario A. El Escenario B requiere mas permisos porque usa Python, Playwright,
Chromium, credenciales y acceso web a redes sociales.

## 2. Escenario A - Solo visualizar dashboard exportado

Este escenario no ejecuta el bot. Solo permite abrir el resultado ya generado.
Es el modo recomendado si el equipo del banco solo necesita revisar el dashboard
del mes.

### 2.1 Archivos a entregar

- Carpeta exportada completa, por ejemplo `dashboard_consolidado_redes`.
- `index.html`.
- `abrir_dashboard.bat`.
- `datos.json`.
- `assets/LINDA.png`.
- `archivos/consolidado_por_red.xlsx`.
- `capturas/`, si existen evidencias visuales.

### 2.2 Permisos requeridos

- Permiso para copiar una carpeta local al equipo.
- Permiso para abrir archivos `.html` locales en navegador.
- Permiso para abrir archivos `.xlsx` en Microsoft Excel o visor autorizado.
- Permiso para abrir imagenes `.png` locales.
- Permiso opcional para ejecutar `abrir_dashboard.bat`.

Si los `.bat` estan bloqueados, no es critico. Se puede abrir directamente
`index.html`.

### 2.3 Acceso a internet requerido

No requiere internet. El dashboard exportado es estatico.

### 2.4 Software requerido

- Microsoft Edge, Google Chrome o navegador corporativo equivalente.
- Microsoft Excel o visor aprobado para `.xlsx`.

No requiere Python, Playwright, Git ni credenciales.

### 2.5 Solicitud sugerida a TI

Solicitar autorizacion para abrir un dashboard HTML local sin conexion externa,
junto con un Excel `.xlsx` sin macros y capturas `.png` asociadas. El archivo
`.bat` solo abre el `index.html`; si no se permite, se abrira el HTML de forma
manual.

## 3. Escenario B - Ejecutar el bot completo en Windows

Este escenario permite ejecutar la recoleccion desde el equipo Windows. Requiere
mas controles porque automatiza navegador y accede a redes sociales.

## 4. Requisitos de sistema operativo

- Windows 10 u 11 de 64 bits.
- Usuario de dominio autorizado para ejecutar herramientas locales.
- Carpeta aprobada para ubicar el proyecto, por ejemplo:
  `C:\Usuarios\<usuario>\Documentos\LINDA` o ruta definida por TI.
- Permiso de lectura y escritura sobre la carpeta del proyecto.
- Permiso de escritura sobre subcarpetas generadas:
  - `resultados\`
  - `dashboard_exportado\`
  - `.perfil_chromium_linkedin\`
  - `.perfil_chromium_instagram\`
  - `.perfil_chromium_facebook\`
  - `.venv\`, si el entorno virtual se crea dentro del proyecto.

## 5. Requisitos de Python

Solicitar una de estas opciones:

- Python 3.11 o superior instalado por TI.
- Python portable aprobado por TI.
- Entorno virtual `.venv` preparado y aprobado previamente.

Permisos necesarios:

- Ejecutar `python.exe`.
- Crear o usar entorno virtual.
- Ejecutar `.venv\Scripts\python.exe`.
- Ejecutar scripts `.py` del proyecto.

Comandos esperados:

```text
python -m venv .venv
.venv\Scripts\python.exe interfaz.py
.venv\Scripts\python.exe exportar_dashboard.py
```

## 6. Dependencias Python

El codigo usa principalmente librerias estandar de Python. La dependencia
externa directa es Playwright.

Dependencias detectadas en el entorno actual:

- `playwright==1.60.0`
- `greenlet==3.5.1`
- `pyee==13.0.1`
- `typing_extensions==4.15.0`

Si el equipo no tiene internet, solicitar aprobacion para instalacion offline
desde paquetes `.whl` revisados por TI.

## 7. Playwright y navegador Chromium

El bot usa Playwright para abrir un navegador Chromium y automatizar la
navegacion. En entidades bancarias esto suele requerir allowlist explicita.

Solicitar permiso para ejecutar:

- `.venv\Scripts\playwright.exe`, si existe.
- `.venv\Lib\site-packages\playwright\driver\node.exe`.
- Chromium instalado por Playwright, usualmente en:
  `%USERPROFILE%\AppData\Local\ms-playwright\chromium-*\chrome-win\chrome.exe`.

Si TI no permite ejecutables bajo `%USERPROFILE%`, solicitar una ruta corporativa
aprobada para los navegadores de Playwright o evaluar uso de Microsoft Edge
corporativo con configuracion adicional.

## 8. Permisos de red

Para visualizar dashboard exportado no se requiere red. Para ejecutar el bot si
se requiere salida HTTPS por puerto 443 a las redes que se monitoreen.

### 8.1 LinkedIn

Solicitar acceso HTTPS a:

- `https://www.linkedin.com`
- `https://linkedin.com`
- dominios estaticos de LinkedIn necesarios para cargar la pagina, por ejemplo
  `*.licdn.com`

### 8.2 Instagram

Solicitar acceso HTTPS a:

- `https://www.instagram.com`
- dominios de contenido necesarios para imagenes y scripts, por ejemplo
  `*.cdninstagram.com`

### 8.3 Facebook

Solicitar acceso HTTPS a:

- `https://www.facebook.com`
- `https://web.facebook.com`
- dominios de contenido necesarios, por ejemplo `*.fbcdn.net`

La lista final debe validarla TI con el proxy corporativo, porque las redes
pueden cargar recursos desde dominios adicionales.

## 9. Proxy, certificado corporativo e inspeccion TLS

Si el banco usa proxy o inspeccion TLS:

- Confirmar si Python y Playwright deben usar `HTTP_PROXY` y `HTTPS_PROXY`.
- Confirmar si Chromium necesita configuracion especial de proxy.
- Confirmar instalacion del certificado raiz corporativo.
- Excluir de proxy el loopback local:
  `NO_PROXY=127.0.0.1,localhost`.
- Validar que la inspeccion TLS no rompa login, recursos estaticos o sesiones.

## 10. Dashboard local y puertos

La interfaz local usa `127.0.0.1` y puertos entre `8000` y `8099`.

Solicitar:

- Permitir bind local en `127.0.0.1:8000-8099`.
- Permitir que el navegador del mismo equipo abra `http://127.0.0.1:8000`.
- No se requiere exponer puertos a la red corporativa.
- No se requiere regla inbound desde otros equipos.

## 11. Credenciales y cuentas

Se requiere definir cuentas autorizadas para cada red que se vaya a ejecutar:

- LinkedIn.
- Instagram.
- Facebook.

Solicitar a Seguridad/Negocio:

- Aprobacion de uso de cuentas para monitoreo.
- Manejo de doble factor o verificacion manual.
- Definir si las credenciales se guardan en `.env` local o en un mecanismo
  aprobado por la entidad.
- Confirmar responsable de custodia de credenciales.

Variables requeridas en `.env`:

```text
LINKEDIN_USUARIO=...
LINKEDIN_CONTRASENA=...
INSTAGRAM_USUARIO=...
INSTAGRAM_CONTRASENA=...
FACEBOOK_USUARIO=...
FACEBOOK_CONTRASENA=...
```

El archivo `.env` no debe subirse a Git ni compartirse por correo.

## 12. Permisos sobre archivos generados

El proyecto genera archivos locales:

- CSV.
- XLSX.
- JSON.
- PNG.
- HTML.
- BAT.

Solicitar que DLP/antivirus permita escribir en:

- `resultados\`
- `dashboard_exportado\`
- `capturas_publicaciones\`

El Excel generado no contiene macros. El `.bat` de exportacion solo abre el
archivo `index.html`.

## 13. Git o forma de transferencia

Si el equipo Windows va a recibir codigo fuente:

- Solicitar Git instalado o aprobado.
- Solicitar acceso al repositorio autorizado.
- Si GitHub esta bloqueado, usar repositorio interno o paquete `.zip` validado.

Si solo se entregan resultados:

- No se requiere Git.
- Entregar carpeta exportada comprimida y validada.

## 14. Antivirus, EDR y controles de ejecucion

Solicitar revision o allowlist para:

- `python.exe`.
- `.venv\Scripts\python.exe`.
- `node.exe` usado internamente por Playwright.
- `chrome.exe` de Playwright.
- Escritura de capturas `.png`.
- Creacion de carpetas de perfil Chromium.
- Automatizacion de navegador por Playwright.

Estos controles pueden bloquear la ejecucion aunque Python este instalado.

## 15. Politica de datos y cumplimiento

Antes de ejecutar el bot, confirmar:

- Que se permite recolectar contenido visible de redes sociales.
- Que se permite almacenar textos y capturas de publicaciones/comentarios.
- Donde deben almacenarse los resultados.
- Tiempo de retencion de los archivos.
- Clasificacion de confidencialidad del output.
- Responsable de revisar y depurar datos personales si aplica.

## 16. Recomendacion de implementacion por fases

Fase 1: Validar visualizacion estatica.

- Entregar `dashboard_consolidado_redes`.
- Abrir `index.html`.
- Abrir `consolidado_por_red.xlsx`.
- No solicitar Python, Playwright ni credenciales.

Fase 2: Validar ejecucion controlada en equipo de pruebas.

- Instalar Python aprobado.
- Instalar dependencias offline o por repositorio interno.
- Permitir Playwright/Chromium.
- Usar cuentas de prueba o cuentas autorizadas.
- Ejecutar una red y un rango corto.

Fase 3: Operacion mensual.

- Definir responsable de ejecucion.
- Definir carpeta de salida.
- Definir proceso de entrega del dashboard exportado.
- Definir retencion y eliminacion de resultados.

## 17. Checklist de solicitud a TI/Seguridad

- Aprobar si el alcance sera solo visualizacion o ejecucion completa.
- Aprobar ubicacion local del proyecto.
- Aprobar ejecucion de Python.
- Aprobar entorno virtual `.venv`.
- Aprobar instalacion o transferencia offline de Playwright.
- Aprobar ejecucion de Chromium/Playwright.
- Aprobar acceso HTTPS a redes sociales necesarias.
- Configurar proxy/certificado corporativo si aplica.
- Permitir loopback `127.0.0.1:8000-8099`.
- Aprobar escritura de resultados CSV/XLSX/JSON/PNG/HTML.
- Definir manejo de credenciales y doble factor.
- Validar DLP/antivirus/EDR.
- Definir repositorio Git interno o transferencia por ZIP.
- Definir retencion y clasificacion de datos generados.

## 18. Requerimiento minimo recomendado

Para una primera aprobacion bancaria, solicitar solo:

- Abrir carpeta estatica exportada.
- Abrir `index.html` local.
- Abrir `consolidado_por_red.xlsx`.
- Abrir capturas `.png`.

Esto permite revisar resultados sin ejecutar codigo, sin credenciales y sin
conexion a redes sociales.

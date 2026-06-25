"""
Bot semiautomatico para Instagram.

Usa la misma configuracion y salida que LinkedIn, pero con credenciales y perfil
de navegador propios. Requiere agregar al archivo .env:

    INSTAGRAM_USUARIO=...
    INSTAGRAM_CONTRASENA=...

La automatizacion es conservadora: abre Instagram, permite login/verificacion
manual, entra al perfil oficial de cada banco y revisa comentarios publicos en
publicaciones del rango configurado.
"""

from social_media_bot import ejecutar_bot_red


DEFINICION_INSTAGRAM = {
    "nombre": "instagram",
    "nombre_visible": "Instagram",
    "usuario_env": "INSTAGRAM_USUARIO",
    "contrasena_env": "INSTAGRAM_CONTRASENA",
    "login_url": "https://www.instagram.com/accounts/login/",
    "perfiles": {
        "Banco Popular Colombia": "https://www.instagram.com/bcopopular/",
        "Banco Davivienda": "https://www.instagram.com/davivienda/",
        "Bancolombia": "https://www.instagram.com/bancolombia/",
        "Banco de Bogotá": "https://www.instagram.com/bancodebogota/",
        "BBVA Colombia": "https://www.instagram.com/bbva_colombia/",
        "Banco Agrario de Colombia": "https://www.instagram.com/bancoagrario/",
        "Banco de Occidente": "https://www.instagram.com/bco_occidente/",
        "Banco AV Villas": "https://www.instagram.com/avvillas/",
        "Banco Caja Social": "https://www.instagram.com/bancocajasocial/",
    },
    "patrones_url_publicacion": [
        r"instagram\.com/(?:[^/]+/)?p/",
        r"instagram\.com/(?:[^/]+/)?reel/",
        r"instagram\.com/(?:[^/]+/)?tv/",
    ],
    "selectores_comentario": [
        "article ul li",
        "ul li",
        "div[role='button']",
        "span",
    ],
}


if __name__ == "__main__":
    ejecutar_bot_red(DEFINICION_INSTAGRAM)

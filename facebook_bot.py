"""
Bot semiautomatico para Facebook.

Usa la misma configuracion y salida que LinkedIn, pero con credenciales y perfil
de navegador propios. Requiere agregar al archivo .env:

    FACEBOOK_USUARIO=...
    FACEBOOK_CONTRASENA=...

La automatizacion es conservadora: abre Facebook, permite login/verificacion
manual, entra al perfil oficial de cada banco y revisa comentarios publicos en
publicaciones del rango configurado.
"""

from social_media_bot import ejecutar_bot_red


DEFINICION_FACEBOOK = {
    "nombre": "facebook",
    "nombre_visible": "Facebook",
    "usuario_env": "FACEBOOK_USUARIO",
    "contrasena_env": "FACEBOOK_CONTRASENA",
    "login_url": "https://www.facebook.com/login",
    "perfiles": {
        "Banco Popular Colombia": "https://web.facebook.com/BancoPopular?locale=es_LA",
        "Banco Davivienda": "https://web.facebook.com/BancoDavivienda",
        "Bancolombia": "https://web.facebook.com/Bancolombia",
        "Banco de Bogotá": "https://web.facebook.com/BancodeBogota",
        "Banco Agrario de Colombia": "https://web.facebook.com/bancoagrario",
        "Banco de Occidente": "https://web.facebook.com/BcoOccidente",
        "Banco Caja Social": "https://web.facebook.com/BancoCajaSocial",
    },
    "patrones_url_publicacion": [
        r"facebook\.com/.*/posts/",
        r"facebook\.com/.*/photos/",
        r"facebook\.com/.*/videos/",
        r"facebook\.com/photo\?fbid=",
        r"facebook\.com/reel/",
        r"facebook\.com/.*/reels/",
        r"facebook\.com/permalink\.php",
        r"story_fbid=",
    ],
    "seccion_publicaciones_textos": [
        "Publicaciones",
        "Posts",
    ],
    "selectores_comentario": [
        "div[aria-label*='comment' i]",
        "div[aria-label*='comentario' i]",
        "div[aria-label*='reply' i]",
        "div[aria-label*='respuesta' i]",
        "div[role='article']",
        "div[dir='auto']",
    ],
}


if __name__ == "__main__":
    ejecutar_bot_red(DEFINICION_FACEBOOK)

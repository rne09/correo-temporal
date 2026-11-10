#!/usr/bin/env python3
"""
Correo temporal - programa sencillo con menu.
Intenta varios proveedores gratuitos en orden y permite usar el correo activo
para realizar un registro individual en Retouch4me.
"""
import html as html_lib
import os
import shutil
import subprocess
import sys
import time
import re
import secrets
import string
import webbrowser
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 6

RETOUCH_BASE = "https://retouch4.me"
RETOUCH_FORM_URL = f"{RETOUCH_BASE}/auth/registration"
RETOUCH_REGISTER_URL = f"{RETOUCH_BASE}/auth/register"
RETOUCH_POLICIES_URL = f"{RETOUCH_BASE}/retouch4mepolicies"
RETOUCH_ACCOUNT_URL = f"{RETOUCH_BASE}/account"
RETOUCH_RECOVERY_URL = f"{RETOUCH_BASE}/auth/password_recovery"
RETOUCH_TIMEOUT = 30
ARCHIVO_CUENTAS_RETOUCH4ME = "cuentas_retouch4me.txt"
ARCHIVO_LIMPIEZA_APEX = "Retouch4me_Apex_LIMPIEZA_DIRIGIDA_Conservar_Quinces.bat"
CMD_EXE = r"C:\Windows\System32\cmd.exe"
CLIP_EXE = r"C:\Windows\System32\clip.exe"

# ---------------------------------------------------------------------------
# Colores ANSI (Windows 10+ los soporta; os.system("") los activa en la consola)
# ---------------------------------------------------------------------------
os.system("")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class C:
    RESET = "\033[0m"
    NEGRITA = "\033[1m"
    TENUE = "\033[2m"
    ROJO = "\033[91m"
    VERDE = "\033[92m"
    AMARILLO = "\033[93m"
    AZUL = "\033[94m"
    MAGENTA = "\033[95m"
    CIAN = "\033[96m"
    BLANCO = "\033[97m"
    FONDO_VERDE = "\033[42m\033[30m"


def color(texto, *estilos):
    return "".join(estilos) + str(texto) + C.RESET


def ok(msg):
    print(color(f"  ✔ {msg}", C.VERDE))


def info(msg):
    print(color(f"  • {msg}", C.CIAN))


def aviso(msg):
    print(color(f"  ! {msg}", C.AMARILLO))


def error(msg):
    print(color(f"  ✖ {msg}", C.ROJO))


def preguntar(msg):
    return input(color(f"  › {msg} ", C.MAGENTA, C.NEGRITA)).strip()


def ancho():
    return max(50, min(shutil.get_terminal_size((80, 20)).columns - 2, 90))


def linea(car="─", c=C.TENUE):
    print(color(car * ancho(), c))


def caja(titulo, filas=(), c=C.AZUL):
    w = ancho()
    print(color("╭" + "─" * (w - 2) + "╮", c))
    print(color("│", c) + color(titulo.center(w - 2), C.NEGRITA, C.BLANCO) + color("│", c))
    if filas:
        print(color("├" + "─" * (w - 2) + "┤", c))
        for f in filas:
            visible = re.sub(r"\033\[[0-9;]*m", "", f)
            print(color("│", c) + " " + f + " " * max(0, w - 3 - len(visible)) + color("│", c))
    print(color("╰" + "─" * (w - 2) + "╯", c))


def limpiar_pantalla():
    os.system("cls" if os.name == "nt" else "clear")


def copiar_portapapeles(texto):
    try:
        if os.name == "nt" and os.path.isfile(CLIP_EXE):
            subprocess.run([CLIP_EXE], input=texto.encode("utf-16"), check=True)
            return True
        if sys.platform == "darwin" and shutil.which("pbcopy"):
            subprocess.run(["pbcopy"], input=texto.encode("utf-8"), check=True)
            return True
    except Exception:
        pass
    return False


class ErrorRegistroRetouch4me(RuntimeError):
    """Error esperado durante el registro de una cuenta en Retouch4me."""


class _RetouchHtmlParser(HTMLParser):
    """Extrae el token CSRF y las credenciales de las paginas de Retouch4me."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.token = None
        self.credenciales = {}
        self._partes_credencial = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        atributos = dict(attrs)

        if tag == "meta" and str(atributos.get("name", "")).lower() == "csrf-token":
            self.token = atributos.get("content") or self.token
        elif tag == "input" and atributos.get("name") == "_token":
            self.token = atributos.get("value") or self.token
        elif tag == "li":
            clases = str(atributos.get("class", "")).split()
            if "user-form__input" in clases:
                self._partes_credencial = []

    def handle_data(self, data):
        if self._partes_credencial is not None:
            self._partes_credencial.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "li" or self._partes_credencial is None:
            return

        texto = " ".join("".join(self._partes_credencial).split())
        coincidencia = re.match(r"(Email|Password)\s*:\s*(\S+)", texto, re.I)
        if coincidencia:
            self.credenciales[coincidencia.group(1).lower()] = coincidencia.group(2)
        self._partes_credencial = None


def _analizar_html_retouch4me(contenido):
    parser = _RetouchHtmlParser()
    parser.feed(contenido or "")
    parser.close()
    return parser


def _obtener_token_retouch4me(sesion):
    respuesta = sesion.get(RETOUCH_FORM_URL, timeout=RETOUCH_TIMEOUT)
    respuesta.raise_for_status()
    token = _analizar_html_retouch4me(respuesta.text).token
    if not token:
        raise ErrorRegistroRetouch4me("Retouch4me no entrego el token de seguridad del formulario.")
    return token


def _diagnostico_registro_retouch4me(respuesta):
    """Devuelve el mensaje de error que muestra la web y guarda la pagina para revisarla."""
    contenido = respuesta.text or ""
    partes = [f"\n    Pagina devuelta: {getattr(respuesta, 'url', '?')} (HTTP {getattr(respuesta, 'status_code', '?')})"]
    mensajes = []
    for bloque in re.findall(
        r'(?is)<[^>]+class="[^"]*(?:error|invalid|alert|danger|warning)[^"]*"[^>]*>(.*?)</',
        contenido,
    ):
        texto = " ".join(html_lib.unescape(ETIQUETA_RE.sub(" ", bloque)).split())
        if texto and texto not in mensajes:
            mensajes.append(texto)
    if mensajes:
        partes.append("    Mensaje de la web: " + " | ".join(mensajes[:5]))
    try:
        ruta = os.path.join(_directorio_aplicacion(), "ultimo_registro_retouch4me.html")
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(contenido)
        partes.append(f"    Pagina guardada en: {ruta}")
    except OSError:
        pass
    return "\n".join(partes)


def registrar_retouch4me(correo, nombre, apellido):
    """Registra una sola cuenta usando el correo temporal activo."""
    with requests.Session() as sesion:
        sesion.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        token = _obtener_token_retouch4me(sesion)
        try:
            respuesta = sesion.post(
                RETOUCH_REGISTER_URL,
                data={
                    "_token": token,
                    "email": correo,
                    "name": nombre,
                    "last_name": apellido,
                    "subscribe": "0",
                    "agree_eula": "1",
                },
                headers={"Referer": RETOUCH_FORM_URL, "Origin": RETOUCH_BASE},
                timeout=RETOUCH_TIMEOUT,
            )
        except requests.Timeout as exc:
            raise ErrorRegistroRetouch4me(
                "Retouch4me no respondio a tiempo. El resultado es incierto: "
                "revisa la bandeja antes de volver a intentarlo."
            ) from exc

        try:
            respuesta.raise_for_status()
        except requests.HTTPError as exc:
            raise ErrorRegistroRetouch4me(
                f"Retouch4me rechazo o no confirmo el registro "
                f"(HTTP {respuesta.status_code})."
            ) from exc

        # La respuesta web del registro NO es la fuente autoritativa de la
        # contrasena. Retouch4me envia la "Temporary password" definitiva por
        # correo junto con el enlace /email/verify/. Aqui solo comprobamos que,
        # si la pagina devolvio un correo, corresponda al que acabamos de usar.
        respuesta_registro = _analizar_html_retouch4me(respuesta.text).credenciales
        correo_respuesta = respuesta_registro.get("email")
        if not correo_respuesta:
            detalle = _diagnostico_registro_retouch4me(respuesta)
            raise ErrorRegistroRetouch4me(
                "Retouch4me no confirmo el registro con el correo solicitado. "
                "Revisa la bandeja antes de volver a intentarlo." + detalle
            )
        if correo_respuesta.casefold() != correo.casefold():
            raise ErrorRegistroRetouch4me(
                "Retouch4me devolvio datos para un correo distinto; "
                "no se continuara por seguridad."
            )

        # La password del email tiene prioridad; la de la pagina se usa solo
        # como respaldo cuando el email llega sin ella.
        return {"email": correo, "password": respuesta_registro.get("password")}


def solicitar_recuperacion_retouch4me(correo):
    """Pide a Retouch4me que envie el correo de 'Forgot your password?'."""
    with requests.Session() as sesion:
        sesion.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        })
        token = _obtener_token_retouch4me(sesion)
        try:
            respuesta = sesion.post(
                RETOUCH_RECOVERY_URL,
                data={"email": correo, "_token": token},
                headers={
                    "Accept": "application/json",
                    "X-CSRF-TOKEN": token,
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{RETOUCH_BASE}/auth",
                    "Origin": RETOUCH_BASE,
                },
                timeout=RETOUCH_TIMEOUT,
            )
        except requests.Timeout as exc:
            raise ErrorRegistroRetouch4me(
                "Retouch4me no respondio a tiempo; revisa la bandeja por si el correo llego."
            ) from exc

    try:
        datos = respuesta.json()
    except ValueError:
        datos = {}
    if respuesta.status_code >= 400:
        motivo = datos.get("error") or datos.get("message") or f"HTTP {respuesta.status_code}"
        raise ErrorRegistroRetouch4me(f"Retouch4me no acepto la recuperacion: {motivo}")
    return datos.get("message") or "Solicitud enviada."


def _directorio_aplicacion():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def guardar_cuenta_retouch4me(credenciales):
    """Guarda SOLO las credenciales recibidas por email de Retouch4me."""
    ruta = os.path.join(_directorio_aplicacion(), ARCHIVO_CUENTAS_RETOUCH4ME)
    url = credenciales.get("verify_url", "")
    with open(ruta, "a", encoding="utf-8") as archivo:
        archivo.write(
            f"{datetime.now():%Y-%m-%d %H:%M:%S} | "
            f"{credenciales['email']} | {credenciales['password']} | {url}\n"
        )
    return ruta


def _ruta_limpieza_apex():
    """Ubica el BAT en la carpeta Retouch, hermana de Correo temporal."""
    base = _directorio_aplicacion()
    raiz_proyecto = os.path.dirname(base) if os.path.basename(base).casefold() == "dist" else base
    candidatos = [
        os.path.abspath(os.path.join(
            raiz_proyecto,
            "..",
            "Retouch",
            ARCHIVO_LIMPIEZA_APEX,
        )),
        os.path.join(
            r"D:\ANDERSON_RENE_FOTOGRAFO\Retouch",
            ARCHIVO_LIMPIEZA_APEX,
        ),
    ]
    for candidato in candidatos:
        if os.path.isfile(candidato):
            return candidato
    return candidatos[0]


def ejecutar_limpieza_apex():
    """Ejecuta la limpieza dirigida en modo automatico y devuelve su codigo."""
    ruta = _ruta_limpieza_apex()
    if not os.path.isfile(ruta):
        raise FileNotFoundError(f"No encontre el archivo de limpieza: {ruta}")

    if os.name != "nt":
        raise RuntimeError("La limpieza de Apex usa un archivo .bat y solo funciona en Windows.")
    if not os.path.isfile(CMD_EXE):
        raise FileNotFoundError(f"No encontre el interprete de Windows: {CMD_EXE}")
    resultado = subprocess.run(
        [CMD_EXE, "/d", "/c", "call", ruta, "/AUTO"],
        cwd=os.path.dirname(ruta),
        check=False,
    )
    return resultado.returncode


def _ofrecer_recuperacion(proveedor, correo):
    respuesta = preguntar("No llego la contrasena. Generar una nueva con 'Forgot your password'? [S/n]:").lower()
    if respuesta in ("", "s", "si", "sí", "y", "yes"):
        flujo_recuperar_contrasena_retouch4me(proveedor, correo)


def flujo_registro_retouch4me(proveedor, correo):
    """Pide los datos, confirma el EULA y registra el correo temporal activo."""
    print()
    caja("REGISTRO EN RETOUCH4ME", [
        f"{color('Correo:', C.CIAN, C.NEGRITA)} {color(correo, C.VERDE, C.NEGRITA)}",
        "Se realizara un unico registro con este correo temporal.",
    ], c=C.MAGENTA)

    nombre = secrets.choice(NOMBRES).capitalize()
    apellido = secrets.choice(APELLIDOS)
    info(f"Nombre generado: {nombre} {apellido}")

    print()
    info(f"EULA y politicas: {RETOUCH_POLICIES_URL}")
    aceptar = preguntar("Continuar y aceptar el EULA de Retouch4me? [s/N]:").lower()
    if aceptar not in ("s", "si", "sí", "y", "yes"):
        aviso("Registro cancelado; no se envio ningun dato.")
        return False

    info("Enviando el registro a Retouch4me...")
    registro = registrar_retouch4me(correo, nombre, apellido) or {}
    password_pagina = registro.get("password")

    print()
    ok("Registro enviado. Esperando el correo con Login, Temporary password y Verify Email...")
    credenciales = esperar_verificacion_retouch4me(
        proveedor, correo_esperado=correo, password_respaldo=password_pagina
    )
    if not credenciales:
        if password_pagina:
            info(f"Contrasena temporal que mostro la web al registrarse: "
                 f"{color(password_pagina, C.VERDE, C.NEGRITA)}")
        else:
            _ofrecer_recuperacion(proveedor, correo)
        return

    print()
    caja("CREDENCIALES RECIBIDAS POR EMAIL", [
        f"{color('Login:', C.CIAN, C.NEGRITA)}              {credenciales['email']}",
        f"{color('Temporary password:', C.CIAN, C.NEGRITA)} "
        f"{credenciales['password'] or color('(no vino en el correo)', C.AMARILLO)}",
        f"{color('Verify Email:', C.CIAN, C.NEGRITA)}       {_recortar(credenciales['verify_url'])}",
    ], c=C.VERDE)
    print()
    print(color("  Enlace de verificacion completo (Cmd + clic para abrirlo):", C.CIAN, C.NEGRITA))
    print(f"  {credenciales['verify_url']}")

    # Siempre se ofrece crear una contrasena nueva con "Forgot your password?":
    # por defecto SI cuando no llego contrasena, y NO cuando si llego.
    print()
    if credenciales["password"]:
        respuesta = preguntar(
            "No ves la contrasena o no funciona? Generar una nueva con 'Forgot your password'? [s/N]:"
        ).lower()
        quiere = respuesta in ("s", "si", "sí", "y", "yes")
    else:
        aviso("El correo de Retouch4me llego sin contrasena.")
        respuesta = preguntar("Generar una nueva con 'Forgot your password'? [S/n]:").lower()
        quiere = respuesta in ("", "s", "si", "sí", "y", "yes")
    if quiere:
        enlace = flujo_recuperar_contrasena_retouch4me(proveedor, correo)
        if enlace:
            credenciales["password"] = "(nueva, creada con: " + enlace + ")"
    if not credenciales["password"]:
        credenciales["password"] = "(pendiente: usa la opcion 8)"

    datos_cuenta = (
        f"Login: {credenciales['email']}\n"
        f"Temporary password: {credenciales['password']}\n"
        f"Verify Email: {credenciales['verify_url']}"
    )
    copiar = preguntar("Copiar login, password temporal y enlace al portapapeles? [s/N]:").lower()
    if copiar in ("s", "si", "sí", "y", "yes"):
        if copiar_portapapeles(datos_cuenta):
            ok("Datos del correo copiados al portapapeles")
        else:
            aviso("No se pudieron copiar los datos.")

    guardar = preguntar("Guardar estos datos del correo sin cifrar en un archivo? [s/N]:").lower()
    if guardar in ("s", "si", "sí", "y", "yes"):
        try:
            ruta = guardar_cuenta_retouch4me(credenciales)
            ok(f"Credenciales correctas guardadas en: {ruta}")
        except OSError as exc:
            aviso(f"La cuenta fue creada, pero no pude guardar el archivo: {exc}")

    _abrir(credenciales["verify_url"])
    confirmar_verificacion_y_abrir_cuenta(credenciales["verify_url"])


NOMBRES = [
    "carlos", "andres", "sofia", "valeria", "mateo", "diego", "camila",
    "lucas", "martina", "sebastian", "isabella", "santiago", "valentina",
    "daniel", "gabriela", "julian", "renata", "nicolas", "paula", "emilio",
    "laura", "esteban", "daniela", "felipe", "natalia", "alejandro", "sara",
]


APELLIDOS = [
    "Garcia", "Rodriguez", "Martinez", "Lopez", "Gonzalez", "Perez", "Sanchez",
    "Ramirez", "Torres", "Flores", "Rivera", "Gomez", "Diaz", "Reyes", "Morales",
    "Herrera", "Castro", "Vargas", "Ortiz", "Mendoza", "Rojas", "Medina",
]


def random_string(n=10):
    alfabeto = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(n))


def nombre_aleatorio():
    return f"{secrets.choice(NOMBRES)}{secrets.randbelow(9900) + 100}"


URL_RE = re.compile(r'https?://[^\s<>"\'()]+')
ANCLA_RE = re.compile(r'<a\b[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
ETIQUETA_RE = re.compile(r"<[^>]+>")

# Palabras que indican un enlace de verificacion / confirmacion de cuenta
PALABRAS_VERIFICAR = (
    "verify", "verification", "confirm", "activate", "activation", "validate",
    "verificar", "verifica", "confirmar", "confirma", "activar", "validar",
)
# Enlaces que no interesan (redes, bajas, legales, imagenes...)
PALABRAS_IGNORAR = (
    "unsubscribe", "optout", "opt-out", "preferences", "privacy", "policies", "policy",
    "terms", "legal", "help", "support", "facebook.com", "instagram.com", "twitter.com",
    "x.com/", "youtube.com", "linkedin.com", "tiktok.com", "pinterest.", "t.me/",
    "w3.org", "schemas.", "fonts.googleapis", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css",
)


def _limpiar_url(url):
    url = html_lib.unescape(url).strip()
    return url.rstrip(".,;:!?]>")


def extraer_enlaces(texto, html):
    """Devuelve una lista de (url, texto_del_enlace) sin duplicados."""
    enlaces = {}
    for href, etiqueta in ANCLA_RE.findall(html or ""):
        url = _limpiar_url(href)
        texto_ancla = " ".join(html_lib.unescape(ETIQUETA_RE.sub(" ", etiqueta)).split())
        if url not in enlaces or not enlaces[url]:
            enlaces[url] = texto_ancla
    for bruto in URL_RE.findall(f"{html or ''} {texto or ''}"):
        url = _limpiar_url(bruto)
        enlaces.setdefault(url, "")
    return list(enlaces.items())


def clasificar_enlaces(enlaces):
    """Separa los enlaces en (verificacion, otros). Descarta los que no interesan."""
    verificar, otros = [], []
    for url, etiqueta in enlaces:
        if not _url_https_segura(url):
            continue
        url_min, etq_min = url.lower(), etiqueta.lower()
        if any(p in url_min or p in etq_min for p in PALABRAS_VERIFICAR):
            verificar.append((url, etiqueta))
        elif not any(p in url_min for p in PALABRAS_IGNORAR):
            otros.append((url, etiqueta))
    return verificar, otros


def _url_https_segura(url):
    """Acepta solo HTTPS con host y sin credenciales incrustadas."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    return bool(
        partes.scheme.lower() == "https"
        and partes.hostname
        and partes.username is None
        and partes.password is None
    )


# ---------------------------------------------------------------------------
# Proveedor: 1secmail (varios dominios: 1secmail.com/.org/.net, wwjmp.com, etc.)
# ---------------------------------------------------------------------------
class Proveedor1secmail:
    nombre = "1secmail"
    API = "https://www.1secmail.com/api/v1/"

    def dominios(self):
        r = requests.get(self.API, params={"action": "getDomainList"}, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def crear_cuenta(self, dominio):
        usuario = nombre_aleatorio()
        self.login = usuario
        self.dominio = dominio
        return f"{usuario}@{dominio}"

    def listar_mensajes(self):
        r = requests.get(self.API, params={"action": "getMessages", "login": self.login, "domain": self.dominio},
                          headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return [{"id": m["id"], "de": m["from"], "asunto": m["subject"]} for m in r.json()]

    def leer_mensaje(self, msg_id):
        r = requests.get(self.API, params={"action": "readMessage", "login": self.login,
                                            "domain": self.dominio, "id": msg_id},
                          headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        m = r.json()
        return {"de": m["from"], "asunto": m["subject"], "texto": m.get("textBody"), "html": m.get("htmlBody")}


# ---------------------------------------------------------------------------
# Proveedor: guerrillamail (varios dominios, aunque a veces asigna uno fijo)
# ---------------------------------------------------------------------------
class ProveedorGuerrillaMail:
    nombre = "guerrillamail"
    API = "https://api.guerrillamail.com/ajax.php"
    DOMINIOS = ["guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
                "sharklasers.com", "grr.la", "pokemail.net", "spam4.me", "guerrillamailblock.com"]

    def dominios(self):
        r = requests.get(self.API, params={"f": "get_email_address"}, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        r.json()
        # guerrillamail suele ignorar el dominio pedido y asigna uno por su cuenta,
        # asi que no se ofrece menu de eleccion para este proveedor.
        return ["(automatico)"]

    def crear_cuenta(self, dominio):
        usuario = nombre_aleatorio()
        r = requests.get(self.API, params={"f": "get_email_address"}, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        datos = r.json()
        self.sid = datos["sid_token"]

        r = requests.get(self.API, params={"f": "set_email_user", "email_user": usuario,
                                            "domain": dominio, "sid_token": self.sid},
                          headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        datos = r.json()
        address = datos["email_addr"]
        if not address.endswith(f"@{dominio}"):
            print(f"(guerrillamail asigno el dominio automaticamente: @{address.split('@')[1]})")
        return address

    def listar_mensajes(self):
        r = requests.get(self.API, params={"f": "get_email_list", "offset": 0, "sid_token": self.sid},
                          headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        lista = r.json().get("list", [])
        return [{"id": m["mail_id"], "de": m["mail_from"], "asunto": m["mail_subject"]} for m in lista]

    def leer_mensaje(self, msg_id):
        r = requests.get(self.API, params={"f": "fetch_email", "email_id": msg_id, "sid_token": self.sid},
                          headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        m = r.json()
        return {"de": m["mail_from"], "asunto": m["mail_subject"], "texto": m.get("mail_body"), "html": m.get("mail_body")}


# ---------------------------------------------------------------------------
# Proveedor: mail.tm (respaldo final, normalmente solo tiene uberip.com)
# ---------------------------------------------------------------------------
class ProveedorMailTm:
    nombre = "mail.tm"
    API = "https://api.mail.tm"

    def dominios(self):
        r = self._peticion("GET", "/domains")
        r.raise_for_status()
        activos = [d["domain"] for d in r.json()["hydra:member"] if d.get("isActive") and not d.get("isPrivate")]
        return activos or [r.json()["hydra:member"][0]["domain"]]

    REINTENTOS_429 = 3

    def _peticion(self, metodo, ruta, autenticada=False, **kwargs):
        """Hace la peticion reintentando si mail.tm responde 429 y renovando el token si caduca."""
        for intento in range(self.REINTENTOS_429 + 1):
            headers = dict(HEADERS)
            if autenticada:
                headers["Authorization"] = f"Bearer {self.token}"
            r = requests.request(metodo, f"{self.API}{ruta}", headers=headers, timeout=TIMEOUT, **kwargs)
            if r.status_code == 401 and autenticada and getattr(self, "address", None):
                self._obtener_token()
                continue
            if r.status_code == 429 and intento < self.REINTENTOS_429:
                try:
                    espera = int(r.headers.get("Retry-After", ""))
                except ValueError:
                    espera = 2 * (intento + 1)
                time.sleep(min(max(espera, 1), 30))
                continue
            return r
        return r

    def _obtener_token(self):
        r = self._peticion("POST", "/token", json={"address": self.address, "password": self.password})
        r.raise_for_status()
        self.token = r.json()["token"]

    def crear_cuenta(self, dominio):
        password = random_string(12)
        self.password = password
        ultimo_error = None
        for _ in range(5):
            usuario = nombre_aleatorio()
            address = f"{usuario}@{dominio}"
            r = self._peticion("POST", "/accounts", json={"address": address, "password": password})
            if r.status_code == 201:
                break
            ultimo_error = f"HTTP {r.status_code}: {r.text[:200]}"
        else:
            raise RuntimeError(f"No se pudo crear la cuenta: {ultimo_error}")

        self.address = address
        self._obtener_token()
        return address

    def listar_mensajes(self):
        r = self._peticion("GET", "/messages", autenticada=True)
        r.raise_for_status()
        return [{"id": m["id"], "de": m["from"]["address"], "asunto": m["subject"]} for m in r.json()["hydra:member"]]

    def leer_mensaje(self, msg_id):
        r = self._peticion("GET", f"/messages/{msg_id}", autenticada=True)
        r.raise_for_status()
        m = r.json()
        contenido_html = m.get("html")
        if isinstance(contenido_html, list):
            contenido_html = "\n".join(str(fragmento) for fragmento in contenido_html)
        return {
            "de": m["from"]["address"],
            "asunto": m["subject"],
            "texto": m.get("text"),
            "html": contenido_html,
        }


PROVEEDORES = [ProveedorMailTm(), Proveedor1secmail()]


def crear_correo_seguro_retouch4me():
    """Crea un buzon mail.tm autenticado para recibir credenciales sensibles."""
    proveedor = ProveedorMailTm()
    info(f"Conectando con {proveedor.nombre} para crear un buzon privado...")
    dominios = proveedor.dominios()
    if not dominios:
        raise RuntimeError("mail.tm no tiene dominios disponibles ahora mismo.")
    correo = proveedor.crear_cuenta(dominios[0])
    return proveedor, correo


def elegir_proveedor_y_dominio():
    """Prueba los proveedores en orden. Devuelve (proveedor, dominio elegido)."""
    for proveedor in PROVEEDORES:
        try:
            info(f"Conectando con {proveedor.nombre}...")
            dominios = proveedor.dominios()
            if not dominios:
                continue
        except Exception:
            aviso(f"{proveedor.nombre} no disponible, probando el siguiente...")
            continue

        if len(dominios) == 1:
            ok(f"Proveedor: {proveedor.nombre}  (dominio @{dominios[0]})")
            return proveedor, dominios[0]

        print()
        print(color(f"  Dominios disponibles en {proveedor.nombre}:", C.NEGRITA))
        for i, d in enumerate(dominios, 1):
            print(f"    {color(f'[{i}]', C.AMARILLO)} @{d}")
        eleccion = preguntar("Elige un dominio (Enter = el primero):")
        if eleccion.isdigit() and 1 <= int(eleccion) <= len(dominios):
            return proveedor, dominios[int(eleccion) - 1]
        return proveedor, dominios[0]

    raise RuntimeError("Ningun proveedor de correo temporal esta disponible ahora mismo.")


# ---------------------------------------------------------------------------
# Presentacion de mensajes y enlaces
# ---------------------------------------------------------------------------
def _recortar(url, maximo=None):
    maximo = maximo or ancho() - 12
    return url if len(url) <= maximo else url[: maximo - 1] + "…"


def _imprimir_lista(enlaces, c=C.BLANCO):
    for i, (url, etiqueta) in enumerate(enlaces, 1):
        host = urlsplit(url).hostname or "host desconocido"
        print(f"    {color(f'[{i}]', C.AMARILLO, C.NEGRITA)} "
              f"{color(host, C.CIAN, C.NEGRITA)}  {color(_recortar(url), c)}")
        if etiqueta:
            print(color(f"        {etiqueta[:ancho() - 10]}", C.TENUE))


def texto_legible(m):
    """Texto plano del mensaje (si solo hay HTML, le quita las etiquetas)."""
    texto = m.get("texto")
    if not texto and m.get("html"):
        html = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", m["html"])
        html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", html)
        texto = html_lib.unescape(ETIQUETA_RE.sub(" ", html))
    limpio, vacia = [], False
    for l in (texto or "").splitlines():
        l = " ".join(l.split())
        if not l:
            if not vacia:
                limpio.append("")
            vacia = True
        else:
            limpio.append(l)
            vacia = False
    return "\n".join(limpio).strip()


def _caja_mensaje(m, titulo, c):
    caja(titulo, [
        f"{color('De:', C.CIAN, C.NEGRITA)}     {m['de']}",
        f"{color('Asunto:', C.CIAN, C.NEGRITA)} {m['asunto']}",
    ], c=c)


def mostrar_mensaje(m, lineas_max=18):
    print()
    _caja_mensaje(m, "✉  NUEVO MENSAJE", C.VERDE)
    cuerpo = texto_legible(m).splitlines()
    for l in cuerpo[:lineas_max]:
        print("  " + l)
    if len(cuerpo) > lineas_max:
        print(color(f"  … ({len(cuerpo) - lineas_max} lineas mas, usa la opcion 4 para leerlo completo)", C.TENUE))
    linea()


def mostrar_mensaje_completo(m):
    print()
    _caja_mensaje(m, "✉  MENSAJE", C.AZUL)
    for l in texto_legible(m).splitlines():
        print("  " + l)
    linea()


def _abrir(url):
    if not _url_https_segura(url):
        error("Enlace bloqueado: debe usar HTTPS y no incluir credenciales.")
        return
    webbrowser.open(url)
    ok("Abierto en el navegador")


def _host_retouch4me(url):
    """Acepta retouch4.me y sus subdominios para enlaces de verificacion."""
    if not _url_https_segura(url):
        return False
    host = (urlsplit(url).hostname or "").casefold()
    return host == "retouch4.me" or host.endswith(".retouch4.me")


def _enlace_verificacion_retouch4me(mensaje):
    """Obtiene el enlace /email/verify/ HTTPS perteneciente a Retouch4me."""
    enlaces = extraer_enlaces(mensaje.get("texto"), mensaje.get("html"))
    candidatos = []
    for url, etiqueta in enlaces:
        if not _host_retouch4me(url):
            continue
        ruta = (urlsplit(url).path or "").casefold()
        etiqueta_min = (etiqueta or "").casefold()
        if "/email/verify/" in ruta:
            return url
        if "verify email" in etiqueta_min or "verify" in etiqueta_min:
            candidatos.append(url)
    return candidatos[0] if candidatos else None


def _enlace_recuperacion_retouch4me(mensaje):
    """Busca en el correo el enlace de Retouch4me para restablecer la contrasena."""
    enlaces = extraer_enlaces(mensaje.get("texto"), mensaje.get("html"))
    palabras = ("reset", "password", "recovery", "restore")
    for url, etiqueta in enlaces:
        if not _host_retouch4me(url):
            continue
        ruta = (urlsplit(url).path or "").casefold()
        etiqueta_min = (etiqueta or "").casefold()
        if "/email/verify/" in ruta:
            continue
        if any(p in ruta or p in etiqueta_min for p in palabras):
            return url
    return None


def esperar_enlace_recuperacion(proveedor, ignorar=()):
    """Espera el correo de recuperacion y devuelve (enlace, mensaje)."""
    print()
    info("Esperando el correo de recuperacion de Retouch4me... (Ctrl+C para cancelar)")
    vistos = set(ignorar)
    giro = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    pausa = PAUSA_NORMAL
    try:
        while True:
            try:
                mensajes = proveedor.listar_mensajes()
                pausa = PAUSA_NORMAL
            except Exception as exc:
                pausa = _siguiente_pausa(pausa, exc)
                print()
                aviso(f"No pude revisar la bandeja ({exc}); reintento en {pausa} s...")
                mensajes = []

            for resumen in mensajes:
                if resumen["id"] in vistos:
                    continue
                try:
                    completo = proveedor.leer_mensaje(resumen["id"])
                except Exception as exc:
                    pausa = _siguiente_pausa(pausa, exc)
                    aviso(f"No pude leer el mensaje todavia, reintento en {pausa} s...")
                    break
                vistos.add(resumen["id"])
                enlace = _enlace_recuperacion_retouch4me(completo)
                if enlace:
                    print("\r" + " " * 80 + "\r", end="")
                    mostrar_mensaje(completo, lineas_max=12)
                    return enlace, completo

            for _ in range(pausa * 2):
                hora = time.strftime("%H:%M:%S")
                estado = f"Esperando correo de recuperacion... {hora}"
                print(f"\r  {color(giro[i % len(giro)], C.CIAN)} {color(estado, C.TENUE)}   ", end="", flush=True)
                i += 1
                time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        aviso("Espera cancelada.")
        return None, None


def flujo_recuperar_contrasena_retouch4me(proveedor, correo):
    """Pide el correo de 'Forgot your password?' y abre el enlace que llegue."""
    print()
    caja("RECUPERAR CONTRASENA DE RETOUCH4ME", [
        f"{color('Correo:', C.CIAN, C.NEGRITA)} {color(correo, C.VERDE, C.NEGRITA)}",
        "Retouch4me enviara un enlace para crear una contrasena nueva.",
    ], c=C.MAGENTA)
    try:
        ya_estaban = {m["id"] for m in proveedor.listar_mensajes()}
    except Exception:
        ya_estaban = set()

    info("Enviando la solicitud de recuperacion...")
    ok(solicitar_recuperacion_retouch4me(correo))
    enlace, _ = esperar_enlace_recuperacion(proveedor, ignorar=ya_estaban)
    if not enlace:
        return None

    print()
    ok("Enlace para crear la contrasena nueva:")
    print(f"  {enlace}")
    print(color("  (Cmd + clic para abrirlo)", C.TENUE))
    _abrir(enlace)
    return enlace


def extraer_credenciales_correo_retouch4me(mensaje, correo_esperado=None, password_respaldo=None):
    """Extrae Login, Temporary password y Verify Email del correo recibido."""
    texto = texto_legible(mensaje)
    if mensaje.get("html"):
        # Tambien se mira la version HTML: a veces la de texto plano omite datos.
        texto += "\n" + texto_legible({"html": mensaje["html"]})

    patron_email = re.compile(
        r"\bLogin\b\s*:?\s*([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
        re.I | re.S,
    )
    patron_password = re.compile(
        r"\bTemporary\s+password\b\s*:?\s*([^\s<>()]+)",
        re.I | re.S,
    )

    m_email = patron_email.search(texto or "")
    verify_url = _enlace_verificacion_retouch4me(mensaje)

    # El correo puede traer iconos (p. ej. un emoji) antes de la contrasena:
    # se toma la primera palabra que contenga letras o numeros ASCII.
    password = None
    for m_etiqueta in re.finditer(r"\bTemporary\s+password\b\s*:?[ \t]*([^\n]*)", texto or "", re.I):
        for palabra in m_etiqueta.group(1).split():
            palabra = palabra.strip("<>()")
            if re.search(r"[A-Za-z0-9]", palabra) and not palabra.lower().startswith(("verify", "http")):
                password = palabra
                break
        if password:
            break
    password = password or password_respaldo

    # Sin contrasena tambien se devuelve: el flujo ofrecera recuperarla.
    if not (m_email and verify_url):
        return None

    email = m_email.group(1).strip()

    if correo_esperado and email.casefold() != correo_esperado.casefold():
        return None

    return {
        "email": email,
        "password": password,
        "verify_url": verify_url,
    }


PAUSA_NORMAL = 5      # segundos entre consultas a la bandeja
PAUSA_MAXIMA = 60     # tope de espera cuando el servidor pide ir mas despacio


def _es_limite_peticiones(exc):
    respuesta = getattr(exc, "response", None)
    return getattr(respuesta, "status_code", None) == 429 or "429" in str(exc)


def _siguiente_pausa(pausa, exc):
    """Duplica la espera si el servidor responde 429 (demasiadas peticiones)."""
    if _es_limite_peticiones(exc):
        return min(max(pausa, PAUSA_NORMAL) * 2, PAUSA_MAXIMA)
    return pausa


def esperar_verificacion_retouch4me(proveedor, correo_esperado=None, password_respaldo=None):
    """Espera el email de Retouch4me y devuelve sus credenciales autoritativas."""
    print()
    info("Esperando el correo de Retouch4me con las credenciales... (Ctrl+C para cancelar)")
    vistos = set()
    giro = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    pausa = PAUSA_NORMAL

    try:
        while True:
            try:
                mensajes = proveedor.listar_mensajes()
                pausa = PAUSA_NORMAL
            except Exception as exc:
                pausa = _siguiente_pausa(pausa, exc)
                print()
                if _es_limite_peticiones(exc):
                    aviso(f"Mail.tm pide ir mas despacio; reintento en {pausa} s...")
                else:
                    aviso(f"Error consultando la bandeja: {exc}")
                mensajes = []

            for resumen in mensajes:
                msg_id = resumen["id"]
                if msg_id in vistos:
                    continue
                try:
                    completo = proveedor.leer_mensaje(msg_id)
                except Exception as exc:
                    # No se marca como visto: se reintenta en la siguiente vuelta.
                    pausa = _siguiente_pausa(pausa, exc)
                    aviso(f"No pude leer el mensaje todavia, reintento en {pausa} s...")
                    break
                vistos.add(msg_id)

                credenciales = extraer_credenciales_correo_retouch4me(
                    completo, correo_esperado=correo_esperado,
                    password_respaldo=password_respaldo,
                )
                if not credenciales:
                    continue

                print("\r" + " " * 80 + "\r", end="")
                mostrar_mensaje(completo, lineas_max=12)
                ok("Correo de Retouch4me encontrado.")
                return credenciales

            for _ in range(pausa * 2):
                hora = time.strftime("%H:%M:%S")
                estado = f"Esperando credenciales... {hora}"
                print(f"\r  {color(giro[i % len(giro)], C.CIAN)} {color(estado, C.TENUE)}   ", end="", flush=True)
                i += 1
                time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        aviso("Espera de credenciales cancelada.")
        return None


def confirmar_verificacion_y_abrir_cuenta(url_verificacion):
    """Pide confirmacion humana antes de abrir la cuenta de Retouch4me."""
    if not url_verificacion:
        return False

    while True:
        print()
        respuesta = preguntar("Ya verificaste el correo? [s = si / r = reabrir enlace / n = cancelar]:").lower()
        if respuesta in ("s", "si", "sí", "y", "yes"):
            info("Abriendo tu cuenta de Retouch4me...")
            _abrir(RETOUCH_ACCOUNT_URL)
            return True
        if respuesta in ("r", "reabrir", "abrir"):
            _abrir(url_verificacion)
            continue
        if respuesta in ("n", "no", ""):
            aviso("Continuacion cancelada. Puedes abrir la cuenta mas tarde desde el menu/navegador.")
            return False
        aviso("Opcion no valida.")


def mostrar_enlaces_y_elegir(enlaces):
    if not enlaces:
        info("Este correo no tiene enlaces.")
        return

    verificar, otros = clasificar_enlaces(enlaces)

    if verificar:
        print()
        print(color("  ★ ENLACE DE VERIFICACION ", C.FONDO_VERDE, C.NEGRITA))
        _imprimir_lista(verificar, c=C.VERDE)
        print()
        print(f"    {color('[numero]', C.AMARILLO)} Abrir   "
              f"{color('[c]', C.AMARILLO)} Copiar el primero   "
              f"{color('[t]', C.AMARILLO)} Ver todos   "
              f"{color('[Enter]', C.AMARILLO)} Nada")
        eleccion = preguntar("Opcion:").lower()
        if eleccion == "c":
            if copiar_portapapeles(verificar[0][0]):
                ok("Enlace copiado al portapapeles")
            else:
                error("No se pudo copiar")
            return
        if eleccion.isdigit() and 1 <= int(eleccion) <= len(verificar):
            _abrir(verificar[int(eleccion) - 1][0])
            return
        if eleccion != "t":
            return
    else:
        aviso("No se encontro enlace de verificacion.")

    todos = verificar + otros
    if not todos:
        info("Solo habia enlaces de redes, bajas o imagenes.")
        return
    print()
    print(color("  Otros enlaces:", C.NEGRITA))
    _imprimir_lista(todos)
    print(f"    {color('[0]', C.AMARILLO)} No abrir ninguno")
    eleccion = preguntar("Elige un enlace:")
    if eleccion.isdigit() and 1 <= int(eleccion) <= len(todos):
        _abrir(todos[int(eleccion) - 1][0])


def pausa():
    input(color("\n  Presiona Enter para volver al menu...", C.TENUE))


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------
OPCIONES = [
    ("1", "Crear correo nuevo"),
    ("2", "Ver bandeja de entrada"),
    ("3", "Esperar correos en tiempo real"),
    ("4", "Leer un mensaje"),
    ("5", "Copiar correo al portapapeles"),
    ("6", "Registrarse en Retouch4me con correo temporal"),
    ("7", "Limpiar sesion de Apex y conservar Quinces"),
    ("8", "Recuperar contrasena de Retouch4me (Forgot password)"),
    ("0", "Salir"),
]


def cabecera(proveedor, correo):
    limpiar_pantalla()
    if correo:
        filas = [
            f"{color('Correo:', C.CIAN, C.NEGRITA)}    {color(correo, C.VERDE, C.NEGRITA)}",
            f"{color('Proveedor:', C.CIAN, C.NEGRITA)} {proveedor.nombre}",
        ]
    else:
        filas = [color("Sin correo todavia (usa la opcion 1)", C.AMARILLO)]
    caja("✉  CORREO TEMPORAL  ✉", filas)
    print()
    for k, texto in OPCIONES:
        print(f"    {color(f'[{k}]', C.AMARILLO, C.NEGRITA)}  {texto}")
    print()


def esperar_en_vivo(proveedor):
    print()
    info("Esperando correos nuevos...  (Ctrl+C para volver)")
    print()
    vistos = set()
    giro = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    pausa = PAUSA_NORMAL
    try:
        while True:
            try:
                mensajes = proveedor.listar_mensajes()
                pausa = PAUSA_NORMAL
            except Exception as e:
                mensajes = []
                pausa = _siguiente_pausa(pausa, e)
                print()
                if _es_limite_peticiones(e):
                    aviso(f"Mail.tm pide ir mas despacio; reintento en {pausa} s...")
                else:
                    aviso(f"Error consultando la bandeja: {e}")
            nuevos = [m for m in mensajes if m["id"] not in vistos]
            if nuevos:
                print("\r" + " " * 70 + "\r\a", end="")  # limpia la linea y da un pitido
            for m in nuevos:
                try:
                    completo = proveedor.leer_mensaje(m["id"])
                except Exception as e:
                    pausa = _siguiente_pausa(pausa, e)
                    aviso(f"No pude leer el mensaje todavia, reintento en {pausa} s...")
                    break
                vistos.add(m["id"])
                mostrar_mensaje(completo)
                mostrar_enlaces_y_elegir(extraer_enlaces(completo.get("texto"), completo.get("html")))
                print()
                info("Sigo esperando mas correos...  (Ctrl+C para volver)")
            for _ in range(pausa * 2):
                hora = time.strftime("%H:%M:%S")
                estado = f"Revisando bandeja... {hora}   {len(vistos)} recibidos"
                print(f"\r  {color(giro[i % len(giro)], C.CIAN)} {color(estado, C.TENUE)}   ",
                      end="", flush=True)
                i += 1
                time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        info("Volviendo al menu.")


def ver_bandeja(proveedor):
    mensajes = proveedor.listar_mensajes()
    print()
    if not mensajes:
        info("Bandeja vacia.")
        return mensajes
    print(color(f"  {'#':<4} {'DE':<32} ASUNTO", C.CIAN, C.NEGRITA))
    linea()
    for i, m in enumerate(mensajes, 1):
        de = str(m["de"])[:32].ljust(32)
        print(f"  {color(str(i).ljust(4), C.AMARILLO)} {de} {m['asunto']}")
    info("Para leer uno usa la opcion 4 y escribe su numero (#).")
    return mensajes


def resolver_id_mensaje(proveedor, entrada, mensajes=None):
    """Convierte un numero de la bandeja o un ID (completo o parcial) en el ID real."""
    entrada = entrada.strip()
    if mensajes is None:
        mensajes = proveedor.listar_mensajes()
    if entrada.isdigit() and 1 <= int(entrada) <= len(mensajes):
        return str(mensajes[int(entrada) - 1]["id"])
    for m in mensajes:
        if str(m["id"]) == entrada:
            return entrada
    coincidencias = [str(m["id"]) for m in mensajes if str(m["id"]).startswith(entrada)]
    if entrada and len(coincidencias) == 1:
        return coincidencias[0]
    return entrada


def menu():
    proveedor = None
    correo = None
    correos_registrados = set()

    while True:
        cabecera(proveedor, correo)
        opcion = preguntar("Elige una opcion:")

        if opcion == "0":
            break

        if opcion in ("2", "3", "4", "5") and (not proveedor or not correo):
            aviso("Primero crea un correo (opcion 1).")
            pausa()
            continue

        try:
            if opcion == "1":
                print()
                proveedor, dominio = elegir_proveedor_y_dominio()
                correo = proveedor.crear_cuenta(dominio)
                print()
                ok(f"Correo creado: {color(correo, C.VERDE, C.NEGRITA)}")
                if copiar_portapapeles(correo):
                    ok("Copiado al portapapeles")
                pausa()

            elif opcion == "2":
                ver_bandeja(proveedor)
                pausa()

            elif opcion == "3":
                esperar_en_vivo(proveedor)
                pausa()

            elif opcion == "4":
                mensajes = ver_bandeja(proveedor)
                if not mensajes:
                    pausa()
                    continue
                msg_id = preguntar("Numero (#) o ID del mensaje (Enter = cancelar):")
                if not msg_id:
                    continue
                m = proveedor.leer_mensaje(resolver_id_mensaje(proveedor, msg_id, mensajes))
                mostrar_mensaje_completo(m)
                mostrar_enlaces_y_elegir(extraer_enlaces(m.get("texto"), m.get("html")))
                pausa()

            elif opcion == "5":
                if copiar_portapapeles(correo):
                    ok(f"{correo} copiado al portapapeles")
                else:
                    error("No se pudo copiar")
                pausa()

            elif opcion == "6":
                if (not isinstance(proveedor, ProveedorMailTm) or not correo
                        or correo in correos_registrados):
                    print()
                    if correo in correos_registrados:
                        info(f"{correo} ya se uso en un registro; creare un correo nuevo...")
                    else:
                        info("Creare un correo autenticado para proteger las credenciales...")
                    proveedor, correo = crear_correo_seguro_retouch4me()
                    ok(f"Correo creado: {color(correo, C.VERDE, C.NEGRITA)}")
                # Si el registro llego a enviarse (aunque luego fallara), ese
                # correo ya no se reutiliza: Retouch4me lo rechazaria por duplicado.
                enviado = True
                try:
                    if flujo_registro_retouch4me(proveedor, correo) is False:
                        enviado = False
                finally:
                    if enviado:
                        correos_registrados.add(correo)
                pausa()

            elif opcion == "8":
                if not isinstance(proveedor, ProveedorMailTm) or not correo:
                    aviso("Necesitas el buzon con el que te registraste (crealo con la opcion 6).")
                else:
                    flujo_recuperar_contrasena_retouch4me(proveedor, correo)
                pausa()

            elif opcion == "7":
                print()
                info("Ejecutando la limpieza dirigida de Retouch4me Apex...")
                codigo = ejecutar_limpieza_apex()
                if codigo == 0:
                    ok("Limpieza terminada; el preset Quinces se conservo.")
                else:
                    error(f"La limpieza termino con el codigo {codigo}.")
                pausa()

            else:
                aviso("Opcion invalida.")
                time.sleep(0.8)

        except KeyboardInterrupt:
            print()
        except Exception as e:
            error(f"Error: {e}")
            pausa()


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        error(f"Error: {e}")
        input("Presiona Enter para salir...")

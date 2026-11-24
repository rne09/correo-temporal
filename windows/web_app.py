"""Correo Temporal en el navegador.

Levanta un servidor local (solo en este equipo) y abre una pagina con botones
para todo lo que hace temp_mail_app.py: crear el correo, ver la bandeja, leer
mensajes, registrarse en Retouch4me, recuperar la contrasena y limpiar Apex.

Uso:  python3 web_app.py
"""

import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import temp_mail_app as app

PUERTO = int(os.environ.get("CORREO_TEMPORAL_PUERTO", "8765"))
TOKEN = secrets.token_urlsafe(24)  # evita que otras paginas usen la API local
ESPERA_MAXIMA = 300  # segundos esperando un correo de Retouch4me
RUTA_PAGINA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_app.html")


# ---------------------------------------------------------------------------
# Estado compartido
# ---------------------------------------------------------------------------
class Estado:
    def __init__(self):
        self.lock = threading.Lock()
        self.proveedor = None
        self.correo = None
        self.registrados = set()
        self.tarea = None  # dict con la tarea en curso (registro, recuperacion...)

    def buzon(self):
        with self.lock:
            return self.proveedor, self.correo

    def poner_buzon(self, proveedor, correo):
        with self.lock:
            self.proveedor, self.correo = proveedor, correo


ESTADO = Estado()


def nuevo_buzon():
    proveedor, correo = app.crear_correo_seguro_retouch4me()
    ESTADO.poner_buzon(proveedor, correo)
    return proveedor, correo


# ---------------------------------------------------------------------------
# Tareas largas (se ejecutan en segundo plano y la pagina consulta su avance)
# ---------------------------------------------------------------------------
class Tarea:
    def __init__(self, tipo):
        self.id = secrets.token_hex(6)
        self.tipo = tipo
        self.estado = "en_curso"
        self.pasos = []
        self.resultado = None
        self.error = None
        self.cancelada = False

    def paso(self, texto):
        self.pasos.append({"hora": time.strftime("%H:%M:%S"), "texto": texto})

    def como_dict(self):
        return {"id": self.id, "tipo": self.tipo, "estado": self.estado, "pasos": self.pasos,
                "resultado": self.resultado, "error": self.error}


def lanzar_tarea(tipo, funcion, *args):
    with ESTADO.lock:
        if ESTADO.tarea and ESTADO.tarea.estado == "en_curso":
            raise RuntimeError("Ya hay una tarea en curso; espera a que termine o cancelala.")
        tarea = Tarea(tipo)
        ESTADO.tarea = tarea

    def ejecutar():
        try:
            tarea.resultado = funcion(tarea, *args)
            tarea.estado = "cancelada" if tarea.cancelada else "terminada"
        except Exception as exc:  # se muestra en la pagina
            tarea.error = str(exc)
            tarea.estado = "error"

    threading.Thread(target=ejecutar, daemon=True).start()
    return tarea


def esperar_mensaje(tarea, proveedor, condicion, ignorar=(), maximo=ESPERA_MAXIMA):
    """Revisa la bandeja hasta que un mensaje cumpla `condicion(mensaje)`."""
    vistos = set(ignorar)
    pausa = app.PAUSA_NORMAL
    limite = time.time() + maximo
    while time.time() < limite and not tarea.cancelada:
        try:
            mensajes = proveedor.listar_mensajes()
            pausa = app.PAUSA_NORMAL
        except Exception as exc:
            pausa = app._siguiente_pausa(pausa, exc)
            tarea.paso(f"Mail.tm no respondio ({exc}); reintento en {pausa} s.")
            mensajes = []
        for resumen in mensajes:
            if resumen["id"] in vistos:
                continue
            try:
                completo = proveedor.leer_mensaje(resumen["id"])
            except Exception as exc:
                pausa = app._siguiente_pausa(pausa, exc)
                break
            vistos.add(resumen["id"])
            completo.setdefault("de", resumen.get("de"))
            completo.setdefault("asunto", resumen.get("asunto"))
            if condicion(completo):
                return completo
        for _ in range(pausa * 2):
            if tarea.cancelada:
                return None
            time.sleep(0.5)
    return None


def _ids_actuales(proveedor):
    try:
        return {m["id"] for m in proveedor.listar_mensajes()}
    except Exception:
        return set()


def recuperar_password(tarea, proveedor, correo):
    ya_estaban = _ids_actuales(proveedor)
    tarea.paso("Pidiendo a Retouch4me el correo de 'Forgot your password'...")
    tarea.paso(app.solicitar_recuperacion_retouch4me(correo))
    tarea.paso("Esperando el correo de recuperacion...")
    mensaje = esperar_mensaje(
        tarea, proveedor,
        lambda m: app.es_correo_recuperacion_retouch4me(m) or app._enlace_recuperacion_retouch4me(m),
        ignorar=ya_estaban)
    if not mensaje:
        raise RuntimeError("No llego el correo de recuperacion a tiempo.")
    password, enlace = app.datos_recuperacion_retouch4me(mensaje)
    tarea.paso("Correo de recuperacion recibido." + (" Contrasena nueva encontrada." if password else ""))
    return password, enlace


def tarea_registro(tarea, guardar):
    proveedor, correo = ESTADO.buzon()
    if not proveedor or correo in ESTADO.registrados:
        tarea.paso("Creando un correo nuevo para el registro...")
        proveedor, correo = nuevo_buzon()
    nombre = secrets.choice(app.NOMBRES).capitalize()
    apellido = secrets.choice(app.APELLIDOS)
    tarea.paso(f"Registrando {correo} como {nombre} {apellido}...")
    ya_estaban = _ids_actuales(proveedor)

    proveedor, correo, registro = app.registrar_con_reintento(
        proveedor, correo, nombre, apellido, avisar=tarea.paso)
    ESTADO.poner_buzon(proveedor, correo)
    ESTADO.registrados.add(correo)
    tarea.paso("Registro enviado. Esperando el correo de bienvenida con la contrasena...")

    def es_bienvenida(m):
        return app.extraer_credenciales_correo_retouch4me(m, correo_esperado=correo) is not None

    mensaje = esperar_mensaje(tarea, proveedor, es_bienvenida, ignorar=ya_estaban)
    if not mensaje:
        raise RuntimeError("No llego el correo de bienvenida a tiempo. Revisa la bandeja.")
    cred = app.extraer_credenciales_correo_retouch4me(
        mensaje, correo_esperado=correo, password_respaldo=registro.get("password"))
    if cred["password"]:
        tarea.paso("Contrasena temporal encontrada en el correo.")
    else:
        tarea.paso("El correo llego sin contrasena; pidiendo una nueva automaticamente...")
        password, _ = recuperar_password(tarea, proveedor, correo)
        cred["password"] = password

    tarea.paso("Iniciando sesion y verificando el correo...")
    estado = app.activar_cuenta_retouch4me(cred["email"], cred["password"], cred["verify_url"])
    tarea.paso("Sesion iniciada." if estado["sesion"] else "No se pudo comprobar el inicio de sesion.")
    if estado["verificado"]:
        tarea.paso("Correo verificado.")
    if guardar and cred["password"]:
        ruta = app.guardar_cuenta_retouch4me(cred)
        tarea.paso(f"Datos guardados en {os.path.basename(ruta)}.")
    return {**cred, **estado}


def tarea_recuperar(tarea):
    proveedor, correo = ESTADO.buzon()
    if not proveedor:
        raise RuntimeError("Primero necesitas el correo con el que te registraste.")
    password, enlace = recuperar_password(tarea, proveedor, correo)
    estado = {"sesion": False, "verificado": None}
    if password:
        with app._sesion_navegador() as sesion:
            estado["sesion"] = app.iniciar_sesion_retouch4me(sesion, correo, password)
        tarea.paso("Sesion iniciada con la contrasena nueva." if estado["sesion"]
                   else "No se pudo comprobar el inicio de sesion.")
    return {"email": correo, "password": password, "enlace": enlace, **estado}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def mensaje_para_pagina(m):
    enlaces = []
    for url, etiqueta in app.extraer_enlaces(m.get("texto"), m.get("html")):
        if app._url_https_segura(url):
            enlaces.append({"url": url, "texto": etiqueta or urlsplit(url).hostname})
    verificar, _ = app.clasificar_enlaces([(e["url"], e["texto"]) for e in enlaces])
    return {
        "de": m.get("de"), "asunto": m.get("asunto"),
        "texto": app.texto_legible(m), "html": m.get("html") or "",
        "enlaces": enlaces, "verificar": [u for u, _ in verificar],
    }


def api(metodo, ruta, consulta, cuerpo):
    if ruta == "/api/estado" and metodo == "GET":
        proveedor, correo = ESTADO.buzon()
        tarea = ESTADO.tarea.como_dict() if ESTADO.tarea else None
        return {"correo": correo, "tarea": tarea, "sistema": sys.platform}

    if ruta == "/api/correo" and metodo == "POST":
        _, correo = nuevo_buzon()
        return {"correo": correo}

    if ruta == "/api/mensajes" and metodo == "GET":
        proveedor, _ = ESTADO.buzon()
        return {"mensajes": proveedor.listar_mensajes() if proveedor else []}

    if ruta == "/api/mensaje" and metodo == "GET":
        proveedor, _ = ESTADO.buzon()
        if not proveedor:
            raise RuntimeError("No hay correo activo.")
        msg_id = (consulta.get("id") or [""])[0]
        return mensaje_para_pagina(proveedor.leer_mensaje(msg_id))

    if ruta == "/api/abrir" and metodo == "POST":
        url = str(cuerpo.get("url") or "")
        if not app._url_https_segura(url):
            raise RuntimeError("Solo se abren enlaces HTTPS.")
        if not app.abrir_incognito(url):
            webbrowser.open(url)
        return {"ok": True}

    if ruta == "/api/copiar" and metodo == "POST":
        return {"ok": app.copiar_portapapeles(str(cuerpo.get("texto") or ""))}

    if ruta == "/api/registro" and metodo == "POST":
        return lanzar_tarea("registro", tarea_registro, bool(cuerpo.get("guardar"))).como_dict()

    if ruta == "/api/recuperar" and metodo == "POST":
        return lanzar_tarea("recuperar", tarea_recuperar).como_dict()

    if ruta == "/api/cancelar" and metodo == "POST":
        if ESTADO.tarea:
            ESTADO.tarea.cancelada = True
        return {"ok": True}

    if ruta == "/api/limpiar-apex" and metodo == "POST":
        codigo = app.ejecutar_limpieza_apex()
        return {"codigo": codigo, "ok": codigo == 0}

    raise LookupError("Ruta desconocida")


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencio en la terminal
        pass

    def _responder(self, codigo, datos, tipo="application/json"):
        cuerpo = datos if isinstance(datos, bytes) else json.dumps(datos).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _atender(self, metodo):
        partes = urlsplit(self.path)
        if partes.path == "/" and metodo == "GET":
            with open(RUTA_PAGINA, encoding="utf-8") as f:
                pagina = f.read().replace("__TOKEN__", TOKEN)
            return self._responder(200, pagina.encode("utf-8"), "text/html")
        if not partes.path.startswith("/api/"):
            return self._responder(404, {"error": "No encontrado"})
        if self.headers.get("X-Token") != TOKEN:
            return self._responder(403, {"error": "Token invalido"})
        cuerpo = {}
        if metodo == "POST":
            largo = int(self.headers.get("Content-Length") or 0)
            if largo:
                try:
                    cuerpo = json.loads(self.rfile.read(largo).decode("utf-8") or "{}")
                except ValueError:
                    return self._responder(400, {"error": "JSON invalido"})
        try:
            self._responder(200, api(metodo, partes.path, parse_qs(partes.query), cuerpo))
        except LookupError as exc:
            self._responder(404, {"error": str(exc)})
        except Exception as exc:
            self._responder(500, {"error": str(exc)})

    def do_GET(self):
        self._atender("GET")

    def do_POST(self):
        self._atender("POST")


def main():
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    url = f"http://127.0.0.1:{PUERTO}/"
    print(f"Correo Temporal abierto en {url}")
    print("Deja esta ventana abierta mientras lo usas. Para cerrar: Ctrl+C.")
    if "--sin-navegador" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()

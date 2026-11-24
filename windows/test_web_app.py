import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import web_app
from web_app import app


class ProveedorFalso:
    """Buzon falso: el correo de bienvenida llega en la segunda consulta."""

    def __init__(self, texto_bienvenida):
        self.consultas = 0
        self.texto = texto_bienvenida

    def listar_mensajes(self):
        self.consultas += 1
        if self.consultas < 3:
            return []
        return [{"id": "m1", "de": "noreply@retouch4.me", "asunto": "Welcome to Retouch4me"}]

    def leer_mensaje(self, msg_id):
        return {"de": "noreply@retouch4.me", "asunto": "Welcome to Retouch4me",
                "texto": self.texto, "html": None}


BIENVENIDA = (
    "Login\n\nnuevo@x.com\n\nTemporary password\n\nuA4Fj\n\n"
    "\U0001F4A1 Tip: change it.\n\nVerify Email ( https://retouch4.me/email/verify/1/tok )"
)


class TareasTests(unittest.TestCase):
    def setUp(self):
        web_app.ESTADO = web_app.Estado()
        self.dormir = patch.object(web_app.time, "sleep")
        self.dormir.start()

    def tearDown(self):
        self.dormir.stop()

    def test_registro_completo_sin_preguntas(self):
        proveedor = ProveedorFalso(BIENVENIDA)
        tarea = web_app.Tarea("registro")
        with patch.object(app, "crear_correo_seguro_retouch4me", return_value=(proveedor, "nuevo@x.com")), \
                patch.object(app, "registrar_retouch4me", return_value={"email": "nuevo@x.com"}), \
                patch.object(app, "activar_cuenta_retouch4me",
                             return_value={"sesion": True, "verificado": True}) as activar:
            resultado = web_app.tarea_registro(tarea, False)
        self.assertEqual(resultado["password"], "uA4Fj")
        self.assertTrue(resultado["sesion"] and resultado["verificado"])
        activar.assert_called_once_with("nuevo@x.com", "uA4Fj", "https://retouch4.me/email/verify/1/tok")
        self.assertIn("nuevo@x.com", web_app.ESTADO.registrados)

    def test_registro_sin_password_pide_una_nueva(self):
        proveedor = ProveedorFalso(BIENVENIDA.replace("uA4Fj", ""))
        tarea = web_app.Tarea("registro")
        with patch.object(app, "crear_correo_seguro_retouch4me", return_value=(proveedor, "nuevo@x.com")), \
                patch.object(app, "registrar_retouch4me", return_value={"email": "nuevo@x.com"}), \
                patch.object(web_app, "recuperar_password", return_value=("Nw45rt", None)), \
                patch.object(app, "activar_cuenta_retouch4me",
                             return_value={"sesion": True, "verificado": True}):
            resultado = web_app.tarea_registro(tarea, False)
        self.assertEqual(resultado["password"], "Nw45rt")

    def test_correo_usado_crea_uno_nuevo(self):
        viejo = ProveedorFalso(BIENVENIDA)
        web_app.ESTADO.poner_buzon(viejo, "viejo@x.com")
        web_app.ESTADO.registrados.add("viejo@x.com")
        nuevo = ProveedorFalso(BIENVENIDA)
        with patch.object(app, "crear_correo_seguro_retouch4me", return_value=(nuevo, "nuevo@x.com")) as crear, \
                patch.object(app, "registrar_retouch4me", return_value={"email": "nuevo@x.com"}), \
                patch.object(app, "activar_cuenta_retouch4me", return_value={"sesion": True, "verificado": True}):
            web_app.tarea_registro(web_app.Tarea("registro"), False)
        crear.assert_called_once()
        self.assertEqual(web_app.ESTADO.buzon(), (nuevo, "nuevo@x.com"))

    def test_espera_se_puede_cancelar(self):
        tarea = web_app.Tarea("registro")
        tarea.cancelada = True
        self.assertIsNone(web_app.esperar_mensaje(tarea, ProveedorFalso(BIENVENIDA), lambda m: True))


class ServidorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), web_app.Manejador)
        cls.url = f"http://127.0.0.1:{cls.servidor.server_address[1]}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def _pedir(self, ruta, token=True, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        pedido = urllib.request.Request(self.url + ruta, data=datos)
        if token:
            pedido.add_header("X-Token", web_app.TOKEN)
        if datos:
            pedido.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(pedido) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_pagina_lleva_el_token(self):
        codigo, html = self._pedir("/", token=False)
        self.assertEqual(codigo, 200)
        self.assertIn(web_app.TOKEN, html)

    def test_api_exige_token(self):
        self.assertEqual(self._pedir("/api/estado", token=False)[0], 403)
        self.assertEqual(self._pedir("/api/estado")[0], 200)

    def test_abrir_solo_https(self):
        codigo, _ = self._pedir("/api/abrir", cuerpo={"url": "file:///etc/passwd"})
        self.assertEqual(codigo, 500)


if __name__ == "__main__":
    unittest.main()

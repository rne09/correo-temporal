import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


requests_falso = types.ModuleType("requests")


class HTTPError(Exception):
    pass


class Timeout(Exception):
    pass


requests_falso.HTTPError = HTTPError
requests_falso.Timeout = Timeout
requests_falso.Session = None
requests_falso.get = None
requests_falso.post = None
requests_falso.request = None
sys.modules["requests"] = requests_falso

app = importlib.import_module("temp_mail_app")


class RespuestaFalsa:
    def __init__(self, texto, estado=200):
        self.text = texto
        self.status_code = estado

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(f"HTTP {self.status_code}")


class RespuestaJsonFalsa(RespuestaFalsa):
    def __init__(self, datos, estado=200):
        super().__init__("", estado)
        self.datos = datos

    def json(self):
        return self.datos


class SesionFalsa:
    def __init__(self, respuesta_post):
        self.headers = {}
        self.respuesta_post = respuesta_post
        self.datos_post = None

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback):
        return False

    def get(self, url, timeout):
        self.url_get = url
        self.timeout_get = timeout
        return RespuestaFalsa('<meta name="csrf-token" content="token-prueba">')

    def post(self, url, data, headers, timeout):
        self.url_post = url
        self.datos_post = data
        self.headers_post = headers
        self.timeout_post = timeout
        if isinstance(self.respuesta_post, BaseException):
            raise self.respuesta_post
        return self.respuesta_post


class IntegracionRetouch4meTests(unittest.TestCase):
    def test_extrae_token_de_meta_o_input(self):
        meta = app._analizar_html_retouch4me(
            '<meta name="csrf-token" content="desde-meta">'
        )
        entrada = app._analizar_html_retouch4me(
            '<input type="hidden" name="_token" value="desde-input">'
        )

        self.assertEqual(meta.token, "desde-meta")
        self.assertEqual(entrada.token, "desde-input")

    def test_extrae_credenciales_con_etiquetas_anidadas(self):
        parser = app._analizar_html_retouch4me(
            """
            <ul class="user-form">
              <li class="user-form__input"><b>Email:</b> temporal@example.com</li>
              <li class="otra user-form__input"><span>Password:</span> Clave123</li>
            </ul>
            """
        )

        self.assertEqual(
            parser.credenciales,
            {"email": "temporal@example.com", "password": "Clave123"},
        )

    def test_registro_envia_correo_y_datos_del_usuario(self):
        respuesta = RespuestaFalsa(
            """
            <li class="user-form__input">Email: temporal@example.com</li>
            <li class="user-form__input">Password: Clave123</li>
            """
        )
        sesion = SesionFalsa(respuesta)
        sesion_original = app.requests.Session
        app.requests.Session = lambda: sesion
        try:
            credenciales = app.registrar_retouch4me(
                "temporal@example.com", "Ana", "Perez"
            )
        finally:
            app.requests.Session = sesion_original

        self.assertEqual(credenciales, {"email": "temporal@example.com", "password": "Clave123"})
        self.assertEqual(sesion.datos_post["_token"], "token-prueba")
        self.assertEqual(sesion.datos_post["email"], "temporal@example.com")
        self.assertEqual(sesion.datos_post["name"], "Ana")
        self.assertEqual(sesion.datos_post["last_name"], "Perez")
        self.assertEqual(sesion.datos_post["agree_eula"], "1")
        self.assertEqual(sesion.datos_post["subscribe"], "0")

    def test_informa_rechazo_http_sin_confiar_en_texto_oculto(self):
        sesion = SesionFalsa(
            RespuestaFalsa("This E-mail is already registered", estado=422)
        )
        sesion_original = app.requests.Session
        app.requests.Session = lambda: sesion
        try:
            with self.assertRaisesRegex(app.ErrorRegistroRetouch4me, "HTTP 422"):
                app.registrar_retouch4me("usado@example.com", "Ana", "Perez")
        finally:
            app.requests.Session = sesion_original

    def test_texto_oculto_no_se_clasifica_como_correo_duplicado(self):
        sesion = SesionFalsa(
            RespuestaFalsa("This E-mail is already registered", estado=200)
        )
        sesion_original = app.requests.Session
        app.requests.Session = lambda: sesion
        try:
            with self.assertRaisesRegex(app.ErrorRegistroRetouch4me, "no confirmo"):
                app.registrar_retouch4me("nuevo@example.com", "Ana", "Perez")
        finally:
            app.requests.Session = sesion_original

    def test_rechaza_credenciales_de_otro_correo(self):
        sesion = SesionFalsa(RespuestaFalsa(
            """
            <li class="user-form__input">Email: otro@example.com</li>
            <li class="user-form__input">Password: Clave123</li>
            """
        ))
        sesion_original = app.requests.Session
        app.requests.Session = lambda: sesion
        try:
            with self.assertRaisesRegex(app.ErrorRegistroRetouch4me, "correo distinto"):
                app.registrar_retouch4me("temporal@example.com", "Ana", "Perez")
        finally:
            app.requests.Session = sesion_original

    def test_timeout_advierte_que_el_resultado_es_incierto(self):
        sesion = SesionFalsa(Timeout("sin respuesta"))
        sesion_original = app.requests.Session
        app.requests.Session = lambda: sesion
        try:
            with self.assertRaisesRegex(app.ErrorRegistroRetouch4me, "resultado es incierto"):
                app.registrar_retouch4me("temporal@example.com", "Ana", "Perez")
        finally:
            app.requests.Session = sesion_original

    def test_mailtm_convierte_html_en_lista_a_texto(self):
        proveedor = app.ProveedorMailTm()
        proveedor.token = "token"
        respuesta = RespuestaJsonFalsa({
            "from": {"address": "servicio@example.com"},
            "subject": "Bienvenido",
            "text": None,
            "html": ["<p>Hola</p>", "<a href='https://example.com'>Abrir</a>"],
        })
        with patch.object(app.requests, "request", return_value=respuesta):
            mensaje = proveedor.leer_mensaje("mensaje-1")

        self.assertEqual(
            mensaje["html"],
            "<p>Hola</p>\n<a href='https://example.com'>Abrir</a>",
        )

    def test_limpieza_apex_se_lanza_en_modo_automatico(self):
        ruta = r"D:\ANDERSON_RENE_FOTOGRAFO\Retouch\limpieza.bat"
        resultado = types.SimpleNamespace(returncode=0)
        with (
            patch.object(app, "_ruta_limpieza_apex", return_value=ruta),
            patch.object(app.os, "name", "nt"),
            patch.object(app.os.path, "isfile", return_value=True),
            patch.object(app.subprocess, "run", return_value=resultado) as ejecutar,
        ):
            codigo = app.ejecutar_limpieza_apex()

        self.assertEqual(codigo, 0)
        argumentos = ejecutar.call_args.args[0]
        self.assertEqual(argumentos[-1], "/AUTO")
        self.assertEqual(argumentos[-3], "call")
        self.assertEqual(argumentos[-2], ruta)
        self.assertFalse(ejecutar.call_args.kwargs["check"])

    def test_solo_clasifica_enlaces_https_sin_credenciales(self):
        enlaces = [
            ("https://retouch4.me/verify/token", "Verify account"),
            ("http://retouch4.me/verify/inseguro", "Verify account"),
            ("https://usuario:clave@retouch4.me/verify", "Verify account"),
        ]

        verificar, otros = app.clasificar_enlaces(enlaces)

        self.assertEqual(verificar, [enlaces[0]])
        self.assertEqual(otros, [])


    def test_detecta_enlace_de_verificacion_retouch4me(self):
        mensaje = {
            "texto": "Confirma tu cuenta: https://retouch4.me/email/verify/123/token123",
            "html": "",
        }

        self.assertEqual(
            app._enlace_verificacion_retouch4me(mensaje),
            "https://retouch4.me/email/verify/123/token123",
        )

    def test_confirmacion_humana_abre_la_cuenta(self):
        with (
            patch.object(app, "preguntar", return_value="s"),
            patch.object(app, "_abrir") as abrir,
        ):
            resultado = app.confirmar_verificacion_y_abrir_cuenta(
                "https://retouch4.me/verify/token123"
            )

        self.assertTrue(resultado)
        abrir.assert_called_once_with(app.RETOUCH_ACCOUNT_URL)


    def test_extrae_login_password_temporal_y_verify_email_del_correo(self):
        mensaje = {
            "texto": (
                "Login\n"
                "daniel9467@uberip.com\n\n"
                "Temporary password\n"
                "u4rJf\n\n"
                "To complete your registration and unlock all features, please verify your email address.\n"
                "Verify Email ( https://retouch4.me/email/verify/4216923/"
                "0ac6d91a895d0ad0bb982af451ce648c5cc5e326e1073476f76f09791d580617 )"
            ),
            "html": "",
        }

        datos = app.extraer_credenciales_correo_retouch4me(
            mensaje, correo_esperado="daniel9467@uberip.com"
        )

        self.assertEqual(datos["email"], "daniel9467@uberip.com")
        self.assertEqual(datos["password"], "u4rJf")
        self.assertTrue(datos["verify_url"].startswith("https://retouch4.me/email/verify/4216923/"))

    def test_no_acepta_correo_de_otro_login(self):
        mensaje = {
            "texto": (
                "Login\notro@uberip.com\nTemporary password\nAbC12\n"
                "https://retouch4.me/email/verify/123/token"
            ),
            "html": "",
        }

        datos = app.extraer_credenciales_correo_retouch4me(
            mensaje, correo_esperado="esperado@uberip.com"
        )

        self.assertIsNone(datos)

    def test_guardado_usa_password_del_correo_y_verify_url(self):
        datos = {
            "email": "temporal@example.com",
            "password": "Tmp9Z",
            "verify_url": "https://retouch4.me/email/verify/123/token",
        }
        import tempfile
        with tempfile.TemporaryDirectory() as carpeta:
            with patch.object(app, "_directorio_aplicacion", return_value=carpeta):
                ruta = app.guardar_cuenta_retouch4me(datos)
            contenido = Path(ruta).read_text(encoding="utf-8")

        self.assertIn("temporal@example.com | Tmp9Z | https://retouch4.me/email/verify/123/token", contenido)


class MejorasMacTests(unittest.TestCase):
    def _mensajes(self):
        return [
            {"id": "6af3517da9173c9999abc", "de": "a@x.com", "asunto": "uno"},
            {"id": "bbb222", "de": "b@x.com", "asunto": "dos"},
        ]

    def test_resolver_id_por_numero_id_completo_y_parcial(self):
        mensajes = self._mensajes()
        self.assertEqual(app.resolver_id_mensaje(None, "1", mensajes), "6af3517da9173c9999abc")
        self.assertEqual(app.resolver_id_mensaje(None, "2", mensajes), "bbb222")
        self.assertEqual(app.resolver_id_mensaje(None, "6af3517da9173c", mensajes), "6af3517da9173c9999abc")
        self.assertEqual(app.resolver_id_mensaje(None, "bbb222", mensajes), "bbb222")

    def _extraer(self, texto, html=None, respaldo=None):
        mensaje = {
            "texto": texto + "\nVerify Email: https://retouch4.me/email/verify/1/tok",
            "html": html,
        }
        return app.extraer_credenciales_correo_retouch4me(
            mensaje, correo_esperado="a@b.com", password_respaldo=respaldo
        )

    def test_password_salta_iconos(self):
        datos = self._extraer("Login: a@b.com\nTemporary password: \U0001F4A1 Xk9pL2q")
        self.assertEqual(datos["password"], "Xk9pL2q")

    def test_password_desde_html(self):
        datos = self._extraer(
            "Login: a@b.com\nTemporary password: \U0001F4A1",
            html="<p>Temporary password: <b>Ht789</b></p>",
        )
        self.assertEqual(datos["password"], "Ht789")

    def test_password_de_respaldo_si_el_correo_no_la_trae(self):
        datos = self._extraer("Login: a@b.com\nTemporary password: \U0001F4A1", respaldo="Pg123")
        self.assertEqual(datos["password"], "Pg123")

    def test_password_del_correo_tiene_prioridad(self):
        datos = self._extraer("Login: a@b.com\nTemporary password: Real1", respaldo="Pg123")
        self.assertEqual(datos["password"], "Real1")

    def test_sin_password_devuelve_login_y_enlace(self):
        datos = self._extraer("Login: a@b.com\nTemporary password: \U0001F4A1")
        self.assertIsNone(datos["password"])
        self.assertEqual(datos["email"], "a@b.com")

    def test_enlace_de_recuperacion(self):
        mensaje = {"texto": "Reset: https://retouch4.me/auth/password/reset/abc123 "
                            "https://retouch4.me/email/verify/1/x", "html": None}
        self.assertEqual(app._enlace_recuperacion_retouch4me(mensaje),
                         "https://retouch4.me/auth/password/reset/abc123")
        self.assertIsNone(app._enlace_recuperacion_retouch4me(
            {"texto": "https://otro.com/reset/x", "html": None}))

    def test_solicitar_recuperacion_envia_correo_y_token(self):
        class Resp(RespuestaJsonFalsa):
            pass

        class Sesion:
            def __init__(self):
                self.headers = {}
                self.enviado = None

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, data=None, headers=None, timeout=None):
                self.enviado = (url, data, headers)
                return Resp({"message": "A password reset link has been sent"})

        sesion = Sesion()
        with patch.object(app.requests, "Session", return_value=sesion), \
                patch.object(app, "_obtener_token_retouch4me", return_value="tok"):
            mensaje = app.solicitar_recuperacion_retouch4me("a@b.com")
        self.assertIn("reset link", mensaje)
        url, data, headers = sesion.enviado
        self.assertEqual(url, app.RETOUCH_RECOVERY_URL)
        self.assertEqual(data["email"], "a@b.com")
        self.assertEqual(headers["X-CSRF-TOKEN"], "tok")

    def test_recuperacion_rechazada_muestra_motivo(self):
        class Sesion:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, *a, **k):
                return RespuestaJsonFalsa({"error": "Invalid email"}, 422)

        with patch.object(app.requests, "Session", return_value=Sesion()), \
                patch.object(app, "_obtener_token_retouch4me", return_value="tok"):
            with self.assertRaises(app.ErrorRegistroRetouch4me) as ctx:
                app.solicitar_recuperacion_retouch4me("a@b.com")
        self.assertIn("Invalid email", str(ctx.exception))

    def test_pausa_crece_con_429_y_tiene_tope(self):
        exc = HTTPError("429 Client Error: Too Many Requests")
        pausa = app.PAUSA_NORMAL
        for _ in range(10):
            pausa = app._siguiente_pausa(pausa, exc)
        self.assertEqual(pausa, app.PAUSA_MAXIMA)
        self.assertEqual(app._siguiente_pausa(5, HTTPError("500 Server Error")), 5)

    def test_espera_no_pierde_el_correo_si_leerlo_da_429(self):
        class Proveedor:
            lecturas = 0

            def listar_mensajes(self):
                return [{"id": "m1", "de": "x", "asunto": "y"}]

            def leer_mensaje(self, msg_id):
                self.lecturas += 1
                if self.lecturas == 1:
                    raise HTTPError("429 Client Error")
                return {
                    "de": "x", "asunto": "y", "html": None,
                    "texto": "Login: a@b.com\nTemporary password: Abc123\n"
                             "Verify Email: https://retouch4.me/email/verify/1/tok",
                }

        with patch.object(app.time, "sleep"), patch("builtins.print"):
            datos = app.esperar_verificacion_retouch4me(Proveedor(), "a@b.com")
        self.assertEqual(datos["password"], "Abc123")

    def test_mailtm_reintenta_tras_429(self):
        class Resp429(RespuestaJsonFalsa):
            headers = {"Retry-After": "1"}

        respuestas = [Resp429({}, 429), RespuestaJsonFalsa({"hydra:member": []})]
        proveedor = app.ProveedorMailTm()
        proveedor.token = "t"
        with patch.object(app.requests, "request", side_effect=respuestas), \
                patch.object(app.time, "sleep") as dormir:
            self.assertEqual(proveedor.listar_mensajes(), [])
        dormir.assert_called_once_with(1)

    def test_mailtm_renueva_token_caducado(self):
        respuestas = [
            RespuestaJsonFalsa({}, 401),
            RespuestaJsonFalsa({"token": "nuevo"}),
            RespuestaJsonFalsa({"hydra:member": []}),
        ]
        proveedor = app.ProveedorMailTm()
        proveedor.token, proveedor.address, proveedor.password = "viejo", "a@b.com", "p"
        with patch.object(app.requests, "request", side_effect=respuestas):
            self.assertEqual(proveedor.listar_mensajes(), [])
        self.assertEqual(proveedor.token, "nuevo")

    def test_limpieza_apex_avisa_fuera_de_windows(self):
        with patch.object(app, "_ruta_limpieza_apex", return_value="/tmp/x.bat"), \
                patch.object(app.os.path, "isfile", return_value=True), \
                patch.object(app.os, "name", "posix"):
            with self.assertRaises(RuntimeError):
                app.ejecutar_limpieza_apex()

    def test_portapapeles_en_mac_usa_pbcopy(self):
        with patch.object(app.os, "name", "posix"), patch.object(app.sys, "platform", "darwin"), \
                patch.object(app.shutil, "which", return_value="/usr/bin/pbcopy"), \
                patch.object(app.subprocess, "run") as ejecutar:
            self.assertTrue(app.copiar_portapapeles("hola"))
        self.assertEqual(ejecutar.call_args.args[0], ["pbcopy"])


if __name__ == "__main__":
    unittest.main()

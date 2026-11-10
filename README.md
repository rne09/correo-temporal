# Correo Temporal

Programa en Python con menu para generar correos temporales usando la API publica de [mail.tm](https://mail.tm), leer los mensajes en tiempo real (con sus enlaces) y registrar o recuperar cuentas de Retouch4me con ese correo.

## Carpetas

| Carpeta | Para | Como abrirlo |
|---|---|---|
| [`mac/`](mac) | macOS | Doble clic en `Correo temporal.command` |
| [`windows/`](windows) | Windows | Doble clic en `CorreoTemporal.bat` |

Las dos carpetas tienen el mismo `temp_mail_app.py`: el programa detecta el sistema y usa lo que corresponde (por ejemplo `pbcopy` en Mac y `clip.exe` en Windows). Cualquier cambio debe copiarse a ambas carpetas.

## Instalacion

### macOS
1. Descarga o clona el repositorio.
2. Doble clic en `mac/Correo temporal.command`. La primera vez crea un entorno de Python en `~/.venvs/correo-temporal` e instala `requests`.
3. Si macOS lo bloquea: clic derecho → **Abrir** → **Abrir** (solo la primera vez).

Desde la terminal:

```bash
cd mac
python3 -m pip install requests
python3 temp_mail_app.py
```

### Windows
```bash
pip install requests
```
Despues, doble clic en `windows/CorreoTemporal.bat` (o `python temp_mail_app.py`).

## Menu

1. **Crear correo nuevo**
2. **Ver bandeja de entrada**: los mensajes salen numerados (`1`, `2`, `3`...).
3. **Esperar correos en tiempo real**
4. **Leer un mensaje**: muestra la bandeja y basta con escribir el numero. Tambien acepta el ID completo o solo su comienzo.
5. **Copiar correo al portapapeles** (Mac y Windows)
6. **Registrarse en Retouch4me con correo temporal**
7. **Limpiar sesion de Apex y conservar Quinces** (solo Windows)
8. **Recuperar contrasena de Retouch4me** (Forgot password)
0. **Salir**

## Novedades

- **Version para Mac** en su propia carpeta, con lanzador de doble clic que se instala solo.
- **Leer mensajes por numero**: corrige el error `404 Not Found` que salia al pegar un ID recortado de la bandeja.
- **Registro sin preguntas**: el nombre y el apellido se generan al azar.
- **Contrasena temporal mas fiable**:
  - ignora iconos (como 💡) delante de la contrasena;
  - la busca tambien en la version HTML del correo;
  - si el correo no la trae, usa la que muestra la web al registrarse;
  - al terminar el registro siempre pregunta si quieres generar una contrasena nueva con "Forgot your password" (la respuesta por defecto es **si** cuando el correo no trajo contrasena).
- **Opcion 8, recuperar contrasena**: pide el correo de "Forgot your password?" a Retouch4me, lo espera en el buzon temporal y abre el enlace para crear la contrasena nueva.
- **Enlace de verificacion completo** debajo del cuadro de credenciales, para abrirlo con Cmd + clic (Mac) o Ctrl + clic (Windows).
- **Limites de mail.tm (error 429)**: el programa espera y reintenta solo (5 s normal, hasta 60 s si mail.tm pide ir mas despacio) y no pierde un correo que no pudo leer.
- **Sesion de mail.tm caducada**: se renueva automaticamente.
- **Correo ya usado**: si el correo actual ya se uso para un registro, la opcion 6 crea uno nuevo (Retouch4me rechaza correos repetidos).
- **Errores de registro mas claros**: muestra el mensaje de la web y guarda la pagina en `ultimo_registro_retouch4me.html`.
- **Portapapeles en Mac** con `pbcopy`.

## Pruebas

Desde la carpeta `mac/` o `windows/`:

```bash
python3 -m unittest test_temp_mail_app
```

## Privacidad

`cuentas_retouch4me.txt` (donde la opcion 6 guarda las cuentas si lo pides) contiene contrasenas sin cifrar y esta en `.gitignore`: no lo subas al repositorio.

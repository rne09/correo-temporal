# Correo Temporal

Programa sencillo en Python con menu para generar correos temporales usando la API publica de [mail.tm](https://mail.tm) y leer los mensajes recibidos en tiempo real, incluyendo los enlaces que contengan.

## Requisitos

```bash
pip install requests
```

## Uso

Doble clic en `CorreoTemporal.bat`, o desde consola:

```bash
python temp_mail_app.py
```

Menu:
1. Crear correo nuevo
2. Ver bandeja de entrada
3. Esperar y mostrar correos en tiempo real
4. Leer un mensaje (con enlaces detectados y opcion de abrirlos)

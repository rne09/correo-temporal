#!/usr/bin/env python3
"""
Correo temporal - programa sencillo con menu (usa la API publica de mail.tm)
"""
import time
import random
import re
import string
import webbrowser
import requests

API = "https://api.mail.tm"

NOMBRES = [
    "carlos", "andres", "sofia", "valeria", "mateo", "diego", "camila",
    "lucas", "martina", "sebastian", "isabella", "santiago", "valentina",
    "daniel", "gabriela", "julian", "renata", "nicolas", "paula", "emilio",
    "laura", "esteban", "daniela", "felipe", "natalia", "alejandro", "sara",
]


def random_string(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def nombre_aleatorio():
    return f"{random.choice(NOMBRES)}{random.randint(100, 9999)}"


def elegir_dominio():
    dominios = requests.get(f"{API}/domains").json()["hydra:member"]
    dominios_activos = [d["domain"] for d in dominios if d.get("isActive") and not d.get("isPrivate")]
    if not dominios_activos:
        dominios_activos = [dominios[0]["domain"]]

    if len(dominios_activos) == 1:
        return dominios_activos[0]

    print("\nDominios disponibles:")
    for i, d in enumerate(dominios_activos, 1):
        print(f"  [{i}] @{d}")
    eleccion = input("Elige un dominio (Enter para el primero): ").strip()
    if eleccion.isdigit() and 1 <= int(eleccion) <= len(dominios_activos):
        return dominios_activos[int(eleccion) - 1]
    return dominios_activos[0]


def crear_cuenta():
    dominio = elegir_dominio()
    password = random_string(12)

    ultimo_error = None
    for _ in range(5):
        usuario = nombre_aleatorio()
        address = f"{usuario}@{dominio}"
        r = requests.post(f"{API}/accounts", json={"address": address, "password": password})
        if r.status_code == 201:
            break
        ultimo_error = r.text
    else:
        raise RuntimeError(f"No se pudo crear la cuenta: {ultimo_error}")

    token_resp = requests.post(f"{API}/token", json={"address": address, "password": password})
    token_resp.raise_for_status()
    token = token_resp.json()["token"]

    return address, token


def listar_mensajes(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/messages", headers=headers)
    r.raise_for_status()
    return r.json()["hydra:member"]


def leer_mensaje(token, msg_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/messages/{msg_id}", headers=headers)
    r.raise_for_status()
    return r.json()


URL_RE = re.compile(r'href=["\'](https?://[^"\']+)["\']|(https?://[^\s<>"\']+)')


def extraer_enlaces(mensaje):
    contenido = " ".join(mensaje.get("html") or []) if isinstance(mensaje.get("html"), list) else (mensaje.get("html") or "")
    contenido += " " + (mensaje.get("text") or "")
    encontrados = []
    for a, b in URL_RE.findall(contenido):
        url = a or b
        if url not in encontrados:
            encontrados.append(url)
    return encontrados


def mostrar_enlaces_y_elegir(enlaces):
    if not enlaces:
        return
    print("\nEnlaces encontrados:")
    for i, url in enumerate(enlaces, 1):
        print(f"  [{i}] {url}")
    print("  [0] No abrir ninguno")
    eleccion = input("Elige un enlace para abrir en el navegador: ").strip()
    if eleccion.isdigit() and 1 <= int(eleccion) <= len(enlaces):
        webbrowser.open(enlaces[int(eleccion) - 1])


def pausa():
    input("\nPresiona Enter para continuar...")


def menu():
    correo = None
    token = None

    while True:
        print("\n=== Correo temporal (mail.tm) ===")
        print(f"Cuenta actual: {correo or '(ninguna)'}")
        print("1) Crear correo nuevo")
        print("2) Ver bandeja de entrada")
        print("3) Esperar y mostrar correos en tiempo real")
        print("4) Leer un mensaje")
        print("0) Salir")
        opcion = input("Elige una opcion: ").strip()

        if opcion == "1":
            correo, token = crear_cuenta()
            print(f"\nCorreo creado: {correo}")

        elif opcion == "2":
            if not token:
                print("Primero crea un correo (opcion 1).")
            else:
                mensajes = listar_mensajes(token)
                if not mensajes:
                    print("Bandeja vacia.")
                for m in mensajes:
                    print(f"[{m['id']}] de: {m['from']['address']}  asunto: {m['subject']}")
            pausa()

        elif opcion == "3":
            if not token:
                print("Primero crea un correo (opcion 1).")
            else:
                print("Esperando correos nuevos... (Ctrl+C para cancelar)\n")
                vistos = set()
                try:
                    while True:
                        mensajes = listar_mensajes(token)
                        nuevos = [m for m in mensajes if m["id"] not in vistos]
                        for m in nuevos:
                            vistos.add(m["id"])
                            completo = leer_mensaje(token, m["id"])
                            print(f"\n>>> Nuevo correo de: {completo['from']['address']}")
                            print(f"Asunto: {completo['subject']}")
                            print("---")
                            print(completo.get("text") or completo.get("html"))
                            mostrar_enlaces_y_elegir(extraer_enlaces(completo))
                            print("===========================================")
                        time.sleep(3)
                except KeyboardInterrupt:
                    print("\nCancelado.")
            pausa()

        elif opcion == "4":
            if not token:
                print("Primero crea un correo (opcion 1).")
            else:
                msg_id = input("ID del mensaje: ").strip()
                m = leer_mensaje(token, msg_id)
                print(f"\nDe: {m['from']['address']}")
                print(f"Asunto: {m['subject']}")
                print("---")
                print(m.get("text") or m.get("html"))
                mostrar_enlaces_y_elegir(extraer_enlaces(m))
            pausa()

        elif opcion == "0":
            break

        else:
            print("Opcion invalida.")


if __name__ == "__main__":
    try:
        menu()
    except Exception as e:
        print(f"\nError: {e}")
        input("Presiona Enter para salir...")

#!/bin/zsh
# Doble clic para abrir Correo temporal en el navegador (macOS).
# Deja la ventana de Terminal abierta mientras lo usas.
cd "$(dirname "$0")" || exit 1
V="$HOME/.venvs/correo-temporal"
if [ ! -x "$V/bin/python" ]; then
  echo "Preparando Python por primera vez..."
  python3 -m venv "$V" && "$V/bin/pip" install -q requests || { echo "No se pudo instalar requests."; read -r; exit 1; }
fi
"$V/bin/python" web_app.py

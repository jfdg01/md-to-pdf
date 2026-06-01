#!/usr/bin/env bash
# Instalador Linux: crea el venv, instala dependencias y enlaza el launcher en
# ~/.local/bin para poder llamar a "md-to-pdf" desde cualquier sitio.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Creando venv en $DIR/.venv ..."
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

chmod +x "$DIR/md-to-pdf"
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/md-to-pdf" "$HOME/.local/bin/md-to-pdf"

echo ""
echo "Listo. Asegúrate de que ~/.local/bin está en el PATH y prueba:"
echo "  md-to-pdf archivo.md"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "  (añade a ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\")" ;;
esac

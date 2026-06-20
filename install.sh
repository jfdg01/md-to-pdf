#!/usr/bin/env bash
# Instalador Linux: crea el venv con uv, instala dependencias desde el lockfile y
# enlaza el launcher en ~/.local/bin para llamar a "md-to-pdf" desde cualquier sitio.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv no está instalado. Instálalo con:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

echo "Creando .venv e instalando dependencias con uv ..."
( cd "$DIR" && uv sync )

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

# md-to-pdf

Convierte ficheros Markdown en un PDF con **portada**, **índice navegable** y
**cabecera/pie** en cada página. Pensado para trabajos y memorias académicas.

El render lo hace **Google Chrome** en modo headless (vía CDP), así que el
resultado es idéntico a imprimir desde el navegador. Las fuentes (Source Serif 4,
Space Grotesk, Space Mono) viajan con el repositorio en `fonts/`.

---

## Requisitos

- **Python 3** (3.10+).
- **Google Chrome** o **Chromium** instalado.
  - Linux: `google-chrome` / `chromium` en el `PATH`.
  - Windows: Chrome en la ruta habitual de *Program Files* (se detecta solo).

Las dependencias de Python (`markdown`, `websocket-client`, `pypdf`) se instalan
en un entorno virtual propio (`.venv/`) por el script de instalación.

---

## Instalación

El instalador crea el `.venv`, instala dependencias y registra el comando global
`md-to-pdf`.

### Linux / Ubuntu
```bash
cd ~/.local/scripts        # o donde tengas clonado el repo
bash install.sh
```
Esto enlaza `md-to-pdf` en `~/.local/bin`. Asegúrate de que ese directorio está
en tu `PATH` (si no, añade a `~/.bashrc`):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Windows
```powershell
cd $env:USERPROFILE\Documents\Universidad\md-to-pdf   # ruta del repo
.\install.ps1
```
Añade la carpeta del repo al `PATH` de usuario. **Abre una terminal nueva** para
que el comando `md-to-pdf` quede disponible.

> El `.venv/` es propio de cada máquina (Windows y Linux no son compatibles) y
> está en `.gitignore`. Ejecuta el instalador una vez por equipo tras clonar.

---

## Uso

```bash
# Convierte UN fichero (genera informe.pdf junto al .md)
md-to-pdf informe.md

# Convierte VARIOS ficheros
md-to-pdf tema1.md tema2.md

# Sin argumentos: convierte TODOS los .md del directorio actual
md-to-pdf
```

Cada PDF se escribe junto a su `.md` de origen, con el mismo nombre.

---

## Cómo estructurar el Markdown

El documento tiene **dos partes** separadas por una línea `---`:

1. **Bloque de portada** (antes del `---`): el título y los metadatos.
2. **Cuerpo** (después del `---`): el contenido que se paginará.

```markdown
# Título del trabajo

**Asignatura:** Nombre de la asignatura
**Máster en Ciberseguridad**
**Curso:** 2025/2026
**Autor:** Tu Nombre Completo

---

## 1. Introducción

Texto de la primera sección...

### 1.1 Un subapartado

Más texto...

## 2. Siguiente sección

...
```

### Metadatos reconocidos (bloque de portada)

| Campo            | Cómo se escribe                       | Dónde aparece                |
|------------------|---------------------------------------|------------------------------|
| Título           | `# Título` (primer encabezado `#`)    | Portada + cabecera de página |
| Asignatura       | `**Asignatura:** ...`                 | Portada + cabecera de página |
| Máster           | `**Máster ...**` (línea en negrita)   | Portada                      |
| Curso            | `**Curso:** 2025/2026`                | Portada ("Curso 2025/2026")  |
| Autor            | `**Autor:** Nombre`                   | Portada + pie de página      |

Todos son opcionales salvo el título. El orden no importa.

### Reglas del cuerpo

- **`## ` = sección.** Cada encabezado de nivel 2 empieza en una **página
  nueva** (la primera no, para no dejar un hueco tras el índice). Numéralas
  `## 1. ...`, `## 2. ...` si quieres numeración.
- **`### ` = subsección.** No fuerza salto de página.
- **El índice** lista automáticamente los `##` y `###`, con enlaces que saltan
  a la sección correspondiente al hacer clic.
- Funciona el Markdown habitual: **negrita**, *cursiva*, listas, tablas,
  `código` en línea y bloques con triple acento grave (```` ``` ````), citas.

### Logo de portada (opcional)

Si colocas una imagen llamada `logo_uja.webp`, `logo_uja.png`, `logo.webp` o
`logo.png` junto al `.md` (o junto al script), se incrusta centrada en la
portada.

---

## Notas

- Cabecera y pie se dibujan como una capa PDF con la fuente (Space Grotesk)
  embebida, así que se ven igual en Windows y Linux sin instalar nada. El cuerpo
  usa también las fuentes incrustadas en `fonts/` en ambos sistemas.
- El tamaño de página es A4.

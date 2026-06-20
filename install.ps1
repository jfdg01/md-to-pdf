# Instalador Windows: crea el venv con uv, instala dependencias desde el lockfile
# y añade el repo al PATH de usuario para llamar a "md-to-pdf" desde cualquier terminal.
$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv no está instalado. Instálalo con:"
    Write-Host "  powershell -ExecutionPolicy ByPass -c ""irm https://astral.sh/uv/install.ps1 | iex"""
    exit 1
}

Write-Host "Creando .venv e instalando dependencias con uv ..."
Push-Location $dir
uv sync
Pop-Location

# El launcher md-to-pdf.cmd vive en src\, así que es esa carpeta la que va al PATH.
$launcherDir = Join-Path $dir "src"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$launcherDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$launcherDir", "User")
    Write-Host "Carpeta src añadida al PATH de usuario."
} else {
    Write-Host "El launcher ya estaba en el PATH."
}

Write-Host ""
Write-Host "Listo. Abre una terminal NUEVA y prueba:  md-to-pdf archivo.md"

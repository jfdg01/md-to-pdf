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

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dir", "User")
    Write-Host "Repo añadido al PATH de usuario."
} else {
    Write-Host "El repo ya estaba en el PATH."
}

Write-Host ""
Write-Host "Listo. Abre una terminal NUEVA y prueba:  md-to-pdf archivo.md"

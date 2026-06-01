# Instalador Windows: crea el venv, instala dependencias y añade el repo al PATH
# de usuario para poder llamar a "md-to-pdf" desde cualquier terminal.
$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

Write-Host "Creando venv en $dir\.venv ..."
python -m venv "$dir\.venv"
& "$dir\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$dir\.venv\Scripts\python.exe" -m pip install -r "$dir\requirements.txt"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dir", "User")
    Write-Host "Repo añadido al PATH de usuario."
} else {
    Write-Host "El repo ya estaba en el PATH."
}

Write-Host ""
Write-Host "Listo. Abre una terminal NUEVA y prueba:  md-to-pdf archivo.md"

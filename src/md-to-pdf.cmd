@echo off
REM Launcher Windows: usa el Python del venv del propio repo.
REM El script vive en src\ y el venv en la raíz del repo (un nivel por encima).
"%~dp0..\.venv\Scripts\python.exe" "%~dp0md_to_pdf.py" %*

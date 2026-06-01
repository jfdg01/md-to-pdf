@echo off
REM Launcher Windows: usa el Python del venv del propio repo.
"%~dp0.venv\Scripts\python.exe" "%~dp0md_to_pdf.py" %*

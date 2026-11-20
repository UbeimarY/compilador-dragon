@echo off
rem Ejecuta todos los pasos de la guia de estudio en Windows.
rem Doble clic sobre este archivo, o en una terminal:  ejecutar_guia.bat
chcp 65001 >nul
cd /d "%~dp0"

set PY=python
%PY% --version >nul 2>nul || set PY=py
%PY% --version >nul 2>nul || (
  echo No se encontro Python. Instale Python 3.10 o superior desde python.org
  echo y marque "Add python.exe to PATH" en el instalador.
  pause
  exit /b 1
)

if not exist main.py (
  if not exist compilador-dragon (
    where git >nul 2>nul && (
      git clone https://github.com/UbeimarY/compilador-dragon.git
    ) || (
      echo Descargando el proyecto como ZIP...
      powershell -NoProfile -Command "Invoke-WebRequest https://github.com/UbeimarY/compilador-dragon/archive/refs/heads/main.zip -OutFile compilador-dragon.zip; Expand-Archive compilador-dragon.zip .; Rename-Item compilador-dragon-main compilador-dragon"
    )
  )
  cd compilador-dragon
)

%PY% --version
%PY% docs\verificar_guia.py
echo.
echo El detalle de cada comando quedo en registro_guia.txt
pause

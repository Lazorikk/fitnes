@echo off
setlocal
cd /d "%~dp0"
set "BOGINI_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%BOGINI_PYTHON%" goto :check_version

py -3 -m venv ".venv" 2>nul
if not errorlevel 1 goto :check_version
python -m venv ".venv"
if errorlevel 1 goto :python_missing

:check_version
"%BOGINI_PYTHON%" -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 goto :python_missing

"%BOGINI_PYTHON%" -c "from PySide6 import QtWidgets; from PIL import ImageQt" >nul 2>&1
if not errorlevel 1 goto :run
if /i "%~1"=="--check" exit /b 0
"%BOGINI_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :failed

:run
if /i "%~1"=="--check" exit /b 0
"%BOGINI_PYTHON%" "%~dp0main.py"
if errorlevel 1 goto :failed
exit /b 0

:python_missing
echo.
echo Python 3.10 or newer is required.
echo Install Python from https://www.python.org/downloads/
echo Enable "Add python.exe to PATH", then run launch.bat again.
pause
exit /b 1

:failed
echo.
echo Application could not start. See the error above.
pause
exit /b 1

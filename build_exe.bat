@echo off
rem Builds desktop_build\dist\Telemetria\Telemetria.exe (frontend + PyInstaller + config next to the exe).
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
set "OUT=desktop_build\dist\Telemetria"

echo [1/3] Frontend build
pushd frontend
call npm run build
if errorlevel 1 (popd & goto :fail)
popd

echo [2/3] PyInstaller
"%PY%" -m PyInstaller telemetria.spec --noconfirm --clean --distpath desktop_build\dist --workpath desktop_build\work
if errorlevel 1 goto :fail

echo [3/3] Config next to the exe
"%PY%" tools\exe_config.py "%OUT%"
if errorlevel 1 goto :fail

echo.
echo Done: %OUT%\Telemetria.exe
exit /b 0

:fail
echo.
echo Build FAILED.
pause
exit /b 1

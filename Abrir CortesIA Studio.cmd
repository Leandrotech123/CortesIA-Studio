@echo off
wsl.exe --cd "%~dp0." -- bash abrir-studio.sh
if errorlevel 1 goto error
start "" "http://localhost:8765/"
exit /b 0
:error
echo Nao foi possivel abrir o Studio. Consulte o README e logs/painel.log.
pause

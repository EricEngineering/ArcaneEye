@echo off
setlocal EnableExtensions
REM ==========================================
REM Arcane Eye clean rebuild (Windows)
REM ==========================================

REM ---- User options ----
set "LOG_ENABLED=1"                  REM 1 = log to .\logs\, 0 = no log
set "SPEC_FILE=arcaneeye.spec"
set "EXE_NAME=Arcane Eye.exe"
REM ----------------------

REM Run from the script's folder
pushd "%~dp0"

REM Prefer venv Python if present
set "PY_EXE=.venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

REM Kill any running instances to avoid locked files
echo [*] Stopping previous instances...
taskkill /IM "%EXE_NAME%" /F >NUL 2>&1

REM Kill python processes that launched arcaneeye (more precise than killing all python)
powershell -NoProfile -Command ^
 "Get-CimInstance Win32_Process | Where-Object { ($_.Name -in 'python.exe','pythonw.exe') -and ($_.CommandLine -match 'arcaneeye') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >NUL 2>&1

REM Give Windows a moment to release DLL handles
ping 127.0.0.1 -n 2 >NUL

REM Clean old build artifacts
echo [*] Cleaning build/dist...
if exist "dist\Arcane Eye"  rmdir /S /Q "dist\Arcane Eye"
if exist "build\arcaneeye"  rmdir /S /Q "build\arcaneeye"
if exist "__pycache__"    rmdir /S /Q "__pycache__"

REM Optional logging
set "LOGDIR=%CD%\logs"
if "%LOG_ENABLED%"=="1" (
  if not exist "%LOGDIR%" mkdir "%LOGDIR%" >NUL 2>&1
  for /f "tokens=1-3 delims=/.- " %%a in ("%date%") do (set "mm=%%a"&set "dd=%%b"&set "yyyy=%%c")
  set "timestr=%time: =0%"
  set "timestr=%timestr::=-%"
  set "timestr=%timestr:.=%"
  set "LOGFILE=%LOGDIR%\build-%yyyy%%mm%%dd%_%timestr%.log"
)

echo [*] Building with PyInstaller...
if "%LOG_ENABLED%"=="1" (
  "%PY_EXE%" -m PyInstaller --noconfirm --clean "%SPEC_FILE%" 1>>"%LOGFILE%" 2>&1
) else (
  "%PY_EXE%" -m PyInstaller --noconfirm --clean "%SPEC_FILE%"
)

set "RC=%ERRORLEVEL%"
echo [*] PyInstaller exit code: %RC%
if "%LOG_ENABLED%"=="1" echo [*] Log: %LOGFILE%
if not "%RC%"=="0" (
  echo [!] Build failed.
  popd & endlocal & exit /b %RC%
)

echo [✓] Build complete: dist\Arcane Eye\
popd
endlocal
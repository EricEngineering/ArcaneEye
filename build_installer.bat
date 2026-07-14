@echo off
setlocal EnableExtensions

REM ==============================
REM Arcane Eye: build EXE + installer
REM ==============================

REM ---- config ----
set "SPEC_FILE=arcaneeye.spec"
set "EXE_NAME=ArcaneEye.exe"
set "ISS_FILE=arcaneeye.iss"
REM ---- version is derived from arcaneeye\__init__.py below ----
REM ----------------

REM Run from this script's folder
pushd "%~dp0"

REM ---- Derive version from arcaneeye\__init__.py (single source of truth) ----
set "VERSION="
for /f "tokens=2 delims== " %%v in ('findstr /b /c:"__version__" "arcaneeye\__init__.py"') do set "VERSION=%%~v"
if not defined VERSION (
  echo [!] Could not read __version__ from arcaneeye\__init__.py.
  goto :end
)
echo [*] Version from __init__.py: %VERSION%

REM Prefer venv python
set "PY_EXE=.venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

echo [*] Stopping previous instances...
taskkill /IM "%EXE_NAME%" /F >NUL 2>&1
powershell -NoProfile -Command ^
 "Get-CimInstance Win32_Process | ? { ($_.Name -in 'python.exe','pythonw.exe') -and ($_.CommandLine -match 'arcaneeye') } | % { Stop-Process -Id $_.ProcessId -Force }" >NUL 2>&1
ping 127.0.0.1 -n 2 >NUL

echo [*] Cleaning old build artifacts...
if exist "dist\ArcaneEye"  rmdir /S /Q "dist\ArcaneEye"
if exist "build\arcaneeye"  rmdir /S /Q "build\arcaneeye"

echo [*] Building EXE with PyInstaller...
"%PY_EXE%" -m PyInstaller --noconfirm --clean "%SPEC_FILE%"
if errorlevel 1 goto :py_fail

echo [*] Staging installer assets (license + icon)...
if not exist "installer\assets" mkdir "installer\assets"
copy /Y "arcaneeye\resources\AGPL_V3.txt" "installer\assets\AGPL_V3.txt" >NUL
if errorlevel 1 goto :stage_fail
copy /Y "arcaneeye\resources\icon.ico" "installer\assets\installer.ico" >NUL
if errorlevel 1 goto :stage_fail

echo [*] Locating Inno Setup compiler...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC for %%I in (ISCC.exe) do set "ISCC=%%~$PATH:I"
if not defined ISCC goto :no_iscc

echo [*] Compiling installer...
"%ISCC%" /DMyAppVersion=%VERSION% "%ISS_FILE%"
if errorlevel 1 goto :iscc_fail

echo.
echo [✓] Installer built.
if exist "installer\output" (
  echo [i] Output folder: installer\output
  dir /b "installer\output"
) else (
  echo [i] Your .iss OutputDir is not 'installer\output'. Check the path configured in the .iss file.
)

goto :end

:py_fail
echo [!] PyInstaller failed.
goto :end

:stage_fail
echo [!] Could not stage installer assets. Check that these exist:
echo       arcaneeye\resources\AGPL_V3.txt
echo       arcaneeye\resources\icon.ico
goto :end

:no_iscc
echo [!] Inno Setup compiler (ISCC.exe) not found.
echo     Install it (winget install JRSoftware.InnoSetup) or adjust ISCC path in this script.
goto :end

:iscc_fail
echo [!] Inno compilation failed. Check the .iss paths (Source:, OutputDir:, LicenseFile:, SetupIconFile:).
goto :end

:end
popd
endlocal

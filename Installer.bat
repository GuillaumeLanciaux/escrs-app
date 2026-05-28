@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: Installation ESCRS IOL Calculator
:: À lancer une seule fois sur chaque poste
:: ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

echo ============================================================
echo   Installation ESCRS IOL Calculator
echo ============================================================
echo.

:: ── Vérifier Python ──────────────────────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python non trouvé
    echo Télécharger depuis : https://www.python.org/downloads/
    pause
    exit /b 1
)
echo ✓ Python détecté

:: ── Vérifier / Installer Node.js ─────────────────────────────────────────────
node --version > nul 2>&1
if not errorlevel 1 (
    echo ✓ Node.js déjà installé
    goto NODE_OK
)

echo Node.js non trouvé — téléchargement en cours...
echo.

:: Télécharger le MSI Node.js 20 LTS 64 bits
set NODE_URL=https://nodejs.org/dist/v20.19.0/node-v20.19.0-x64.msi
set NODE_MSI=%TEMP%\node_setup.msi

echo Téléchargement de Node.js 20 LTS...
powershell -Command "Invoke-WebRequest -Uri '%NODE_URL%' -OutFile '%NODE_MSI%' -UseBasicParsing"

if not exist "%NODE_MSI%" (
    echo ERREUR : Téléchargement de Node.js échoué
    echo Télécharger manuellement depuis : https://nodejs.org/
    pause
    exit /b 1
)

echo Installation de Node.js en cours ^(mode silencieux^)...
msiexec /i "%NODE_MSI%" /quiet /norestart ADDLOCAL=ALL

:: Attendre la fin de l'installation
timeout /t 10 /nobreak > nul

:: Recharger le PATH pour que node soit disponible
call RefreshEnv.cmd > nul 2>&1
:: Fallback si RefreshEnv n'est pas disponible
set "PATH=%PATH%;%ProgramFiles%\nodejs"

del "%NODE_MSI%" > nul 2>&1

:: Vérifier l'installation
node --version > nul 2>&1
if errorlevel 1 (
    echo.
    echo ⚠ Node.js installé mais pas encore dans le PATH.
    echo   Fermez cette fenêtre, redémarrez et relancez Installer.bat
    pause
    exit /b 1
)

echo ✓ Node.js installé avec succès

:NODE_OK

:: ── Lancer le script d'installation Python ────────────────────────────────────
echo.
echo Lancement de l'installation des dépendances...
echo.
python setup.py

if errorlevel 1 (
    echo.
    echo ERREUR : L'installation a échoué — voir les messages ci-dessus
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installation terminée !
echo   Vous pouvez maintenant lancer "Lancer ESCRS.bat"
echo ============================================================
echo.
pause
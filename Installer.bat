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

:: Vérifier Python
python --version > nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python non trouvé
    echo Télécharger depuis : https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Vérifier Node.js
node --version > nul 2>&1
if errorlevel 1 (
    echo ERREUR : Node.js non trouvé
    echo Télécharger depuis : https://nodejs.org/
    pause
    exit /b 1
)

:: Lancer le script d'installation Python
echo Lancement de l'installation...
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

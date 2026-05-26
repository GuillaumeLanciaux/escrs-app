@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: Lancer ESCRS IOL Calculator
:: Double-cliquer pour démarrer l'application
:: ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

:: Vérifier que node_modules existe (premier lancement)
if not exist "node_modules\" (
    echo Installation des dépendances en cours...
    call npm install
    if errorlevel 1 (
        echo ERREUR : npm install a échoué
        pause
        exit /b 1
    )
)

:: Vérifier que dist/main.js existe (compilation nécessaire)
if not exist "dist\main.js" (
    echo Compilation en cours...
    call npm run build
    if errorlevel 1 (
        echo ERREUR : La compilation a échoué
        pause
        exit /b 1
    )
)

:: Lancer l'application
call npx electron .

exit /b 0

"""
setup.py — Installation automatique des dépendances ESCRS IOL Calculator
=========================================================================
À lancer une seule fois sur chaque poste :
    python setup.py

Ce script :
  1. Vérifie la version de Python
  2. Installe les dépendances Python (pip)
  3. Télécharge et installe Tesseract 5.x dans vendor/tesseract/
  4. Vérifie l'installation de Node.js
  5. Lance npm install
  6. Compile le TypeScript
"""

import sys
import os
import shutil
import subprocess
import urllib.request
import zipfile
import tempfile
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_DIR  = Path(__file__).parent
VENDOR_DIR   = PROJECT_DIR / "vendor" / "tesseract"
PYTHON_DIR   = PROJECT_DIR / "python"

# URL du zip portable Tesseract 5 (pas d'installeur, juste les fichiers)
# Source : https://github.com/UB-Mannheim/tesseract/wiki
TESSERACT_URL = (
    "https://github.com/UB-Mannheim/tesseract/releases/download/"
    "v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
)

# Tessdata minimal nécessaire
TESSDATA_URLS = {
    "eng.traineddata": "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata",
    "fra.traineddata": "https://github.com/tesseract-ocr/tessdata/raw/main/fra.traineddata",
}

REQUIREMENTS = PROJECT_DIR / "requirements.txt"


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def titre(msg: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def erreur(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def run(cmd: list, cwd: Path = None) -> bool:
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd or PROJECT_DIR),
            capture_output=True, text=True
        )
        if result.returncode != 0:
            erreur(f"Commande échouée : {' '.join(cmd)}")
            print(result.stderr, file=sys.stderr)
            return False
        return True
    except FileNotFoundError:
        erreur(f"Commande introuvable : {cmd[0]}")
        return False


def telecharger(url: str, dest: Path, label: str) -> bool:
    print(f"  ⬇ Téléchargement {label}…", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print("OK")
        return True
    except Exception as e:
        print(f"ÉCHEC ({e})")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Étapes d'installation
# ─────────────────────────────────────────────────────────────────────────────

def verifier_python() -> bool:
    titre("1. Vérification Python")
    version = sys.version_info
    print(f"  Python {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        erreur("Python 3.11+ requis")
        return False
    ok("Version Python compatible")
    return True


def installer_pip() -> bool:
    titre("2. Installation des dépendances Python")
    if not REQUIREMENTS.exists():
        erreur(f"requirements.txt introuvable : {REQUIREMENTS}")
        return False

    print("  pip install -r requirements.txt…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        capture_output=False  # afficher la progression
    )
    if result.returncode != 0:
        erreur("Échec pip install")
        return False

    ok("Dépendances Python installées")
    return True


def installer_tesseract() -> bool:
    titre("3. Installation Tesseract OCR")

    # Vérifier si déjà présent
    tesseract_exe = VENDOR_DIR / "tesseract.exe"
    if tesseract_exe.exists():
        try:
            result = subprocess.run(
                [str(tesseract_exe), "--version"],
                capture_output=True, text=True
            )
            version_line = (result.stdout or result.stderr).split('\n')[0]
            ok(f"Tesseract déjà installé : {version_line}")
            return True
        except Exception:
            pass

    # Vérifier si Tesseract 5+ est déjà installé sur le système
    for chemin in [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]:
        if chemin.exists():
            result = subprocess.run(
                [str(chemin), "--version"],
                capture_output=True, text=True
            )
            output = result.stdout or result.stderr
            if "5." in output or "4." in output:
                # Copier dans vendor/
                print(f"  Tesseract trouvé : {chemin.parent}")
                print(f"  Copie vers vendor/tesseract/…")
                VENDOR_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    str(chemin.parent),
                    str(VENDOR_DIR),
                    dirs_exist_ok=True
                )
                ok("Tesseract copié dans vendor/")
                return True

    # Télécharger l'installeur
    print("  Tesseract non trouvé — téléchargement en cours…")
    print(f"  URL : {TESSERACT_URL}")

    with tempfile.TemporaryDirectory() as tmp:
        installer = Path(tmp) / "tesseract_setup.exe"

        if not telecharger(TESSERACT_URL, installer, "Tesseract 5.3"):
            erreur(
                "Impossible de télécharger Tesseract.\n"
                "  Téléchargez manuellement depuis :\n"
                "  https://github.com/UB-Mannheim/tesseract/wiki\n"
                "  Et copiez le dossier dans : vendor/tesseract/"
            )
            return False

        # Lancer l'installeur en silencieux
        print("  Installation Tesseract (mode silencieux)…")
        install_dir = PROJECT_DIR / "vendor" / "tesseract"
        install_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run([
            str(installer),
            "/S",                          # silencieux
            f"/D={install_dir}",           # dossier destination
        ], capture_output=True)

        if result.returncode != 0:
            erreur("Échec installation Tesseract silencieuse")
            erreur("Lancer l'installeur manuellement et installer dans :")
            erreur(f"  {install_dir}")
            return False

    # Télécharger les fichiers tessdata
    tessdata_dir = VENDOR_DIR / "tessdata"
    tessdata_dir.mkdir(parents=True, exist_ok=True)

    for filename, url in TESSDATA_URLS.items():
        dest = tessdata_dir / filename
        if dest.exists():
            ok(f"  {filename} déjà présent")
            continue
        telecharger(url, dest, filename)

    ok("Tesseract installé dans vendor/tesseract/")
    return True


def verifier_nodejs() -> bool:
    titre("4. Vérification Node.js")
    result = subprocess.run(
        ["node", "--version"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        erreur("Node.js non trouvé")
        erreur("Télécharger depuis : https://nodejs.org/")
        return False

    version = result.stdout.strip()
    print(f"  Node.js {version}")

    # Vérifier version >= 20
    major = int(version.lstrip('v').split('.')[0])
    if major < 20:
        erreur(f"Node.js 20+ requis (trouvé : {version})")
        return False

    ok("Version Node.js compatible")
    return True


def installer_npm() -> bool:
    titre("5. Installation des dépendances Node.js")
    print("  npm install…")
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(PROJECT_DIR),
        capture_output=False
    )
    if result.returncode != 0:
        erreur("Échec npm install")
        return False
    ok("Dépendances Node.js installées")
    return True


def compiler_typescript() -> bool:
    titre("6. Compilation TypeScript")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(PROJECT_DIR),
        capture_output=False
    )
    if result.returncode != 0:
        erreur("Échec compilation TypeScript")
        return False
    ok("TypeScript compilé")
    return True

def _check_pywin32() -> bool:
    try:
        import win32com.client
        return True
    except ImportError:
        return False

def verifier_installation_finale() -> None:
    titre("Vérification finale")

    checks = {
        "Python 3.11+"         : sys.version_info >= (3, 11),
        "requirements.txt"     : REQUIREMENTS.exists(),
        "Tesseract vendor/"    : (VENDOR_DIR / "tesseract.exe").exists(),
        "tessdata/eng"         : (VENDOR_DIR / "tessdata" / "eng.traineddata").exists(),
        "node_modules/"        : (PROJECT_DIR / "node_modules").exists(),
        "dist/main.js"         : (PROJECT_DIR / "dist" / "main.js").exists(),
        "escrs_inject.js"      : (PYTHON_DIR / "escrs_inject.js").exists(),
        "escrs_connector.py"   : (PYTHON_DIR / "escrs_connector.py").exists(),
        "pywin32"              : _check_pywin32(),
    }

    tous_ok = True
    for label, status in checks.items():
        symbole = "✓" if status else "✗"
        print(f"  {symbole} {label}")
        if not status:
            tous_ok = False

    if tous_ok:
        print("\n  ✅ Installation complète — lancer avec : npm start")
    else:
        print("\n  ⚠ Certains éléments manquent — voir les erreurs ci-dessus")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  ESCRS IOL Calculator — Installation")
    print("=" * 60)

    etapes = [
        verifier_python,
        installer_pip,
        installer_tesseract,
        verifier_nodejs,
        installer_npm,
        compiler_typescript,
    ]

    for etape in etapes:
        if not etape():
            print("\n  ⛔ Installation interrompue — corriger l'erreur et relancer setup.py")
            sys.exit(1)

    verifier_installation_finale()

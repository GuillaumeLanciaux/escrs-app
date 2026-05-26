"""
Extraction automatique de l'épaisseur cornéenne centrale
depuis un rapport Pachymétrie Optovue

Formats supportés :
  - OU Report  (deux yeux sur la même image)
  - Single eye (un seul oeil, OD ou OS)

Dépendances :
    Windows : installer Tesseract via https://github.com/UB-Mannheim/tesseract/wiki
              pip install pytesseract opencv-python-headless
    Linux   : sudo apt install tesseract-ocr
              pip install pytesseract opencv-python-headless

Utilisation :
    python pachymetry_ocr.py image.jpg
    python pachymetry_ocr.py image.jpg --debug   # sauvegarde les zones cropées
"""

import cv2
import pytesseract
import numpy as np
import json
import sys
import shutil
from pathlib import Path
from collections import Counter


# ─────────────────────────────────────────────────────────────────────────────
# Détection automatique de Tesseract
# ─────────────────────────────────────────────────────────────────────────────

def _find_tesseract() -> str:
    chemins = [
        # Tesseract embarqué dans le projet — TOUJOURS prioritaire
        # pour éviter le conflit avec Tesseract 3.02 d'AlmaPro
        Path(__file__).parent.parent / "vendor" / "tesseract.exe",
        Path(__file__).parent / "tesseract.exe",
        # Chemin manuel projet
        Path(r"C:\Stage\database\test\tesseract\tesseract.exe"),
        # Installation standard Windows (v4/v5)
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        # AlmaPro en DERNIER — v3.02 incompatible
        Path(r"C:\almapro\tesseract\tesseract.exe"),
        Path(r"C:\AlmaPro\tesseract\tesseract.exe"),
    ]
    # ...

    for chemin in chemins:
        if chemin.exists():
            print(f"  ✓ Tesseract : {chemin}", file=sys.stderr)
            return str(chemin)

    # Dernier recours : PATH système (peut être celui d'AlmaPro)
    system = shutil.which("tesseract")
    if system:
        print(f"  ✓ Tesseract (PATH) : {system}", file=sys.stderr)
        return system

    raise FileNotFoundError(
        "Tesseract introuvable. Vérifier l'installation.\n"
        "Chemins vérifiés :\n" + "\n".join(f"  - {c}" for c in chemins)
    )


pytesseract.pytesseract.tesseract_cmd = _find_tesseract()

# ─────────────────────────────────────────────────────────────────────────────
# Zones calibrées (ratios x1,y1,x2,y2 relatifs à la taille image)
# ─────────────────────────────────────────────────────────────────────────────

ZONES = {
    "ou_report": {
        "OD": (0.157, 0.252, 0.232, 0.330),
        "OS": (0.752, 0.272, 0.852, 0.330),
    },
    "single_OD": {
        "OD": (0.376, 0.612, 0.464, 0.709),
    },
    "single_OS": {
        "OS": (0.376, 0.612, 0.464, 0.709),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Détection du type de rapport
# ─────────────────────────────────────────────────────────────────────────────

def detecter_type_rapport(img):
    """
    Lit le bandeau supérieur de l'image pour identifier :
      - OU Report (deux yeux)
      - Single eye OD
      - Single eye OS
    Retourne : "ou_report", "single_OD" ou "single_OS"
    """
    top = img[0:80, :]
    gray = cv2.cvtColor(top, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(big, 150, 255, cv2.THRESH_BINARY)
    texte = pytesseract.image_to_string(
        binary, config="--psm 11"
    ).lower()

    ou_report = "ou report" in texte or ("left" in texte and "right" in texte)
    if ou_report:
        return "ou_report"
    if "right" in texte or "od" in texte:
        return "single_OD"
    return "single_OS"


# ─────────────────────────────────────────────────────────────────────────────
# Extraction OCR d'une zone
# ─────────────────────────────────────────────────────────────────────────────

def ocr_zone_centrale(img, zone_ratio, label, debug=False):
    """
    Extrait la valeur pachymétrique centrale d'une zone.
    Vote majoritaire sur plusieurs combinaisons seuil / PSM / agrandissement.
    """
    h, w = img.shape[:2]
    x1 = int(zone_ratio[0] * w)
    y1 = int(zone_ratio[1] * h)
    x2 = int(zone_ratio[2] * w)
    y2 = int(zone_ratio[3] * h)

    zone = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)

    if debug:
        cv2.imwrite(f"debug_zone_{label}.png", zone)
        print(f"  [{label}] Zone pixels: ({x1},{y1}) -> ({x2},{y2})")

    votes = []

    for scale in [3, 4]:
        big = cv2.resize(gray, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        for thresh in [110, 130, 150, 170]:
            _, binary = cv2.threshold(big, thresh, 255, cv2.THRESH_BINARY)
            for img_bin in [binary, cv2.bitwise_not(binary)]:
                for psm in [6, 11, 13]:
                    config = (f"--psm {psm} "
                              f"-c tessedit_char_whitelist=0123456789")
                    data = pytesseract.image_to_data(
                        img_bin, config=config,
                        output_type=pytesseract.Output.DICT
                    )
                    for i, t in enumerate(data["text"]):
                        t = t.strip()
                        if (t and t.isdigit()
                                and len(t) == 3
                                and int(data["conf"][i]) > 40
                                and 400 <= int(t) <= 800):
                            votes.append(t)

    if not votes:
        return {"valeur_µm": None, "confiance_%": 0, "votes": {}}

    comptage = Counter(votes)
    meilleure_valeur = comptage.most_common(1)[0][0]
    confiance = round(comptage[meilleure_valeur] / len(votes) * 100)

    return {
        "valeur_µm": int(meilleure_valeur),
        "confiance_%": confiance,
        "votes": dict(comptage)
    }


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ─────────────────────────────────────────────────────────────────────────────

def extraire_pachymetrie(chemin_image, debug=False):
    img = cv2.imread(chemin_image)
    if img is None:
        raise FileNotFoundError(f"Image introuvable : {chemin_image}")

    type_rapport = detecter_type_rapport(img)
    zones = ZONES[type_rapport]

    if debug:
        print(f"Type de rapport detecte : {type_rapport}")
        print(f"Zones utilisees : {zones}")

    resultats = {}
    for oeil, zone_ratio in zones.items():
        resultats[oeil] = ocr_zone_centrale(img, zone_ratio, oeil, debug)

    # Asymétrie si les deux yeux sont présents
    asymetrie = None
    if "OD" in resultats and "OS" in resultats:
        od_val = resultats["OD"]["valeur_µm"]
        os_val = resultats["OS"]["valeur_µm"]
        if od_val and os_val:
            asymetrie = abs(od_val - os_val)

    # Norme indicative (population générale)
    norme = {}
    for oeil, res in resultats.items():
        val = res["valeur_µm"]
        norme[f"{oeil}_dans_norme"] = (500 <= val <= 570) if val else None

    return {
        "fichier": chemin_image,
        "type_rapport": type_rapport,
        "pachymetrie_centrale": resultats,
        "asymetrie_µm": asymetrie,
        "norme_indicative_500_570µm": norme,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug = "--debug" in sys.argv
    chemin = next(
        (a for a in sys.argv[1:] if not a.startswith("--")),
        "pachymetry.jpg"
    )
    resultat = extraire_pachymetrie(chemin, debug)
    print(json.dumps(resultat, indent=2, ensure_ascii=False))
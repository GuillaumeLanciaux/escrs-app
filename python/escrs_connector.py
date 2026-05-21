"""
escrs_connector.py
==================
Connecte extraction_biometrie.py + pachymetry_ocr.py → script JS ESCRS

Pipeline complet :
  1. Récupère la biométrie depuis les PDFs Zeiss IOLMaster (extraction_biometrie.py)
  2. Récupère la CCT depuis les images Optovue (pachymetry_ocr.py)
  3. Récupère le sexe depuis PUBLIC.MDB (champ SEXE ou fallback SS)
  4. Génère le script JS d'injection pour le calculateur ESCRS

Utilisation :
    from escrs_connector import preparer_patient_escrs

    result = preparer_patient_escrs(
        patient_code = "66844742",
        surgeon      = "Dr Dupont",
        manufacturer = "Alcon",
        iol          = "AcrySof SN60WF",
        mode         = "normal",   # 'normal' | 'toric' | 'postlasik'
    )

    # result["script_js"]     → script JS prêt à injecter dans le WebView
    # result["patient_escrs"] → données formatées (debug / log)
    # result["session"]       → session biométrique brute

CLI :
    python escrs_connector.py 66844742 --surgeon "Dr Dupont" \
           --manufacturer Alcon --iol "AcrySof SN60WF"

    python escrs_connector.py --get-active-patient
    # → {"code": "66844742", "nom": "DUPONT", "prenom": "Jean"} ou {"code": null}
"""

import re
import json
import pyodbc
import sys
import io
from datetime import date, datetime
from pathlib import Path

# Import des modules locaux
from extraction_biometrie import charger_biometrie, _db_connect, find_patient_folder
from pachymetry_ocr import extraire_pachymetrie


# Forcer UTF-8 sur stdout et stderr (Windows cp1252 ne supporte pas les emojis)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# CONFIGURATION
FICHIER_MDB     = Path(r"C:\Stage\database\baseSQL\PUBLIC.MDB")
DEST_PHOTOS     = Path(r"c:\Stage\database\donnés_pdf")
ESCRS_INJECT_JS = Path(__file__).parent / "escrs_inject.js"

# Champs Access du formulaire patient (identiques à suivi_myopie.py)
_ACCESS_FIELD_CODE   = "Code patient"
_ACCESS_FIELD_NOM    = "NOM"
_ACCESS_FIELD_PRENOM = "Prénom"


# 0. DÉTECTION AUTOMATIQUE DU PATIENT ACTIF DANS ACCESS (COM Interop)

def _log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr, flush=True)


try:
    import win32com.client as _win32
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False
    _log("pywin32 non disponible — détection automatique désactivée.")


def get_active_patient() -> dict | None:
    """
    Lit le patient actuellement ouvert dans Microsoft Access via COM Interop.

    Retourne :
        {"code": str, "nom": str, "prenom": str}  si un patient est ouvert
        None  si Access est fermé, aucun formulaire actif, ou pywin32 absent.

    Prérequis :
        pip install pywin32
        Access doit être ouvert avec le formulaire patient visible.
    """
    if not _WIN32_AVAILABLE:
        return None
    try:
        access = _win32.GetActiveObject("Access.Application")
        form   = access.Screen.ActiveForm
        if form is None:
            return None

        target = {_ACCESS_FIELD_CODE, _ACCESS_FIELD_NOM, _ACCESS_FIELD_PRENOM}
        data: dict = {}

        for i in range(form.Controls.Count):
            ctrl = form.Controls(i)
            try:
                if str(ctrl.Name) in target:
                    data[ctrl.Name] = ctrl.Value
            except Exception:
                pass

        if not target.issubset(data.keys()):
            _log("COM: formulaire ouvert mais champs requis absents.")
            return None

        return {
            "code":   str(data[_ACCESS_FIELD_CODE]),
            "nom":    str(data[_ACCESS_FIELD_NOM]),
            "prenom": str(data[_ACCESS_FIELD_PRENOM]),
        }

    except Exception as e:
        _log(f"COM: aucun patient actif ({e})")
        return None


# 1. SEXE DEPUIS MDB + FALLBACK SS

def _sexe_depuis_ss(ss: str) -> str | None:
    """Extrait le sexe depuis le premier chiffre du numéro SS."""
    ss = re.sub(r'[\s.\-]', '', str(ss or '')).strip()
    if ss and ss[0] == '1': return 'Male'
    if ss and ss[0] == '2': return 'Female'
    return None


def _get_patient_info(patient_code: str, conn: pyodbc.Connection) -> dict:
    """Récupère sexe depuis PUBLIC.MDB — champ SEXE prioritaire, SS en fallback."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SEXE, SS FROM [Patients] WHERE [code patient] = ?",
            (int(patient_code),)
        )
        row = cursor.fetchone()
        if not row:
            return {"gender": "Male"}

        sexe_raw = str(row[0] or '').strip()
        ss_raw   = str(row[1] or '').strip()

        if sexe_raw in ('1', '1.0'):
            gender = 'Male'
        elif sexe_raw in ('2', '2.0'):
            gender = 'Female'
        else:
            gender = _sexe_depuis_ss(ss_raw) or 'Male'

        return {"gender": gender}

    except Exception as e:
        _log(f"  ⚠ Erreur lecture info patient : {e}")
        return {"gender": "Male"}


# 2. CCT DEPUIS PACHYMÉTRIE OPTOVUE

def _get_cct(patient_code: str, dossier: Path, conn: pyodbc.Connection) -> dict:
    """
    Récupère la CCT OD et OS depuis les images pachymétrie Optovue.
    Cherche via PUBLIC.MDB les images référencées pour ce patient,
    prend la plus récente, et utilise pachymetry_ocr pour l'extraction.
    Le type de rapport (OU/OD/OS) est détecté automatiquement.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT [Photo externe] FROM Documents "
            "WHERE [code patient] = ? "
            "AND [Photo externe] LIKE '%Pachymetry%'",
            (int(patient_code),)
        )
        rows = cursor.fetchall()

        if not rows:
            _log("  ⚠ Aucune image pachymétrie en base")
            return {"OD": None, "OS": None}

        # Résoudre les chemins physiques
        images = []
        for row in rows:
            nom  = Path(str(row[0])).name
            path = dossier / nom
            if path.exists():
                images.append(path)

        if not images:
            _log("  ⚠ Images pachymétrie introuvables sur disque")
            return {"OD": None, "OS": None}

        # Trier par date extraite du nom (format YYYY-MM-DD_HH-MM-SS)
        def _date_nom(p: Path) -> str:
            m = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', p.name)
            return m.group(1) if m else ''

        images.sort(key=_date_nom)
        derniere = images[-1]
        _log(f"  ✓ Pachymétrie : {derniere.name}")

        # Extraction OCR — detecter_type_rapport() gère OU/OD/OS automatiquement
        resultat = extraire_pachymetrie(str(derniere))
        pachy    = resultat.get("pachymetrie_centrale", {})

        od_val = pachy.get("OD", {}).get("valeur_µm")
        os_val = pachy.get("OS", {}).get("valeur_µm")
        _log(f"  ✓ CCT OD={od_val}µm  OS={os_val}µm")

        return {"OD": od_val, "OS": os_val}

    except Exception as e:
        _log(f"  ⚠ Erreur pachymétrie : {e}")
        return {"OD": None, "OS": None}


# 3. CALCUL ÂGE

def _calculer_age(date_naissance) -> int | None:
    if not date_naissance:
        return None
    try:
        if hasattr(date_naissance, 'date'):
            dob = date_naissance.date()
        elif isinstance(date_naissance, str):
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    dob = datetime.strptime(date_naissance, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                return None
        else:
            dob = date_naissance
        return (date.today() - dob).days // 365
    except Exception:
        return None


# 4. CONVERSION SESSION → OBJET ESCRS

# Formules par défaut selon le mode
FORMULES_PAR_MODE = {
    'normal':    ['Barrett', 'Kane', 'Hill-RBF', 'Pearl DGS'],
    'toric':     ['Barrett', 'Kane', 'EVO', 'Hill-RBF'],
    'postlasik': ['Barrett True K', 'EVO', 'Hoffer®QST'],
}


def _session_to_escrs(
    session:       dict,
    patient_info:  dict,
    cct:           dict,
    surgeon:       str,
    manufacturer:  str,
    iol:           str,
    mode:          str   = 'normal',
    formulas:      list  = None,
    index:         str   = '1.3375',
    target_od:     float = 0.0,
    target_og:     float = 0.0,
    # Champs toric uniquement
    k1axis_od:     float = None,
    k2axis_od:     float = None,
    incision_od:   float = None,
    sia_od:        float = None,
    k1axis_og:     float = None,
    k2axis_og:     float = None,
    incision_og:   float = None,
    sia_og:        float = None,
    # Post LASIK uniquement
    post_lasik_type: str = 'Myopic',
) -> dict:

    patient = session.get("patient", {})
    nom     = (patient.get("nom")    or "").strip().upper()
    prenom  = (patient.get("prenom") or "").strip().capitalize()
    initials = f"{nom[:3]}{prenom[:2]}".upper() if nom and prenom else nom[:5].upper()
    dob      = patient.get("date_naissance")
    age      = _calculer_age(dob)

    OD = session.get("OD", {})
    OS = session.get("OS", {})

    def _oeil(data, cct_val, k1axis=None, k2axis=None, incision=None, sia=None):
        oeil = {
            "al":               data.get("AL_mm"),
            "acd":              data.get("ACD_mm"),
            "lt":               data.get("LT_mm"),
            "cct":              cct_val,
            "wtw":              data.get("WTW_mm"),
            "k1":               data.get("K1_D"),
            "k2":               data.get("K2_D"),
            "manufacturer":     manufacturer,
            "iol":              iol,
        }
        # Champs toric
        if mode == 'toric':
            oeil.update({
                "k1axis":   k1axis or data.get("K1_axis"),
                "k2axis":   k2axis or data.get("K2_axis"),
                "incision": incision or 135.0,
                "sia":      sia or 0.3,
            })
        return oeil

    result = {
        "mode":          mode,
        "surgeon":       surgeon,
        "initials":      initials,
        "gender":        patient_info.get('gender', 'Male'),
        "age":           age,
        "index":         index,
        "formulas":      formulas or FORMULES_PAR_MODE.get(mode, []),
        "rightEye":      _oeil(OD, cct.get("OD"), k1axis_od, k2axis_od, incision_od, sia_od),
        "leftEye":       _oeil(OS, cct.get("OS"), k1axis_og, k2axis_og, incision_og, sia_og),
    }

    result["rightEye"]["targetRefraction"] = target_od
    result["leftEye"]["targetRefraction"]  = target_og

    if mode == 'postlasik':
        result["postLasikType"] = post_lasik_type

    return result


# 5. GÉNÉRATION DU SCRIPT JS

def _generer_script_js(patient_escrs: dict) -> str:
    if not ESCRS_INJECT_JS.exists():
        raise FileNotFoundError(f"Template JS introuvable : {ESCRS_INJECT_JS}")

    data_json = json.dumps(patient_escrs, ensure_ascii=False, indent=2)
    script    = ESCRS_INJECT_JS.read_text(encoding='utf-8')

    # Remplace le placeholder par les données patient
    script = script.replace('{PATIENT_DATA}', data_json)
    return script


# 6. POINT D'ENTRÉE PRINCIPAL

def preparer_patient_escrs(
    patient_code:    str,
    surgeon:         str,
    manufacturer:    str,
    iol:             str,
    mode:            str   = 'normal',
    formulas:        list  = None,
    index:           str   = '1.3375',
    target_od:       float = 0.0,
    target_og:       float = 0.0,
    session_index:   int   = -1,
    # Toric
    k1axis_od:       float = None,
    k2axis_od:       float = None,
    incision_od:     float = 135.0,
    sia_od:          float = 0.3,
    k1axis_og:       float = None,
    k2axis_og:       float = None,
    incision_og:     float = 135.0,
    sia_og:          float = 0.3,
    # Post LASIK
    post_lasik_type: str   = 'Myopic',
) -> dict:
    """
    Charge toutes les données d'un patient et retourne l'objet ESCRS
    avec le script JS prêt à injecter dans le WebView.
    """
    _log(f"▶ Préparation patient {patient_code}…")

    # Connexion unique partagée
    conn    = _db_connect()
    dossier = find_patient_folder(patient_code, conn)

    if not dossier:
        conn.close()
        raise ValueError(f"Dossier patient introuvable : {patient_code}")

    patient_info = _get_patient_info(patient_code, conn)
    cct          = _get_cct(patient_code, dossier, conn)
    conn.close()

    # Biométrie
    sessions = charger_biometrie(patient_code)
    if not sessions:
        raise ValueError(f"Aucune session biométrique pour {patient_code}")

    session = sessions[session_index]

    # Conversion
    patient_escrs = _session_to_escrs(
        session, patient_info, cct,
        surgeon, manufacturer, iol,
        mode, formulas, index, target_od, target_og,
        k1axis_od, k2axis_od, incision_od, sia_od,
        k1axis_og, k2axis_og, incision_og, sia_og,
        post_lasik_type,
    )

    script_js = _generer_script_js(patient_escrs)

    _log(f"  ✓ {patient_escrs['initials']} | "
         f"{patient_escrs['gender']} | "
         f"{patient_escrs['age']} ans | "
         f"CCT OD={cct['OD']}µm OS={cct['OS']}µm")

    return {
        "patient_escrs": patient_escrs,
        "script_js":     script_js,
        "session":       session,
    }


# CLI

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("patient_code",       nargs="?", help="Code patient")
    parser.add_argument("--params-file",      help="Fichier JSON de paramètres (mode Electron)")
    parser.add_argument("--get-active-patient", action="store_true",
                        help="Lit le patient actif dans Access et retourne son code en JSON")
    parser.add_argument("--surgeon",          default="Dr Dupont")
    parser.add_argument("--manufacturer",     default="Alcon")
    parser.add_argument("--iol",              default="AcrySof SN60WF")
    parser.add_argument("--mode",             default="normal",
                        choices=["normal", "toric", "postlasik"])
    parser.add_argument("--json",             action="store_true")
    parser.add_argument("--js",               action="store_true")
    args = parser.parse_args()

    # Mode détection automatique du patient actif
    # Appelé par Electron via IPC "get-active-patient"
    if args.get_active_patient:
        patient = get_active_patient()
        if patient:
            print(json.dumps(patient, ensure_ascii=False))
        else:
            print(json.dumps({"code": None}))
        sys.exit(0)

    # Mode Electron : lire les paramètres depuis un fichier JSON
    if args.params_file:
        with open(args.params_file, encoding='utf-8') as f:
            p = json.load(f)

        result = preparer_patient_escrs(
            patient_code    = str(p["patient_code"]),
            surgeon         = p.get("surgeon",         "Dr Dupont"),
            manufacturer    = p.get("manufacturer",    "Alcon"),
            iol             = p.get("iol",             "AcrySof SN60WF"),
            mode            = p.get("mode",            "normal"),
            index           = p.get("index",           "1.3375"),
            target_od       = float(p.get("target_od", 0.0)),
            target_og       = float(p.get("target_og", 0.0)),
            k1axis_od       = p.get("k1axis_od"),
            k2axis_od       = p.get("k2axis_od"),
            incision_od     = p.get("incision_od"),
            sia_od          = p.get("sia_od"),
            k1axis_og       = p.get("k1axis_og"),
            k2axis_og       = p.get("k2axis_og"),
            incision_og     = p.get("incision_og"),
            sia_og          = p.get("sia_og"),
            post_lasik_type = p.get("post_lasik_type", "Myopic"),
        )

        # Electron lit stdout comme JSON — rien d'autre ne doit être sur stdout
        print(json.dumps({
            "script_js":     result["script_js"],
            "patient_escrs": result["patient_escrs"],
        }, ensure_ascii=False))
        sys.exit(0)

    # Mode CLI classique
    if not args.patient_code:
        parser.error("patient_code requis en mode CLI")

    result = preparer_patient_escrs(
        patient_code = args.patient_code,
        surgeon      = args.surgeon,
        manufacturer = args.manufacturer,
        iol          = args.iol,
        mode         = args.mode,
    )

    if args.json:
        print(json.dumps(result["patient_escrs"], indent=2, ensure_ascii=False))
    elif args.js:
        print(result["script_js"])
    else:
        _log(f"\n✓ Patient prêt — {result['patient_escrs']['initials']}")
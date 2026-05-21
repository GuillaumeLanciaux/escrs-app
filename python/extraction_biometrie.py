"""
Extraction automatique des données biométriques
depuis les PDFs Zeiss IOLMaster (IOLMultiformula et MMT-Full)
=============================================================

Architecture identique à suivi_al.py :
  - Connexion à PUBLIC.MDB via pyodbc
  - Résolution du dossier patient via find_patient_folder()
  - Lecture du texte sélectionnable via pdfplumber

Pour un patient donné, le script :
  1. Interroge la table Documents pour trouver tous ses IOLMultiformula et MMT-Full
  2. Résout les chemins physiques sur le disque
  3. Extrait les données biométriques de chaque PDF
  4. Retourne un historique trié par date

Dépendances :
    pip install pdfplumber pyodbc pandas
    Driver requis : Microsoft Access Database Engine 2016 (64 bits)

Utilisation
-----------
    from extraction_biometrie import charger_biometrie, fusionner_session

    # Tous les PDFs d'un patient
    sessions = charger_biometrie("66844742")

    # Accès à une session fusionnée (IOL + MMT de la même date)
    for s in sessions:
        print(s["patient"]["nom"], s["OD"]["AL_mm"], s["OD"]["WTW_mm"])

CLI
---
    python extraction_biometrie.py 66844742
    python extraction_biometrie.py 66844742 --json
"""

import logging
import re
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber
import pyodbc

# ═════════════════════════════════════════════════════════════════════════════
# ▶▶  CONFIGURATION  
# ═════════════════════════════════════════════════════════════════════════════
FICHIER_MDB = Path(r"C:\Stage\database\baseSQL\PUBLIC.MDB")
DEST_PHOTOS = Path(r"c:\Stage\database\donnés_pdf")
# ═════════════════════════════════════════════════════════════════════════════

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONNEXION MDB  
# ─────────────────────────────────────────────────────────────────────────────

def _db_connect() -> pyodbc.Connection:
    if not FICHIER_MDB.exists():
        raise FileNotFoundError(f"PUBLIC.MDB introuvable : {FICHIER_MDB}")
    return pyodbc.connect(
        f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={FICHIER_MDB};"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. RÉSOLUTION DU DOSSIER PATIENT  
# ─────────────────────────────────────────────────────────────────────────────

def find_patient_folder(patient_code: str, conn: pyodbc.Connection) -> Path | None:
    """Résout le dossier physique d'un patient sur le disque."""
    try:
        cursor = conn.cursor()
        # Priorité aux fichiers MMT
        cursor.execute(
            "SELECT TOP 1 [Photo externe] FROM Documents "
            "WHERE [code patient] = ? "
            "AND [Photo externe] IS NOT NULL "
            "AND [Photo externe] LIKE '%MMT%'",
            (int(patient_code),)
        )
        row = cursor.fetchone()

        # Fallback : n'importe quel document
        if not row:
            cursor.execute(
                "SELECT TOP 1 [Photo externe] FROM Documents "
                "WHERE [code patient] = ? AND [Photo externe] IS NOT NULL",
                (int(patient_code),)
            )
            row = cursor.fetchone()

        if not row or not row[0]:
            log.warning(f"Aucun document trouvé pour le patient {patient_code}")
            return None

        chemin  = Path(row[0].strip())
        dossier = DEST_PHOTOS / Path(*chemin.parts[1:-1])  # exclure racine et fichier

        if not dossier.is_dir():
            log.warning(f"Dossier absent sur le disque : {dossier}")
            return None

        return dossier

    except Exception as e:
        log.error(f"Erreur résolution dossier patient {patient_code} : {e}")
        return None


def code_patient_depuis_chemin(chemin: str) -> str | None:
    """Extrait le code patient depuis le chemin stocké en base (repris de suivi_al.py)."""
    m = re.search(r"\\(\d{7,})[^\\]*\\[^\\]+\.pdf$", chemin)
    return m.group(1) if m else None


def date_depuis_nom_fichier(nom: str) -> pd.Timestamp | None:
    """MMTFull_20260415_052633_1192.pdf → Timestamp('2026-04-15') (repris de suivi_al.py)."""
    m = re.search(r"_(\d{8})_", nom)
    if m:
        try:
            return pd.Timestamp(datetime.strptime(m.group(1), "%Y%m%d"))
        except ValueError:
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. PATTERNS REGEX
# ─────────────────────────────────────────────────────────────────────────────

# Patient
_RE_NOM      = re.compile(r"Nom\s*:\s*([^\r\n]*)")
_RE_PRENOM   = re.compile(r"Pr[ée]nom\s*:\s*([^\r\n]*)")
_RE_ID       = re.compile(r"(?<!\w)ID\s*:\s*(\d+)")
_RE_DOB      = re.compile(r"Date de naissance\s*:\s*([\d/]+)")

# Session
_RE_DOM      = re.compile(r"Date de mesure\s*:\s*([\d/]+)")
_RE_CIBLE    = re.compile(r"R[ée]fraction cible\s*:\s*([-\d.]+)\s*D")
_RE_LENTILLE = re.compile(r"Lentille\s*:\s*(.+)")
_RE_INSTR    = re.compile(r"(Carl Zeiss IOLMaster[^\n]+)")

# Biométrie IOLMultiformula
_RE_AL       = re.compile(r"\bAL\s*:\s*([\d.]+)\s*mm")
_RE_K1       = re.compile(r"\bK1\s*:\s*([\d.]+)\s*D\s*/\s*[\d.]+\s*mm\s*x\s*(\d+)°")
_RE_K2       = re.compile(r"\bK2\s*:\s*([\d.]+)\s*D\s*/\s*[\d.]+\s*mm\s*x\s*(\d+)°")
_RE_ACD_IOL  = re.compile(r"\bACD\s*:\s*([\d.]+)\s*mm")
_RE_ETAT     = re.compile(r"[ÉE]tat\s*:\s*(\w+)")
# IOL emmétropisante — ordre dans le PDF : OD×4 puis OS×4
# (Haigis, Holladay, SRKT, HofferQ) pour chaque œil
_RE_EMME     = re.compile(r"IOL emm[ée]\.\s*:\s*([\d.]+)")

# Biométrie MMT-Full
_RE_ACD      = re.compile(r"\bACD\s*:\s*([\d.]+)\s*mm")
_RE_COMP_AL  = re.compile(r"Comp\.\s*AL\s*:\s*([\d.]+)\s*mm")
_RE_K_MOY    = re.compile(r"Moyenne\s*:\s*([\d.]+)/([\d.]+)\s*D")
_RE_WTW      = re.compile(r"\bWTW\s*:\s*([\d.]+)\s*mm")
_RE_ETAT_LIB = re.compile(r"\b(Phaque|Pseudophaque)\b")


# ─────────────────────────────────────────────────────────────────────────────
# 4. HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _lire_pdf(chemin_pdf: Path) -> str:
    """Texte sélectionnable de toutes les pages (identique à suivi_al.py)."""
    with pdfplumber.open(str(chemin_pdf)) as pdf:
        return "\n".join(p.extract_text() for p in pdf.pages if p.extract_text())


def _champ_texte(match) -> str | None:
    """Valeur d'un champ texte, None si vide ou parasite (contient ':')."""
    if not match:
        return None
    val = match.group(1).strip()
    return val if val and ":" not in val else None


def _nth(lst: list, n: int, cast=float):
    try:
        return cast(lst[n])
    except (IndexError, TypeError, ValueError):
        return None


def _extraire_patient(txt: str) -> dict:
    """
       Trois formats possibles selon la configuration Zeiss :
      A) Nom en tête de document (avant "Nom :") : "DOE, JOHN\nNom :\nID :"
         → format "NOM, Prénom" ou "NOM Prénom"
      B) Nom sur la même ligne que le label      : "Nom : DUPONT Jean"
      C) Nom et prénom sur lignes séparées       : "Nom : DUPONT\nPrénom : Jean"
    """
    m_id  = _RE_ID.search(txt)
    m_dob = _RE_DOB.search(txt)

    nom    = None
    prenom = None

    # Format A : nom complet sur la ligne juste avant "Nom :"
    m_avant = re.search(r"^([\w][^\n,]+(?:,\s*[\w][^\n]+)?)\nNom\s*:", txt, re.MULTILINE)
    if m_avant:
        nom_brut = m_avant.group(1).strip()
        if "," in nom_brut:                        # "DOE, JOHN"
            parts  = [p.strip() for p in nom_brut.split(",", 1)]
            nom, prenom = parts[0], parts[1]
        elif " " in nom_brut:                      # "DUPONT Jean"
            parts  = nom_brut.split(None, 1)
            nom, prenom = parts[0], parts[1]
        else:
            nom = nom_brut
    else:
        # Formats B et C : nom dans le champ "Nom :"
        nom_brut = _champ_texte(_RE_NOM.search(txt))
        prenom_c = _champ_texte(_RE_PRENOM.search(txt))
        if nom_brut and not prenom_c and " " in nom_brut:
            parts  = nom_brut.split(None, 1)
            nom, prenom = parts[0], parts[1]
        else:
            nom, prenom = nom_brut, prenom_c

    return {
        "nom"            : nom    or None,
        "prenom"         : prenom or None,
        "id_zeiss"       : m_id.group(1) if m_id else None,
        "date_naissance" : m_dob.group(1) if m_dob else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. EXTRACTION PAR TYPE DE PDF
# ─────────────────────────────────────────────────────────────────────────────

def extraire_iol(pdf_path: Path) -> dict:
    """
    Extrait les données depuis un PDF IOL-Multiformula (Zeiss IOLMaster).

    pdfplumber retourne OD et OS côte à côte sur la même ligne :
    "AL : 30.35 mm (SNR = 46.4) AL : 25.36 mm (SNR = 193.9)"
    findall retourne [OD, OS] dans l'ordre, index 0 = OD, index 1 = OS.
    """
    txt = _lire_pdf(pdf_path)

    patient = _extraire_patient(txt)
    m_dom   = _RE_DOM.search(txt)
    m_cib   = _RE_CIBLE.search(txt)
    m_len   = _RE_LENTILLE.search(txt)
    m_ins   = _RE_INSTR.search(txt)

    session = {
        "date_mesure"        : m_dom.group(1) if m_dom else None,
        "refraction_cible_D" : float(m_cib.group(1)) if m_cib else None,
        "lentille"           : m_len.group(1).strip() if m_len else None,
    }

    al_vals   = _RE_AL.findall(txt)       # [OD, OS]
    k1_vals   = _RE_K1.findall(txt)       # [OD, OS]
    k2_vals   = _RE_K2.findall(txt)       # [OD, OS]
    acd_vals  = _RE_ACD_IOL.findall(txt)  # [OD, OS]
    etat_vals = _RE_ETAT.findall(txt)     # [OD, OS]
    iol_emme  = _RE_EMME.findall(txt)     # OD×4 puis OS×4

    def _iol_par_oeil(idx: int) -> dict:
        # Ordre dans le PDF : Haigis_OD[0], Holladay_OD[1], Haigis_OS[2], Holladay_OS[3],
        #                     SRKT_OD[4],   HofferQ_OD[5],  SRKT_OS[6],   HofferQ_OS[7]
        if idx == 0:  # OD
            positions = {"Haigis": 0, "Holladay": 1, "SRKT": 4, "HofferQ": 5}
        else:          # OS
            positions = {"Haigis": 2, "Holladay": 3, "SRKT": 6, "HofferQ": 7}
        return {f: _nth(iol_emme, i) for f, i in positions.items()}

    def _oeil(i: int) -> dict:
        # k1_vals et k2_vals sont des tuples (dioptries, axe)
        # ex: [('43.05', '144'), ('43.60', '54')]
        k1_tuple = k1_vals[i] if i < len(k1_vals) else None
        k2_tuple = k2_vals[i] if i < len(k2_vals) else None
        k1 = float(k1_tuple[0]) if k1_tuple else None
        k2 = float(k2_tuple[0]) if k2_tuple else None
        k1_axis = int(k1_tuple[1]) if k1_tuple else None
        k2_axis = int(k2_tuple[1]) if k2_tuple else None
        return {
            "AL_mm"               : _nth(al_vals,   i),
            "K1_D"                : k1,
            "K1_axis"             : k1_axis,
            "K2_D"                : k2,
            "K2_axis"             : k2_axis,
            "Km_D"                : round((k1 + k2) / 2, 2) if k1 and k2 else None,
            "ACD_mm"              : _nth(acd_vals,  i),
            "etat"                : _nth(etat_vals, i, str),
            "iol_emmetropisante_D": _iol_par_oeil(i),
        }

    return {
        "fichier"   : pdf_path.name,
        "source"    : "IOL-Multiformula",
        "instrument": m_ins.group(1).strip() if m_ins else "Zeiss IOLMaster",
        "patient"   : patient,
        "session"   : session,
        "OD"        : _oeil(0),
        "OS"        : _oeil(1),
    }


def extraire_mmt(pdf_path: Path) -> dict:
    """
    Extrait les données depuis un PDF MMT-Full.
    Retourne patient, session, OD/OS avec Comp.AL, ACD, WTW, K moyens.
    """
    txt = _lire_pdf(pdf_path)

    patient = _extraire_patient(txt)
    m_dom   = _RE_DOM.search(txt)
    m_ins   = _RE_INSTR.search(txt)

    session = {"date_mesure": m_dom.group(1) if m_dom else None}

    comp_al = _RE_COMP_AL.findall(txt)
    acd     = _RE_ACD.findall(txt)
    wtw     = _RE_WTW.findall(txt)
    k_moy   = _RE_K_MOY.findall(txt)
    etat    = _RE_ETAT_LIB.findall(txt)

    def _oeil(i):
        k1 = float(k_moy[i][0]) if len(k_moy) > i else None
        k2 = float(k_moy[i][1]) if len(k_moy) > i else None
        return {
            "comp_AL_mm": _nth(comp_al, i),
            "ACD_mm"    : _nth(acd,     i),
            "WTW_mm"    : _nth(wtw,     i),
            "K1_D"      : k1,
            "K2_D"      : k2,
            "Km_D"      : round((k1 + k2) / 2, 2) if k1 and k2 else None,
            "etat"      : _nth(etat,    i, str),
        }

    return {
        "fichier"   : pdf_path.name,
        "source"    : "MMT-Full",
        "instrument": m_ins.group(1).strip() if m_ins else "Zeiss IOLMaster",
        "patient"   : patient,
        "session"   : session,
        "OD"        : _oeil(0),
        "OS"        : _oeil(1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. FUSION IOL + MMT D'UNE MÊME SESSION
# ─────────────────────────────────────────────────────────────────────────────

def fusionner_session(iol: dict, mmt: dict | None) -> dict:
    """
    Fusionne un IOLMultiformula et son MMT-Full correspondant.
    Si mmt est None (pas de MMT pour cette session), retourne l'IOL seul enrichi.

    Priorité :
      - AL, K, ACD           : IOLMultiformula
      - WTW, comp_AL         : MMT-Full
      - iol_emmetropisante   : IOLMultiformula
      - Identité patient     : IOLMultiformula (fallback MMT)
    """
    def _merge_oeil(oeil: str) -> dict:
        i = iol.get(oeil, {})
        m = (mmt or {}).get(oeil, {})
        return {
            "AL_mm"               : i.get("AL_mm")  or m.get("comp_AL_mm"),
            "comp_AL_mm"          : m.get("comp_AL_mm"),
            "K1_D"                : i.get("K1_D")    or m.get("K1_D"),
            "K1_axis"             : i.get("K1_axis") or m.get("K1_axis"),
            "K2_D"                : i.get("K2_D")    or m.get("K2_D"),
            "K2_axis"             : i.get("K2_axis") or m.get("K2_axis"),
            "Km_D"                : i.get("Km_D")   or m.get("Km_D"),
            "ACD_mm"              : i.get("ACD_mm") or m.get("ACD_mm"),
            "WTW_mm"              : m.get("WTW_mm"),
            "etat"                : i.get("etat")   or m.get("etat"),
            "iol_emmetropisante_D": i.get("iol_emmetropisante_D"),
        }

    pi = iol.get("patient", {})
    pm = (mmt or {}).get("patient", {})

    return {
        "patient": {
            "nom"            : pi.get("nom")            or pm.get("nom"),
            "prenom"         : pi.get("prenom")         or pm.get("prenom"),
            "id_zeiss"       : pi.get("id_zeiss")       or pm.get("id_zeiss"),
            "date_naissance" : pi.get("date_naissance") or pm.get("date_naissance"),
        },
        "session": {
            "date_mesure"        : iol["session"].get("date_mesure"),
            "refraction_cible_D" : iol["session"].get("refraction_cible_D"),
            "lentille"           : iol["session"].get("lentille"),
            "date_mesure_mmt"    : mmt["session"].get("date_mesure") if mmt else None,
        },
        "instrument" : iol.get("instrument") or (mmt or {}).get("instrument"),
        "fichier_iol": iol.get("fichier"),
        "fichier_mmt": mmt.get("fichier") if mmt else None,
        "OD"         : _merge_oeil("OD"),
        "OS"         : _merge_oeil("OS"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. CHARGEMENT DEPUIS MDB  
# ─────────────────────────────────────────────────────────────────────────────

def charger_biometrie(patient_code: str) -> list[dict]:
    """
    Charge et extrait toutes les sessions biométriques d'un patient.

    Pour chaque IOLMultiformula trouvé en base :
      - Résout le chemin physique via find_patient_folder()
      - Extrait les données biométriques
      - Cherche le MMT-Full de la même date pour le fusionner

    Retourne une liste de sessions triées par date, chaque session étant
    un dict fusionné IOLMultiformula + MMT-Full (si disponible).
    """
    conn = _db_connect()

    # ── Récupération des documents depuis la base ─────────────────────────
    docs = pd.read_sql(
        "SELECT * FROM [Documents] WHERE [code patient] = ?",
        conn, params=(int(patient_code),)
    )

    col = "Photo externe"
    if col not in docs.columns:
        raise KeyError(f"Colonne '{col}' absente de la table Documents")

    # Séparer IOLMultiformula et MMT-Full
    iol_rows = docs[docs[col].astype(str).str.contains("IOL-Multiformula", na=False)]
    mmt_rows = docs[docs[col].astype(str).str.contains("MMT",             na=False)]

    print(f"  {len(iol_rows)} IOL-Multiformula / {len(mmt_rows)} MMT référencés en base")

    # ── Résolution du dossier physique (une seule fois par patient) ────────
    dossier = find_patient_folder(patient_code, conn)
    conn.close()

    if not dossier:
        log.error(f"Dossier patient introuvable : {patient_code}")
        return []

    # ── Index MMT par date pour appariement rapide ─────────────────────────
    # Clé : date au format YYYYMMDD extraite du nom de fichier
    mmt_par_date: dict[str, Path] = {}
    for _, row in mmt_rows.iterrows():
        nom = Path(str(row[col])).name
        m   = re.search(r"_(\d{8})_", nom)
        if m:
            mmt_par_date[m.group(1)] = dossier / nom

    # ── Extraction de chaque IOLMultiformula ──────────────────────────────
    sessions = []
    for _, row in iol_rows.iterrows():
        nom_iol  = Path(str(row[col])).name
        path_iol = dossier / nom_iol

        if not path_iol.exists():
            print(f"    ⚠  IOL introuvable : {nom_iol}")
            continue

        try:
            iol_data = extraire_iol(path_iol)
        except Exception as e:
            print(f"    ⚠  Erreur extraction IOL {nom_iol} : {e}")
            continue

        # Cherche le MMT de la même date (clé YYYYMMDD)
        m_date = re.search(r"_(\d{8})_", nom_iol)
        mmt_data = None
        if m_date:
            path_mmt = mmt_par_date.get(m_date.group(1))
            if path_mmt and path_mmt.exists():
                try:
                    mmt_data = extraire_mmt(path_mmt)
                except Exception as e:
                    print(f"    ⚠  Erreur extraction MMT {path_mmt.name} : {e}")
            else:
                log.debug(f"Pas de MMT pour la date {m_date.group(1)}")

        session = fusionner_session(iol_data, mmt_data)
        session["_date_sort"] = date_depuis_nom_fichier(nom_iol)

        nom    = session["patient"].get("nom",    "?")
        prenom = session["patient"].get("prenom", "")
        date   = session["session"].get("date_mesure", nom_iol)
        od_al  = session["OD"].get("AL_mm")
        os_al  = session["OS"].get("AL_mm")
        wtw    = session["OD"].get("WTW_mm")
        print(f"    ✓  {date}  {prenom} {nom}  OD={od_al}  OS={os_al}  WTW={wtw}")

        sessions.append(session)

    # Tri chronologique, suppression de la clé technique
    sessions.sort(key=lambda s: s.get("_date_sort") or pd.Timestamp.min)
    for s in sessions:
        s.pop("_date_sort", None)

    print(f"  {len(sessions)} session(s) extraite(s)")
    return sessions


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s %(message)s")

    p = argparse.ArgumentParser(
        description="Extraction biométrie depuis PDFs Zeiss IOLMaster via PUBLIC.MDB"
    )
    p.add_argument("patient_code", help="Code patient (ex: 66844742)")
    p.add_argument("--json", action="store_true", help="Afficher la sortie JSON complète")
    args = p.parse_args()

    print(f"▶ Chargement biométrie pour patient {args.patient_code}…")
    sessions = charger_biometrie(args.patient_code)

    if not sessions:
        print("Aucune session trouvée.")
        sys.exit(1)

    if args.json:
        # Conversion Timestamp → str pour la sérialisation JSON
        def _serial(obj):
            if isinstance(obj, pd.Timestamp):
                return obj.strftime("%d/%m/%Y")
            raise TypeError(f"Type non sérialisable : {type(obj)}")
        print(json.dumps(sessions, indent=2, ensure_ascii=False, default=_serial))
    else:
        print(f"\n✓ {len(sessions)} session(s) pour le patient {args.patient_code}")
# ESCRS IOL Calculator — Guide

Application desktop Windows permettant de préremplir automatiquement le calculateur IOL ESCRS à partir des données biométriques patient extraites de la base locale StudioVision.

---

## Table des matières

- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Données extraites automatiquement](#données-extraites-automatiquement)
- [Modes de calcul](#modes-de-calcul)
- [Export PDF](#export-pdf)
- [Résolution des problèmes](#résolution-des-problèmes)
- [Développement](#développement)

---

## Architecture

```
escrs-app/
├── Installer.bat                  # Installation automatique (lancer une fois)
├── Lancer ESCRS.bat               # Démarrage de l'application
├── setup.py                       # Script d'installation Python
├── requirements.txt               # Dépendances Python
│
├── src/
│   ├── main.ts                    # Processus principal Electron
│   ├── preload.ts                 # Bridge IPC sécurisé
│   └── renderer/
│       ├── index.html             # Interface médecin
│       ├── renderer.ts            # Logique UI
│       ├── guide_escrs.html       # Guide d'utilisation
│       └── tsconfig.json
│
├── python/
│   ├── escrs_connector.py         # Pipeline principal
│   ├── extraction_biometrie.py    # Extraction PDFs Zeiss IOLMaster
│   ├── pachymetry_ocr.py          # OCR images Optovue
│   └── escrs_inject.js            # Script d'injection ESCRS
│
├── vendor/
│   └── tesseract/                 # Tesseract OCR embarqué
│       ├── tesseract.exe
│       ├── tessdata/
│       └── *.dll
│
├── dist/                          # Généré par tsc — ne pas modifier
├── package.json
└── tsconfig.json
```

---

## Prérequis

| Logiciel | Version | Obligatoire |
|---|---|---|
| Windows | 10/11 64 bits | ✅ |
| Python | 3.11+ | ✅ |
| Node.js | 20+ | ✅ (installé automatiquement) |
| Microsoft Access Database Engine 2016 | 64 bits | ✅ |


> ⚠ **Access Database Engine** doit être en **64 bits** si Python est en 64 bits.
> Télécharger : https://www.microsoft.com/en-us/download/details.aspx?id=54920

---

## Installation

### Première installation sur un poste

**1.** Copier le dossier `escrs-app/` sur le poste (clé USB, réseau, etc.)

**2.** Double-cliquer sur `Installer.bat`

Le script installe automatiquement :
- Node.js 20 LTS (si absent)
- Les dépendances Python (`pip install -r requirements.txt`)
- Tesseract OCR dans `vendor/tesseract/`
- Les dépendances Electron (`npm install`)
- Compile le TypeScript (`npm run build`)

**3.** Une fois l'installation terminée, double-cliquer sur `Lancer ESCRS.bat`

### Installations suivantes

Double-cliquer simplement sur `Lancer ESCRS.bat`.

### Tesseract OCR

Tesseract est installé automatiquement dans `vendor/tesseract/`. Si le téléchargement échoue (réseau restreint), copier manuellement le dossier `Tesseract-OCR` depuis un poste existant vers `vendor/tesseract/`.

> Le projet utilise toujours sa propre version dans `vendor/tesseract/` en priorité.

---

## Utilisation

### Flux de travail

```
1. Ouvrir le patient dans StudioVsion
         ↓
2. Lancer ESCRS.bat
         ↓
3. Cliquer sur "⟳ Détecter le patient actif dans Access"
         ↓
4. Choisir le mode (Standard / Torique / Post LASIK)
         ↓
5. Saisir le fabricant et le modèle d'IOL
         ↓
6. Cliquer sur "Calculer sur ESCRS →
         ↓
7. La fenêtre ESCRS s'ouvre et se préremplie automatiquement
         ↓
8. Vérifier les valeurs et cliquer sur Calculate
         ↓
9. Ctrl+P ou bouton Print → enregistrer en PDF
```

### Interface

| Champ | Description |
|---|---|
| ⟳ Détecter | Lit le patient actif dans StudioVision via COM |
| Chirurgien | Nom affiché dans ESCRS |
| Fabricant | Ex : Alcon, HOYA, BVI, Zeiss |
| Modèle IOL | Nom exact tel qu'affiché dans ESCRS |
| Indice de réfraction | 1.3375 (défaut), 1.332, 1.3315 |
| Réfraction cible OD/OS | En dioptries (0.00 par défaut) |

---

## Données extraites automatiquement

| Donnée | Source |
|---|---|
| AL (longueur axiale) | PDF Zeiss IOLMaster |
| K1, K2 (kératométrie) | PDF Zeiss IOLMaster |
| K1 axis, K2 axis | PDF Zeiss IOLMaster |
| ACD (profondeur chambre antérieure) | PDF Zeiss IOLMaster |
| WTW (white-to-white) | PDF Zeiss IOLMaster |
| CCT (épaisseur cornéenne) | Image Optovue (OCR) |
| Sexe du patient | PUBLIC.MDB — champ SEXE ou numéro SS |
| Initiales patient | PUBLIC.MDB — NOM / Prénom |
| Âge | Calculé depuis la date de naissance |

> Si plusieurs sessions biométriques existent, la **plus récente** est utilisée automatiquement.

---

## Modes de calcul

### Standard
Calcul IOL classique pour œil non opéré.
- Formules : Barrett, Kane, Hill-RBF, Pearl DGS

### Torique
Correction de l'astigmatisme cornéen.
- Les axes K1/K2 sont extraits automatiquement du PDF
- Incision : 135° (fixe)
- SIA : 0.3 D (fixe)
- Formules : Barrett, Kane, EVO, Hill-RBF

### Post LASIK/PRK
Œil opéré au laser réfractif.
- Type : Myopique ou Hypermétropique
- Formules : Barrett True K, EVO, Hoffer QST

---

## Export PDF

Trois façons d'enregistrer les résultats :

| Méthode | Action |
|---|---|
| **Ctrl+P** | Dans la fenêtre ESCRS → dialogue d'enregistrement PDF |
| **Bouton Print** | Sur le site ESCRS → dialogue d'enregistrement PDF |
| **IPC save-pdf** | Depuis l'interface principale si besoin |

---

## Résolution des problèmes

### "Aucun patient ouvert dans Access"
StudioVsion doit être ouvert avec le formulaire patient visible.
Vérifier que `pywin32` est installé : `pip install pywin32`

### "Aucune session biométrique trouvée"
Vérifier que les PDFs biométriques sont présents dans le dossier patient.
Vérifier que `DEST_PHOTOS` dans `escrs_connector.py` pointe vers le bon dossier.

### "IOL non trouvé dans ESCRS"
Le nom de l'IOL doit correspondre **exactement** à celui du dropdown ESCRS (majuscules, espaces, parenthèses).

### Erreur Microsoft Access Database Engine
Installer le pilote 64 bits depuis :
https://www.microsoft.com/en-us/download/details.aspx?id=54920

### Le formulaire ESCRS ne se remplit pas
- Vérifier la connexion internet
- Fermer la fenêtre ESCRS et relancer le calcul
- Le CAPTCHA peut nécessiter une résolution manuelle au premier lancement

### Tesseract introuvable
Vérifier que `vendor/tesseract/tesseract.exe` existe et contient toutes les DLLs.
Relancer `Installer.bat` pour réinstaller Tesseract.

---

## Développement

### Recompiler après modification TypeScript
```bash
npm run build
```

### Lancer l'application
```bash
npm start
```

### Activer les DevTools
Dans `src/main.ts`, décommenter :
```typescript
// mainWindow.webContents.openDevTools();  // interface principale
// win.webContents.openDevTools();          // fenêtre ESCRS
```

### Tester le pipeline Python
```bash
cd python
python escrs_connector.py 66844742 --surgeon "Dr Dupont" --manufacturer Alcon --iol "AcrySof SN60WF" --json
```

### Tester la pachymétrie OCR
```bash
cd python
python pachymetry_ocr.py image.jpg --debug
```

### Structure des données patient (JSON)
```json
{
  "mode":     "normal",
  "surgeon":  "Dr Dupont",
  "initials": "J.D",
  "gender":   "Female",
  "age":      73,
  "index":    "1.3375",
  "formulas": ["Barrett", "Kane", "Hill-RBF", "Pearl DGS"],
  "rightEye": {
    "al": 24.05, "acd": 3.08, "lt": null, "cct": null,
    "wtw": 11.9,  "k1": 43.05, "k2": 43.60,
    "manufacturer": "Alcon", "iol": "AcrySof SN60WF",
    "targetRefraction": 0.0
  },
  "leftEye": { "..." : "..." }
}
```

---

## Dépendances

### Python
| Package | Usage |
|---|---|
| pyodbc | Connexion à PUBLIC.MDB (Access) |
| pandas | Manipulation des données tabulaires |
| pdfplumber | Extraction texte PDFs biométriques |
| pytesseract | OCR images pachymétriques |
| opencv-python-headless | Prétraitement images OCR |
| numpy | Calculs matriciels |
| pywin32 | Détection patient actif dans Access |

### Node.js
| Package | Usage |
|---|---|
| electron | Framework desktop WebView |
| typescript | Typage statique |
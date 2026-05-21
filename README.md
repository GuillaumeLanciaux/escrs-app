# ESCRS-APP

> Calculateur IOL desktop — interface pour pré-remplir le calculateur ESCRS

Résumé
------
ESCRS-APP est une application desktop (Electron + TypeScript) qui automatise
le pré-remplissage du calculateur IOL ESCRS à partir des données patients
stockées localement (PDF Zeiss, images pachymétrie, base ACCESS).

Architecture — comment ça marche
-------------------------------
- Renderer (`src/renderer`) : interface médecin (formulaire, bouton "Calculer").
- Preload (`src/preload.ts`) : pont sécurisé exposant `window.escrsAPI.calculer()`.
- Main (`src/main.ts`) : processus principal Electron.
  - Écrit les paramètres en JSON temporaire et lance le script Python
    `python/escrs_connector.py`.
  - Reçoit en sortie JSON un champ `script_js` contenant un script JS prêt
    à être injecté dans le site ESCRS.
  - Ouvre une fenêtre vers `https://iolcalculator.escrs.org`, attend que
    l'interface Blazor soit prête, injecte le JS et permet l'export PDF.
- Python (`python/`) : extraction et conversion des données patient en objet
  compatible ESCRS.
  - `extraction_biometrie.py` : extraction depuis PDF Zeiss (pdfplumber, pandas).
  - `pachymetry_ocr.py` : OCR des rapports pachymétrie (pytesseract, OpenCV).
  - `escrs_connector.py` : orchestration, lecture de PUBLIC.MDB, génération
    du `script_js` à partir du template `python/escrs_inject.js`.

Principaux flux
---------------
1. L'utilisateur saisit un `patient_code` et options dans l'UI et clique "Calculer".
2. Le renderer envoie les paramètres au main via `ipcRenderer`.
3. Le main lance Python avec les paramètres (fichier temporaire).
4. Python extrait biométrie + pachymétrie, construit l'objet patient ESCRS
   et renvoie un `script_js` via stdout en JSON.
5. Le main ouvre la page ESCRS, injecte le script qui remplit les champs
   (simulateur d'interactions DOM). L'utilisateur peut ensuite vérifier et
   lancer le calcul sur le site ESCRS.
6. Un export PDF peut être déclenché depuis le site (`window.print`) ou
   via Ctrl+P → le main capture la page et enregistre un PDF.

Prérequis
---------
- Node.js & npm (ex: Node 18+ recommandé).
- Python 3 installé et disponible dans le PATH.
- Pour l'extraction depuis PUBLIC.MDB : driver ODBC Microsoft Access (Access
  Database Engine 2016 x64) et fichier `PUBLIC.MDB` accessible (chemin
  configuré dans les scripts Python).
- Tesseract OCR (binaire) — sur Windows le dépôt contient `tesseract/tesseract.exe`
  et `pachymetry_ocr.py` définit la variable `pytesseract.pytesseract.tesseract_cmd`
  vers ce chemin. Sinon installez Tesseract et mettez à jour la variable.

Dépendances Python
------------------
Le fichier `requirements.txt` à la racine contient les dépendances Python
utilisées par les scripts (`pyodbc`, `pdfplumber`, `pandas`, `pytesseract`,
`opencv-python-headless`, `numpy`). Installez-les depuis un virtualenv :

```bash
# Créer et activer un virtualenv (macOS / Linux)
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# Installer les dépendances
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Scripts NPM
-----------
- `npm run build` : compile TypeScript (main + renderer).
- `npm start`     : `build` puis lance Electron.
- `npm run dev`   : mode développement (watch + electron . --dev).

Lancer l'application
--------------------
1. Installer les dépendances Node :

```bash
npm install
```

2. Installer les dépendances Python (via `requirements.txt`) :

```bash
# activez d'abord votre virtualenv (voir ci-dessus), puis :
python -m pip install -r requirements.txt
```

3. Démarrer l'app :

```bash
npm start
```

Exécution manuelle / débogage
----------------------------
- Tester le connecteur Python seul :

```bash
python python/escrs_connector.py 66844742 --json
```

- Mode Electron : le main écrit les paramètres dans un fichier JSON temporaire
  et attend le JSON de sortie de Python — utile pour reproduire le flux en CLI.

Fichiers de configuration importants
-----------------------------------
- `python/escrs_connector.py` : chemins vers `PUBLIC.MDB` et `DEST_PHOTOS`.
- `pachymetry_ocr.py` : chemin du binaire Tesseract (ligne `tesseract_cmd`).

Sécurité & limites
------------------
- Le preload utilise `contextBridge` et n'expose qu'une API minimale (`calculer`).
- Python doit être fiable : le main lit stdout et attend strictement du JSON —
  ne pas afficher d'autres logs sur stdout en mode Electron (les scripts
  utilisent stderr pour les logs techniques).

Fichiers utiles
--------------
- `src/main.ts`, `src/preload.ts`, `src/renderer/renderer.ts`
- `python/escrs_connector.py`, `python/extraction_biometrie.py`,
  `python/pachymetry_ocr.py`, `python/escrs_inject.js`

Dépôt & gitignore
------------------
Le dépôt ignore `node_modules/` et `tesseract/` (cf `.gitignore`).

Support
-------
Si vous voulez, j'ajoute un `requirements.txt` avec les dépendances Python,
ou je détaille les chemins à adapter pour `PUBLIC.MDB` et Tesseract.

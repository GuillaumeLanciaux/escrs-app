/**
 * main.ts — Processus principal Electron
 */

import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { spawn }  from 'child_process';
import * as path  from 'path';
import * as fs    from 'fs';
import * as os    from 'os';

const PYTHON_SCRIPT = path.join(__dirname, '..', 'python', 'escrs_connector.py');
const ESCRS_URL     = 'https://iolcalculator.escrs.org';

let mainWindow:  BrowserWindow | null = null;
let escrsWindow: BrowserWindow | null = null;


// 1. FENÊTRE PRINCIPALE

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width:  600,
    height: 750,
    title:  'Calculateur IOL ESCRS',
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration:  false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'src', 'renderer', 'index.html'));
  // mainWindow.webContents.openDevTools();
  mainWindow.on('closed', () => { mainWindow = null; });
}


// 2. FENÊTRE ESCRS + EXPORT PDF

async function _savePDF(win: BrowserWindow): Promise<void> {
  const parentWin = win.isDestroyed() ? (mainWindow ?? undefined) : win;
  const { canceled, filePath } = await dialog.showSaveDialog(parentWin!, {
    title:       'Enregistrer les résultats ESCRS',
    defaultPath: `ESCRS_${new Date().toISOString().slice(0, 10)}.pdf`,
    filters:     [{ name: 'PDF', extensions: ['pdf'] }],
  });

  if (canceled || !filePath) return;

  try {
    const data = await win.webContents.printToPDF({
      printBackground: true,
      pageSize:        'A4',
      landscape:       false,
      margins: {
        marginType: 'printableArea',
      },
    });

    fs.writeFileSync(filePath, data);
    console.log(`  ✓ PDF enregistré : ${filePath}`);
  } catch (err) {
    console.error('Erreur export PDF :', err);
    dialog.showErrorBox('Erreur', `Impossible d'enregistrer le PDF :\n${err}`);
  }
}

function createEscrsWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width:  1400,
    height: 900,
    title:  'ESCRS IOL Calculator',
    webPreferences: {
      contextIsolation: false,
      nodeIntegration:  false,
      session: require('electron').session.fromPartition('persist:escrs'),
    },
  });

  // Intercepter Ctrl+P
  win.webContents.on('before-input-event', (_event, input) => {
    if ((input.control || input.meta) && input.key === 'p') {
      _event.preventDefault();
      _savePDF(win);
    }
  });

  // Intercepter window.print() appelé par le bouton Print du site ESCRS
  win.webContents.on('did-finish-load', () => {
    win.webContents.executeJavaScript(`
      window.print = function() {
        document.dispatchEvent(new CustomEvent('escrs-print-request'));
      };
      document.addEventListener('escrs-print-request', function() {
        const orig = document.title;
        document.title = '__ESCRS_PRINT__';
        setTimeout(() => { document.title = orig; }, 500);
      });
    `).catch(() => {});
  });

  // Détecter le changement de titre pour déclencher le PDF
  win.webContents.on('page-title-updated', (_event, title) => {
    if (title === '__ESCRS_PRINT__') {
      _savePDF(win);
    }
  });

  // win.webContents.openDevTools();
  win.on('closed', () => { escrsWindow = null; });
  return win;
}


// 3. APPEL PYTHON — helpers génériques

interface PythonResult {
  script_js:     string;
  patient_escrs: Record<string, unknown>;
}

/** Lance Python avec des arguments arbitraires et retourne stdout parsé en JSON. */
function runPythonArgs(args: string[]): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const py = spawn('python', [PYTHON_SCRIPT, ...args], {
      env: { ...process.env }
    });

    let stdout = '';
    let stderr = '';

    py.stdout.on('data', (d: Buffer) => stdout += d.toString());
    py.stderr.on('data', (d: Buffer) => {
      const line = d.toString();
      stderr += line;
      process.stdout.write('[Python] ' + line);
    });

    py.on('close', (code: number) => {
      if (code !== 0) {
        reject(new Error(`Python error (code ${code}):\n${stderr}`));
        return;
      }
      // Trouver le premier '{' pour ignorer les éventuels logs avant le JSON
      const jsonStart = stdout.indexOf('{');
      if (jsonStart === -1) {
        reject(new Error(`Aucun JSON trouvé dans stdout:\n${stdout}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout.slice(jsonStart)));
      } catch {
        reject(new Error(`JSON parse error:\n${stdout}`));
      }
    });
  });
}

/** Lance Python avec un fichier de paramètres JSON (mode Electron existant). */
function runPython(params: Record<string, unknown>): Promise<PythonResult> {
  return new Promise((resolve, reject) => {
    const tmpFile = path.join(os.tmpdir(), 'escrs_params.json');
    fs.writeFileSync(tmpFile, JSON.stringify(params, null, 2), 'utf-8');

    const py = spawn('python', [PYTHON_SCRIPT, '--params-file', tmpFile], {
      env: { ...process.env }
    });

    let stdout = '';
    let stderr = '';

    py.stdout.on('data', (d: Buffer) => stdout += d.toString());
    py.stderr.on('data', (d: Buffer) => {
      const line = d.toString();
      stderr += line;
      process.stdout.write('[Python] ' + line);
    });

    py.on('close', (code: number) => {
      try { fs.unlinkSync(tmpFile); } catch {}

      if (code !== 0) {
        reject(new Error(`Python error (code ${code}):\n${stderr}`));
        return;
      }

      const jsonStart = stdout.indexOf('{"script_js"');
      if (jsonStart === -1) {
        reject(new Error(`Aucun JSON trouvé dans stdout:\n${stdout}`));
        return;
      }

      try {
        resolve(JSON.parse(stdout.slice(jsonStart)) as PythonResult);
      } catch {
        reject(new Error(`JSON parse error:\n${stdout}`));
      }
    });
  });
}


// 4. IPC

/**
 * Détection automatique du patient actif dans Access.
 * Retourne { code, nom, prenom } ou { code: null } si rien n'est ouvert.
 */
ipcMain.handle('get-active-patient', async () => {
  try {
    const result = await runPythonArgs(['--get-active-patient']) as Record<string, string | null>;
    return { success: true, patient: result };
  } catch (err) {
    console.error('get-active-patient error:', err);
    return { success: false, patient: { code: null }, error: String(err) };
  }
});

/** Calcul ESCRS principal — inchangé. */
ipcMain.handle('calculer-escrs', async (_event, params: Record<string, unknown>) => {
  try {
    const result = await runPython(params);

    // ── Créer et charger la page une seule fois ────────────────────────────
    if (!escrsWindow || escrsWindow.isDestroyed()) {
      escrsWindow = createEscrsWindow();
      await escrsWindow.loadURL(ESCRS_URL);
      escrsWindow.show();

      console.log('  ⏳ Attente Blazor…');
      await escrsWindow.webContents.executeJavaScript(`
        new Promise((resolve) => {
          const check = setInterval(() => {
            const inputs = document.querySelectorAll('input.mud-input-slot');
            if (inputs.length >= 5) {
              clearInterval(check);
              setTimeout(resolve, 1500);
            }
          }, 300);
          setTimeout(() => { clearInterval(check); resolve(null); }, 15000);
        })
      `);
    } else {
      // Fenêtre déjà ouverte — juste la mettre au premier plan
      await escrsWindow.webContents.executeJavaScript(`
        (function() {
          const btns = Array.from(document.querySelectorAll('button'));
          const editBtn = btns.find(b => b.textContent?.trim().toLowerCase() === 'edit');
          if (editBtn) editBtn.click();
        })()
      `);
      await new Promise(r => setTimeout(r, 1000));
      escrsWindow.show();
      escrsWindow.focus();
    }

    console.log('  ▶ Injection des données patient…');
    await escrsWindow.webContents.executeJavaScript(result.script_js);
    console.log('  ✓ Injection complète');

    return { success: true };

  } catch (err) {
    console.error('Erreur:', err);
    return { success: false, error: String(err) };
  }
});

// Déclenchement manuel du PDF depuis le renderer si besoin
ipcMain.handle('save-pdf', async () => {
  if (escrsWindow && !escrsWindow.isDestroyed()) {
    await _savePDF(escrsWindow);
    return { success: true };
  }
  return { success: false, error: 'Fenêtre ESCRS non disponible' };
});


// 5. LIFECYCLE

app.whenReady().then(() => {
  const escrsSession = require('electron').session.fromPartition('persist:escrs');
  escrsSession.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
  );
  createMainWindow();
});

app.on('activate', () => {
  if (!mainWindow) createMainWindow();
});
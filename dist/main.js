"use strict";
/**
 * main.ts — Processus principal Electron
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const PYTHON_SCRIPT = path.join(__dirname, '..', 'python', 'escrs_connector.py');
const ESCRS_URL = 'https://iolcalculator.escrs.org';
let mainWindow = null;
let escrsWindow = null;
// 1. FENÊTRE PRINCIPALE
function createMainWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 600,
        height: 750,
        title: 'Calculateur IOL ESCRS',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    mainWindow.loadFile(path.join(__dirname, '..', 'src', 'renderer', 'index.html'));
    // mainWindow.webContents.openDevTools();
    mainWindow.on('closed', () => { mainWindow = null; });
}
// 2. FENÊTRE ESCRS + EXPORT PDF
async function _savePDF(win) {
    const parentWin = win.isDestroyed() ? (mainWindow ?? undefined) : win;
    // ✅ CORRECTION : ne pas destructurer directement, utiliser result
    const result = await electron_1.dialog.showSaveDialog(parentWin, {
        title: 'Enregistrer les résultats ESCRS',
        defaultPath: `ESCRS_${new Date().toISOString().slice(0, 10)}.pdf`,
        filters: [{ name: 'PDF', extensions: ['pdf'] }],
    });
    if (result.canceled || !result.filePath)
        return;
    try {
        const data = await win.webContents.printToPDF({
            printBackground: true,
            pageSize: 'A4',
            landscape: false,
            margins: {
                marginType: 'printableArea',
            },
        });
        fs.writeFileSync(result.filePath, data);
        console.log(`  ✓ PDF enregistré : ${result.filePath}`);
    }
    catch (err) {
        console.error('Erreur export PDF :', err);
        electron_1.dialog.showErrorBox('Erreur', `Impossible d'enregistrer le PDF :\n${err}`);
    }
}
function createEscrsWindow() {
    const win = new electron_1.BrowserWindow({
        width: 1400,
        height: 900,
        title: 'ESCRS IOL Calculator',
        webPreferences: {
            contextIsolation: false,
            nodeIntegration: false,
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
    `).catch(() => { });
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
/** Lance Python avec des arguments arbitraires et retourne stdout parsé en JSON. */
function runPythonArgs(args) {
    return new Promise((resolve, reject) => {
        const py = (0, child_process_1.spawn)('python', [PYTHON_SCRIPT, ...args], {
            env: { ...process.env }
        });
        let stdout = '';
        let stderr = '';
        py.stdout.on('data', (d) => stdout += d.toString());
        py.stderr.on('data', (d) => {
            const line = d.toString();
            stderr += line;
            process.stdout.write('[Python] ' + line);
        });
        py.on('close', (code) => {
            if (code !== 0) {
                reject(new Error(`Python error (code ${code}):\n${stderr}`));
                return;
            }
            const jsonStart = stdout.indexOf('{');
            if (jsonStart === -1) {
                reject(new Error(`Aucun JSON trouvé dans stdout:\n${stdout}`));
                return;
            }
            try {
                resolve(JSON.parse(stdout.slice(jsonStart)));
            }
            catch {
                reject(new Error(`JSON parse error:\n${stdout}`));
            }
        });
    });
}
/** Lance Python avec un fichier de paramètres JSON (mode Electron existant). */
function runPython(params) {
    return new Promise((resolve, reject) => {
        const tmpFile = path.join(os.tmpdir(), 'escrs_params.json');
        fs.writeFileSync(tmpFile, JSON.stringify(params, null, 2), 'utf-8');
        const py = (0, child_process_1.spawn)('python', [PYTHON_SCRIPT, '--params-file', tmpFile], {
            env: { ...process.env }
        });
        let stdout = '';
        let stderr = '';
        py.stdout.on('data', (d) => stdout += d.toString());
        py.stderr.on('data', (d) => {
            const line = d.toString();
            stderr += line;
            process.stdout.write('[Python] ' + line);
        });
        py.on('close', (code) => {
            try {
                fs.unlinkSync(tmpFile);
            }
            catch { }
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
                resolve(JSON.parse(stdout.slice(jsonStart)));
            }
            catch {
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
electron_1.ipcMain.handle('get-active-patient', async () => {
    try {
        const result = await runPythonArgs(['--get-active-patient']);
        return { success: true, patient: result };
    }
    catch (err) {
        console.error('get-active-patient error:', err);
        return { success: false, patient: { code: null }, error: String(err) };
    }
});
/** Calcul ESCRS principal — inchangé. */
electron_1.ipcMain.handle('calculer-escrs', async (_event, params) => {
    try {
        const result = await runPython(params);
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
        }
        else {
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
    }
    catch (err) {
        console.error('Erreur:', err);
        return { success: false, error: String(err) };
    }
});
// Déclenchement manuel du PDF depuis le renderer si besoin
electron_1.ipcMain.handle('save-pdf', async () => {
    if (escrsWindow && !escrsWindow.isDestroyed()) {
        await _savePDF(escrsWindow);
        return { success: true };
    }
    return { success: false, error: 'Fenêtre ESCRS non disponible' };
});
// 5. LIFECYCLE
electron_1.app.whenReady().then(() => {
    const escrsSession = require('electron').session.fromPartition('persist:escrs');
    escrsSession.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36');
    createMainWindow();
});
electron_1.app.on('activate', () => {
    if (!mainWindow)
        createMainWindow();
});

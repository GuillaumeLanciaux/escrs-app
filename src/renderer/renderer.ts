/**
 * renderer.ts — Logique de l'interface médecin
 */

// Typage de l'API exposée par preload.ts via contextBridge
interface EscrsAPI {
  calculer: (params: Record<string, unknown>) => Promise<{
    success: boolean;
    error?:  string;
  }>;
}

// Extension de Window sans redéclarer la variable globale
interface Window {
  escrsAPI: EscrsAPI;
}

// ── Mode tabs ──────────────────────────────────────────────────────────────

let currentMode = 'normal';

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentMode = (tab as HTMLElement).dataset.mode || 'normal';
    document.body.className = `mode-${currentMode}`;
  });
});

// ── Bouton calculer ────────────────────────────────────────────────────────

const btn       = document.getElementById('btn-calculer') as HTMLButtonElement;
const statusDiv = document.getElementById('status')        as HTMLDivElement;

function setStatus(msg: string, type: 'info' | 'success' | 'error'): void {
  statusDiv.textContent = msg;
  statusDiv.className   = type;
}

function getVal(id: string): string {
  return (document.getElementById(id) as HTMLInputElement)?.value?.trim() || '';
}

function getNum(id: string): number | null {
  const v = parseFloat(getVal(id));
  return isNaN(v) ? null : v;
}

btn.addEventListener('click', async () => {
  const patientCode = getVal('patient_code');
  if (!patientCode) {
    setStatus('⚠ Veuillez saisir un code patient.', 'error');
    return;
  }

  btn.disabled = true;
  setStatus('⏳ Chargement des données patient…', 'info');

  // ── Construction des paramètres ──────────────────────────────────────────
  const params: Record<string, unknown> = {
    patient_code:  patientCode,
    surgeon:       getVal('surgeon'),
    manufacturer:  getVal('manufacturer'),
    iol:           getVal('iol'),
    mode:          currentMode,
    index:         getVal('index'),
    target_od:     getNum('target_od') ?? 0.0,
    target_og:     getNum('target_og') ?? 0.0,
  };

  if (currentMode === 'toric') {
    Object.assign(params, {
      k1axis_od:   getNum('k1axis_od'),
      k2axis_od:   getNum('k2axis_od'),
      incision_od: getNum('incision_od'),
      sia_od:      getNum('sia_od'),
      k1axis_og:   getNum('k1axis_og'),
      k2axis_og:   getNum('k2axis_og'),
      incision_og: getNum('incision_og'),
      sia_og:      getNum('sia_og'),
    });
  }

  if (currentMode === 'postlasik') {
    params.post_lasik_type = getVal('postLasikType');
  }

  // ── Appel principal ──────────────────────────────────────────────────────
  try {
    setStatus('⏳ Extraction biométrie + pachymétrie…', 'info');
    const api    = (window as Window & typeof globalThis).escrsAPI;
    const result = await api.calculer(params);

    if (result.success) {
      setStatus('✓ Données injectées — le médecin peut valider et calculer.', 'success');
    } else {
      setStatus(`✗ Erreur : ${result.error}`, 'error');
    }
  } catch (err) {
    setStatus(`✗ Erreur inattendue : ${err}`, 'error');
  } finally {
    btn.disabled = false;
  }
});
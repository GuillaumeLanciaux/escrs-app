"use strict";
/**
 * renderer.ts — Logique de l'interface médecin
 */
// ── État global ────────────────────────────────────────────────────────────
let currentMode = 'normal';
let currentPatientCode = ''; // remplace getVal('patient_code')
// ── Mode tabs ──────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentMode = tab.dataset.mode || 'normal';
        document.body.className = `mode-${currentMode}`;
    });
});
// ── Helpers ────────────────────────────────────────────────────────────────
const btn = document.getElementById('btn-calculer');
const btnAutoDetect = document.getElementById('btn-auto-detect');
const btnClear = document.getElementById('btn-clear-patient');
const patientCard = document.getElementById('patient-card');
const patientName = document.getElementById('patient-name');
const patientCodeDisplay = document.getElementById('patient-code-display');
const statusDiv = document.getElementById('status');
function setStatus(msg, type) {
    statusDiv.textContent = msg;
    statusDiv.className = type;
}
function getVal(id) {
    return document.getElementById(id)?.value?.trim() || '';
}
function getNum(id) {
    const v = parseFloat(getVal(id));
    return isNaN(v) ? null : v;
}
function afficherPatient(patient) {
    if (!patient.code)
        return;
    currentPatientCode = patient.code;
    const name = [patient.prenom, patient.nom].filter(Boolean).join(' ');
    patientName.textContent = name || `Patient ${patient.code}`;
    patientCodeDisplay.textContent = `Code : ${patient.code}`;
    patientCard.classList.add('visible');
}
function effacerPatient() {
    currentPatientCode = '';
    patientCard.classList.remove('visible');
    patientName.textContent = '—';
    patientCodeDisplay.textContent = 'Code : —';
}
// ── Détection automatique ─────────────────────────────────────────────────
btnAutoDetect.addEventListener('click', async () => {
    btnAutoDetect.disabled = true;
    btnAutoDetect.textContent = '⟳ Détection…';
    setStatus('⏳ Lecture du patient actif dans Access…', 'info');
    try {
        const api = window.escrsAPI;
        const result = await api.getActivePatient();
        if (result.success && result.patient.code) {
            afficherPatient(result.patient);
            const name = [result.patient.prenom, result.patient.nom].filter(Boolean).join(' ');
            setStatus(`✓ Patient détecté : ${name} (${result.patient.code})`, 'success');
        }
        else {
            setStatus('⚠ Aucun patient ouvert dans Access.', 'error');
        }
    }
    catch (err) {
        setStatus(`✗ Erreur détection : ${err}`, 'error');
    }
    finally {
        btnAutoDetect.disabled = false;
        btnAutoDetect.textContent = '⟳ Détecter le patient actif dans Access';
    }
});
// ── Effacer patient ────────────────────────────────────────────────────────
btnClear?.addEventListener('click', () => {
    effacerPatient();
    setStatus('', 'info');
    statusDiv.style.display = 'none';
});
// ── Guide ──────────────────────────────────────────────────────────────────
document.getElementById('btn-guide')?.addEventListener('click', (e) => {
    e.preventDefault();
    const api = window.escrsAPI;
    api.ouvrirGuide();
});
// ── Bouton calculer ────────────────────────────────────────────────────────
btn.addEventListener('click', async () => {
    // Vérifier qu'un patient est détecté
    if (!currentPatientCode) {
        setStatus('⚠ Veuillez détecter un patient via le bouton "⟳ Détecter".', 'error');
        return;
    }
    // Vérifier que l'IOL est renseigné
    const iol = getVal('iol');
    if (!iol) {
        setStatus('⚠ Veuillez saisir le modèle IOL.', 'error');
        return;
    }
    btn.disabled = true;
    setStatus('⏳ Chargement des données patient…', 'info');
    // ── Construction des paramètres ──────────────────────────────────────────
    const params = {
        patient_code: currentPatientCode,
        surgeon: getVal('surgeon'),
        manufacturer: getVal('manufacturer'),
        iol: iol,
        mode: currentMode,
        index: getVal('index'),
        target_od: getNum('target_od') ?? 0.0,
        target_og: getNum('target_og') ?? 0.0,
    };
    if (currentMode === 'toric') {
        Object.assign(params, {
            k1axis_od: getNum('k1axis_od'),
            k2axis_od: getNum('k2axis_od'),
            incision_od: getNum('incision_od'),
            sia_od: getNum('sia_od'),
            k1axis_og: getNum('k1axis_og'),
            k2axis_og: getNum('k2axis_og'),
            incision_og: getNum('incision_og'),
            sia_og: getNum('sia_og'),
        });
    }
    if (currentMode === 'postlasik') {
        params.post_lasik_type = getVal('postLasikType');
    }
    // ── Appel principal ──────────────────────────────────────────────────────
    try {
        setStatus('⏳ Extraction biométrie + pachymétrie…', 'info');
        const api = window.escrsAPI;
        const result = await api.calculer(params);
        if (result.success) {
            setStatus('✓ Données injectées — le médecin peut valider et calculer.', 'success');
        }
        else {
            setStatus(`✗ Erreur : ${result.error}`, 'error');
        }
    }
    catch (err) {
        setStatus(`✗ Erreur inattendue : ${err}`, 'error');
    }
    finally {
        btn.disabled = false;
    }
});

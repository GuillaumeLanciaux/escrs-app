/**
 * preload.ts — Bridge sécurisé entre main et renderer
 * Expose uniquement les APIs nécessaires via contextBridge.
 */

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('escrsAPI', {

  /**
   * Lance le calcul ESCRS pour un patient.
   * Appelle Python, ouvre le WebView ESCRS et injecte les données.
   */
  calculer: (params: Record<string, unknown>) =>
    ipcRenderer.invoke('calculer-escrs', params),

  /**
   * Lit le patient actuellement ouvert dans Microsoft Access via COM Interop.
   * Retourne { success, patient: { code, nom, prenom } | { code: null } }
   */
  getActivePatient: () =>
    ipcRenderer.invoke('get-active-patient'),

  /** Déclenche manuellement l'export PDF de la fenêtre ESCRS. */
  savePDF: () =>
    ipcRenderer.invoke('save-pdf'),

});
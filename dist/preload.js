"use strict";
/**
 * preload.ts — Bridge sécurisé entre main et renderer
 * Expose uniquement les APIs nécessaires via contextBridge.
 */
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('escrsAPI', {
    /**
     * Lance le calcul ESCRS pour un patient.
     * Appelle Python, ouvre le WebView ESCRS et injecte les données.
     */
    calculer: (params) => electron_1.ipcRenderer.invoke('calculer-escrs', params),
});

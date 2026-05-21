(async function injectESCRS(patient) {
  function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

  function setField(index, value) {
    if (value === null || value === undefined) return;
    const inputs = Array.from(document.querySelectorAll('input.mud-input-slot'));
    const input  = inputs[index];
    if (!input) { console.warn(`Input [${index}] non trouvé`); return; }
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, String(value));
    input.dispatchEvent(new Event('input',  { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.dispatchEvent(new Event('blur',   { bubbles: true }));
    console.log(`✓ [${index}] = ${value}`);
  }

  async function selectOption(selectIndex, optionText) {
    if (!optionText) return false;
    document.querySelector('.mud-overlay')?.click();
    await delay(300);
    const select = Array.from(document.querySelectorAll('.mud-select'))[selectIndex];
    if (!select) { console.warn(`Select [${selectIndex}] non trouvé`); return false; }
    const btn = select.querySelector('.mud-input-adornment button, [class*="mud-input"]');
    btn?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    btn?.click();
    await delay(700);
    const option = Array.from(document.querySelectorAll('.mud-list-item'))
                        .find(o => o.textContent.trim() === optionText);
    if (!option) {
      console.warn(`"${optionText}" non trouvé`);
      document.querySelector('.mud-overlay')?.click();
      return false;
    }
    option.click();
    await delay(800);
    console.log(`✓ "${optionText}"`);
    return true;
  }

  async function setSwitch(index, checked) {
    const sw = Array.from(document.querySelectorAll('.mud-switch'))[index];
    if (!sw) { console.warn(`Switch [${index}] non trouvé`); return; }
    const input = sw.querySelector('input[type="checkbox"]');
    if (!input) return;
    const isChecked = sw.classList.contains('mud-switch-base-checked') ||
                      sw.querySelector('.mud-switch-base-checked') !== null;
    if (isChecked === checked) return;
    sw.querySelector('.mud-button-root, label, .mud-switch-base')?.click();
    await delay(300);
    console.log(`✓ Switch [${index}] → ${checked}`);
  }

  async function setCheckbox(labelText, checked) {
    document.querySelector('.mud-overlay')?.click();
    await delay(200);
    const cbs = Array.from(document.querySelectorAll('.mud-checkbox'));
    const cb = cbs.find(c => c.textContent.trim() === labelText);
    if (!cb) { console.warn(`Checkbox "${labelText}" non trouvée`); return; }
    const input = cb.querySelector('input[type="checkbox"]');
    if (!input || input.checked === checked) return;
    cb.click();
    await delay(200);
    console.log(`✓ Checkbox "${labelText}" → ${checked}`);
  }

  function getOGOffset() {
    const inputs = Array.from(document.querySelectorAll('input.mud-input-slot'));
    const labels = inputs.map(inp =>
      inp.closest('.mud-input-control')?.querySelector('.mud-input-label')?.textContent?.trim()
    );
    let count = 0;
    for (let i = 0; i < labels.length; i++) {
      if (labels[i] === 'AL') { count++; if (count === 2) return i; }
    }
    return null;
  }

  const isToric     = patient.mode === 'toric';
  const isPostLasik = patient.mode === 'postlasik';
  const OD = patient.rightEye;
  const OG = patient.leftEye;

  // ÉTAPE 1 : modes
  if (isToric) {
    await setSwitch(0, true);
    await setSwitch(8, true);
    await delay(800);
  }
  if (isPostLasik) {
    await setSwitch(6, true);
    await setSwitch(14, true);
    await delay(800);
    await selectOption(2,  patient.postLasikType);
    await selectOption(10, patient.postLasikType);
  }

  // ÉTAPE 2 : commun
  setField(0, patient.surgeon);
  setField(1, patient.initials);
  setField(3, patient.age);
  await selectOption(0, patient.gender);

  // Index OD et OG (sauf toric)
  if (!isToric) {
    const allSelects = Array.from(document.querySelectorAll('.mud-select'));
    const indexSelects = allSelects.reduce((acc, s, i) => {
      if (s.querySelector('.mud-input-label')?.textContent?.trim() === 'Index') acc.push(i);
      return acc;
    }, []);
    if (indexSelects[0] !== undefined) await selectOption(indexSelects[0], patient.index ?? '1.3375');
    if (indexSelects[1] !== undefined) await selectOption(indexSelects[1], patient.index ?? '1.3375');
  }

  // ÉTAPE 3 : OD
  if (isToric) {
    setField(5,  OD.al);   setField(6,  OD.acd);
    setField(7,  OD.lt);   setField(8,  OD.cct);
    setField(9,  OD.wtw);  setField(10, OD.k1);
    setField(11, OD.k1axis); setField(12, OD.k2);
    setField(13, OD.k2axis); setField(14, OD.incision);
    setField(15, OD.sia);  setField(18, OD.targetRefraction);
    await selectOption(6, OD.manufacturer); await delay(1200);
    await selectOption(8, OD.iol);
  } else if (isPostLasik) {
    setField(6,  OD.al);   setField(7,  OD.acd);
    setField(8,  OD.lt);   setField(9,  OD.cct);
    setField(10, OD.wtw);  setField(11, OD.k1);
    setField(12, OD.k2);   setField(14, OD.targetRefraction);
    await selectOption(6, OD.manufacturer); await delay(1200);
    await selectOption(8, OD.iol);
  } else {
    setField(5,  OD.al);   setField(6,  OD.acd);
    setField(7,  OD.lt);   setField(8,  OD.cct);
    setField(9,  OD.wtw);  setField(10, OD.k1);
    setField(11, OD.k2);   setField(13, OD.targetRefraction);
    await selectOption(4, OD.manufacturer); await delay(1200);
    await selectOption(6, OD.iol);
  }

  // ÉTAPE 4 : OG offset dynamique
  await delay(1000);
  const og = getOGOffset();
  console.log(`OG offset: ${og}`);

  if (isToric) {
    setField(og,      OG.al);   setField(og + 1,  OG.acd);
    setField(og + 2,  OG.lt);   setField(og + 3,  OG.cct);
    setField(og + 4,  OG.wtw);  setField(og + 5,  OG.k1);
    setField(og + 6,  OG.k1axis); setField(og + 7, OG.k2);
    setField(og + 8,  OG.k2axis); setField(og + 9, OG.incision);
    setField(og + 10, OG.sia);  setField(og + 13, OG.targetRefraction);
    await selectOption(7, OG.manufacturer); await delay(1200);
    await selectOption(9, OG.iol);
  } else if (isPostLasik) {
    setField(og,     OG.al);   setField(og + 1, OG.acd);
    setField(og + 2, OG.lt);   setField(og + 3, OG.cct);
    setField(og + 4, OG.wtw);  setField(og + 5, OG.k1);
    setField(og + 6, OG.k2);   setField(og + 8, OG.targetRefraction);
    await selectOption(7, OG.manufacturer); await delay(1200);
    await selectOption(9, OG.iol);
  } else {
    setField(og,     OG.al);   setField(og + 1, OG.acd);
    setField(og + 2, OG.lt);   setField(og + 3, OG.cct);
    setField(og + 4, OG.wtw);  setField(og + 5, OG.k1);
    setField(og + 6, OG.k2);   setField(og + 8, OG.targetRefraction);
    await selectOption(5, OG.manufacturer); await delay(1200);
    await selectOption(7, OG.iol);
  }

  // ÉTAPE 5 : formules
  document.querySelector('.mud-overlay')?.click();
  await delay(800);
  for (const formula of (patient.formulas || [])) {
    await setCheckbox(formula, true);
  }

  console.log('\n✅ Injection ESCRS complète');

})({PATIENT_DATA});
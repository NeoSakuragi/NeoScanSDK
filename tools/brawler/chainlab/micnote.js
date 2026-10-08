// Note field with a microphone (Bruno's standard for every note box): a text box with the mic button on its right.
// The button shows its state by icon, label and shape (never colour alone, e-ink):
//   idle         microphone, "Speak"           tap to record
//   listening    square + timer, inverted      tap (or Esc) to stop; stops by itself after MAX_S seconds
//   transcribing hourglass, dashed border      audio sent to feedback-api/transcribe (OpenAI)
//   done         check mark, for 1.5 s         the text is appended to the box, 'input' fires so the page saves it
//   error        warning sign, "Retry"         the reason under the field (refused microphone, no audio, network...)
//   window.micNote(textarea) -> a wrapper holding the textarea and the button (put it where the textarea was)
(function () {
  const API = 'feedback-api/', MAX_S = 120;
  const ICONS = {
    idle: '<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" fill="none"/>',
    listening: '<rect x="6" y="6" width="12" height="12"/>',
    transcribing: '<path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9" fill="none"/>',
    done: '<path d="M4 12l5 5L20 6" fill="none"/>',
    error: '<path d="M12 3L2 21h20L12 3z" fill="none"/><path d="M12 10v5M12 18v.5" fill="none"/>'
  };
  const LABEL = { idle: 'Speak', listening: 'Stop', transcribing: 'Writing…', done: 'Added', error: 'Retry' };
  const ARIA = { idle: 'Dictate a note', listening: 'Stop recording', transcribing: 'Transcribing your note', done: 'Note added', error: 'Try dictating again' };
  if (!document.getElementById('micnote-css')) {
    const st = document.createElement('style'); st.id = 'micnote-css';
    st.textContent = `
.micfield { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: stretch; }
.micfield textarea { min-width: 0; width: 100%; box-sizing: border-box; min-height: 3.2em; resize: vertical; }
.micfield .micbtn { width: 70px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  font: inherit; font-size: 12px; font-weight: 700; background: #fff; color: #000; border: 2px solid #000; border-radius: 0; cursor: pointer; padding: 4px; }
.micfield .micbtn svg { width: 24px; height: 24px; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; fill: currentColor; }
.micfield .micbtn[data-state="listening"] { background: #000; color: #fff; }
.micfield .micbtn[data-state="transcribing"] { border-style: dashed; cursor: wait; }
.micfield .micbtn[data-state="error"] { border-width: 3px; }
.micfield .micbtn:focus-visible { outline: 3px dashed #000; outline-offset: 2px; }
.micfield .micmsg { grid-column: 1 / -1; font-size: 13px; min-height: 0; }
.micfield .micmsg:empty { display: none; }
@media (prefers-reduced-motion: no-preference) { .micfield .micbtn[data-state="listening"] svg { animation: micpulse 1s steps(2) infinite; } }
@keyframes micpulse { 50% { opacity: .35; } }`;
    document.head.append(st);
  }
  window.micNote = function (ta) {
    const wrap = document.createElement('div'); wrap.className = 'micfield';
    if (ta.parentNode) ta.parentNode.insertBefore(wrap, ta);
    const b = document.createElement('button'); b.type = 'button'; b.className = 'micbtn';
    const msg = document.createElement('div'); msg.className = 'micmsg'; msg.setAttribute('aria-live', 'polite');
    wrap.append(ta, b, msg);
    let state = 'idle', rec = null, stream = null, chunks = [], t0 = 0, tick = null, cancel = false;
    const set = (s, text) => {
      state = s; b.dataset.state = s; b.setAttribute('aria-label', ARIA[s]);
      const el = t0 ? Date.now() - t0 : 0;
      const lab = s === 'listening' ? `Stop ${Math.floor(el / 60000)}:${String(Math.floor(el / 1000) % 60).padStart(2, '0')}` : LABEL[s];
      b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[s]}</svg><span>${lab}</span>`;
      b.disabled = s === 'transcribing';
      if (text !== undefined) msg.textContent = text;
    };
    const fail = why => { cleanup(); set('error', why); };
    const cleanup = () => { clearInterval(tick); tick = null; if (stream) stream.getTracks().forEach(t => t.stop()); stream = null; };
    const stop = (c = false) => { cancel = c; if (rec && rec.state === 'recording') rec.stop(); };
    async function start() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) return fail('This browser cannot record here. Type the note instead.');
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (e) { return fail(e && e.name === 'NotAllowedError' ? 'The microphone is blocked for this page: allow it in the browser settings, then tap Retry.' : 'No microphone found.'); }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find(x => MediaRecorder.isTypeSupported(x)) || '';
      try { rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined); } catch (e) { return fail('Recording is not supported here.'); }
      chunks = []; cancel = false;
      rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onerror = () => fail('The recording stopped unexpectedly. Tap Retry.');
      rec.onstop = send;
      rec.start(250); t0 = Date.now(); set('listening', 'Listening… tap Stop when done (Esc cancels).');
      tick = setInterval(() => { if ((Date.now() - t0) / 1000 >= MAX_S) stop(); else set('listening'); }, 500);
    }
    async function send() {
      const secs = (Date.now() - t0) / 1000;
      cleanup();
      if (cancel) return set('idle', '');
      const blob = new Blob(chunks, { type: (rec && rec.mimeType) || 'audio/webm' });
      if (secs < 0.6 || blob.size < 1200) return fail('Nothing was recorded. Hold on a little longer.');
      const ext = /mp4/.test(blob.type) ? 'm4a' : /ogg/.test(blob.type) ? 'ogg' : 'webm';
      set('transcribing', 'Transcribing…');
      try {
        const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 125000);
        const r = await fetch(API + 'transcribe', { method: 'POST', credentials: 'same-origin', headers: { 'X-Audio-Name': 'audio.' + ext }, body: blob, signal: ctl.signal });
        clearTimeout(to);
        const j = await r.json().catch(() => ({}));
        if (r.status === 401) return fail('Signed out: sign in to the Lab again, then tap Retry.');
        if (!r.ok) return fail('Transcription failed (' + (j.error || 'HTTP ' + r.status) + '). Tap Retry.');
        const text = (j.text || '').trim();
        if (!text) return fail('No words were heard. Tap Retry and speak a little closer.');
        ta.value = (ta.value.trim() ? ta.value.replace(/\s*$/, '') + ' ' : '') + text;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        set('done', ''); setTimeout(() => { if (state === 'done') set('idle'); }, 1500);
      } catch (e) { fail(e && e.name === 'AbortError' ? 'The transcription took too long. Tap Retry.' : 'No connection to the transcription service. Tap Retry.'); }
    }
    b.onclick = () => { if (state === 'listening') stop(); else if (state !== 'transcribing') { msg.textContent = ''; start(); } };
    wrap.addEventListener('keydown', e => { if (e.key === 'Escape' && state === 'listening') { e.preventDefault(); stop(true); } });
    set('idle');
    wrap.micState = set;   // tests / pages: show a state (e.g. micState('error', 'reason'))
    return wrap;
  };
})();

// The microphone button every note field in the Lab gets (Bruno's standard): press to record, press again to stop;
// the audio goes to the feedback service's /api/transcribe (OpenAI, the same backend as the Player's voice notes) and
// the text is appended to the field, which then fires 'input' so the page saves it as if typed.
//   window.micNote(textarea)  -> the button (insert it next to the field)
(function () {
  const API = 'feedback-api/';
  window.micNote = function (ta) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'micbtn'; b.textContent = '● Speak'; b.setAttribute('aria-label', 'Dictate a note');
    let rec = null, chunks = [], stream = null;
    const label = t => { b.textContent = t; };
    b.onclick = async () => {
      if (rec && rec.state === 'recording') { rec.stop(); return; }
      if (!navigator.mediaDevices || !window.MediaRecorder) { label('No microphone here'); return; }
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (e) { label('Microphone refused'); return; }
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t)) || '';
      rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined); chunks = [];
      rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
        const ext = /mp4/.test(blob.type) ? 'm4a' : /ogg/.test(blob.type) ? 'ogg' : 'webm';
        label('Transcribing…'); b.disabled = true;
        try {
          const r = await fetch(API + 'transcribe', { method: 'POST', credentials: 'same-origin', headers: { 'X-Audio-Name': 'audio.' + ext }, body: blob });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || r.status);
          ta.value = (ta.value ? ta.value.replace(/\s*$/, '') + ' ' : '') + (j.text || '');
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          label('● Speak');
        } catch (e) { label('Transcription failed: ' + e.message); }
        b.disabled = false;
      };
      rec.start(); label('■ Stop (recording)');
    };
    return b;
  };
})();

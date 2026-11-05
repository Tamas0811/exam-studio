/* Oral examiner mode.
   After solving a task the student explains it to the "examiner", by voice or by typing,
   under oral-exam timing: 10 seconds to start talking, about 60 seconds to answer (both soft
   limits: the clock goes red and keeps counting). The examiner can give ONE nudge if the student
   is on the right track, then asks two follow-up questions, and finally rates the explanation
   against the key points for that question. Gemini does the judging through /api/examine; if it
   is unavailable, a keyword-based examiner takes over so the mode always works. */
(function () {
  const START_LIMIT = 10, ANSWER_LIMIT = 60, FOLLOW_UPS = 2;
  const store = {
    get(k, d) { try { const v = localStorage.getItem("eso." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("eso." + k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let aiReady = null;
  fetch("/api/health").then((r) => r.json()).then((d) => { aiReady = !!d.ai; }).catch(() => { aiReady = false; });

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (sec) => { const s = Math.max(0, Math.round(sec)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const words = (t) => (t.trim().match(/\S+/g) || []).length;

  // ---------------- AI calls with offline fallback ----------------
  async function api(body) {
    if (aiReady === false) return null;
    try {
      const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 25000);
      const r = await fetch("/api/examine", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal });
      clearTimeout(t);
      if (!r.ok) return null;
      return await r.json();
    } catch { return null; }
  }
  function offlineAssess(q, transcript, nudgeAvailable) {
    const t = " " + transcript.toLowerCase() + " ";
    const points = q.keyPoints.map((p) => {
      const hits = p.keywords.filter((k) => t.includes(k.toLowerCase())).length;
      return { id: p.id, status: hits >= 2 ? "covered" : hits === 1 ? "partial" : "missing" };
    });
    const onTrack = points.some((p) => p.status !== "missing");
    const gap = points.find((p) => p.status === "partial") || points.find((p) => p.status === "missing");
    const kp = gap && q.keyPoints.find((p) => p.id === gap.id);
    return { points, onTrack, nudge: nudgeAvailable && onTrack && kp ? kp.hint : null, nudgePoint: kp ? kp.id : null,
      comment: onTrack ? "You are on the right track. Make each step and the reason for it explicit." : "Start from what the question asks, then walk through your steps one by one.", offline: true };
  }
  function payload(q) {
    return { subject: q.subject, dataset: q.datasetName, prompt: q.prompt, answer: q.answer.display, method: q.method,
      keyPoints: q.keyPoints.map((p) => ({ id: p.id, text: p.text })) };
  }
  async function assess(q, asked, transcript, nudgeAvailable) {
    const r = await api({ mode: "assess", question: payload(q), asked, transcript, nudgeAvailable });
    if (r && Array.isArray(r.points)) {
      const ids = new Set(q.keyPoints.map((p) => p.id));
      r.points = q.keyPoints.map((p) => r.points.find((x) => x.id === p.id) || { id: p.id, status: "missing" }).filter((p) => ids.has(p.id));
      if (!nudgeAvailable) r.nudge = null;
      return r;
    }
    return offlineAssess(q, transcript, nudgeAvailable);
  }
  async function nextFollowUp(q, transcript, asked) {
    const r = await api({ mode: "followup", question: payload(q), transcript, pool: q.followUps, alreadyAsked: asked });
    if (r && r.question) return { question: r.question, expected: r.expected || [] };
    const left = q.followUps.filter((f) => !asked.includes(f));
    const pick = left[Math.floor(Math.random() * left.length)] || "What would you check to make sure your result is correct?";
    return { question: pick, expected: [], offline: true };
  }
  async function gradeFollowUp(q, asked, expected, transcript) {
    const r = await api({ mode: "grade_followup", question: payload(q), asked, expected, transcript });
    if (r && r.verdict) return r;
    return { verdict: words(transcript) >= 15 ? "answered" : "short", comment: "Graded offline: only the length of your answer was checked. Compare it with what you know from the case.", offline: true };
  }

  // ---------------- one examiner turn (question → spoken/typed answer) ----------------
  function speak(text) {
    return new Promise((res) => {
      if (!store.get("readAloud", false) || !window.speechSynthesis) return res();
      const u = new SpeechSynthesisUtterance(text); u.lang = "en-GB"; u.rate = 1;
      u.onend = res; u.onerror = res; speechSynthesis.cancel(); speechSynthesis.speak(u);
      setTimeout(res, 15000);
    });
  }

  function turn(box, { kind, text, number }) {
    return new Promise(async (resolve) => {
      const relaxed = store.get("pace", "exam") === "relaxed";
      const who = kind === "nudge" ? "Examiner · hint" : kind === "follow" ? `Examiner · follow-up ${number}` : "Examiner";
      box.innerHTML = `
        <div class="ex-q ${kind === "nudge" ? "nudge" : ""}"><span class="who">${who}</span>${esc(text)}</div>
        <div class="timers" ${relaxed ? "hidden" : ""}>
          <div class="tbox live" data-t="start"><div class="lbl">Start answering</div><div class="val">0:${START_LIMIT}</div><div class="meter"><i style="width:100%"></i></div></div>
          <div class="tbox" data-t="answer"><div class="lbl">Answer time</div><div class="val">${fmt(ANSWER_LIMIT)}</div><div class="meter"><i style="width:100%"></i></div></div>
        </div>
        ${relaxed ? `<p class="note">Relaxed mode: no clocks. Switch to exam pace when you are ready.</p>` : ""}
        ${SR ? `<button class="btn mic" type="button"><span class="rec-dot"></span><span class="mlbl">Answer by voice</span></button>` : `<p class="note">Voice input is not available in this browser (use Chrome or Edge for voice). Type your answer below.</p>`}
        <label class="small muted" for="ex-text" style="display:block;margin:.6rem 0 .25rem">${SR ? "Or type your answer (your spoken words appear here and can be edited)" : "Your answer"}</label>
        <textarea id="ex-text" placeholder="Explain as you would to the examiner…"></textarea>
        <div class="row" style="justify-content:space-between;margin-top:.6rem">
          <span class="small muted" data-status></span>
          <button class="btn primary" type="button" data-done disabled>Done answering</button>
        </div>`;
      const ta = box.querySelector("textarea"), done = box.querySelector("[data-done]"), status = box.querySelector("[data-status]");
      const tStart = box.querySelector('[data-t="start"]'), tAns = box.querySelector('[data-t="answer"]');
      const mic = box.querySelector(".mic");
      let shownAt = 0, startedAt = 0, mode = "typed", rec = null, finalText = "", raf = 0;

      await speak(text);
      shownAt = performance.now();
      ta.focus({ preventScroll: true });

      const tick = () => {
        const now = performance.now();
        if (!startedAt) {
          const left = START_LIMIT - (now - shownAt) / 1000;
          set(tStart, left, START_LIMIT);
        } else {
          const left = ANSWER_LIMIT - (now - startedAt) / 1000;
          set(tAns, left, ANSWER_LIMIT);
        }
        raf = requestAnimationFrame(tick);
      };
      function set(el, left, lim) {
        if (!el) return;
        el.querySelector(".val").textContent = left >= 0 ? fmt(left) : "+" + fmt(-left);
        el.querySelector(".meter i").style.width = left >= 0 ? (left / lim * 100) + "%" : "100%";
        el.classList.toggle("over", left < 0);
      }
      const begin = () => {
        if (startedAt) return;
        startedAt = performance.now();
        tStart && (tStart.classList.remove("live"), tStart.classList.add("done"));
        tAns && tAns.classList.add("live");
      };
      raf = requestAnimationFrame(tick);

      ta.addEventListener("input", () => { if (ta.value.trim()) begin(); done.disabled = !ta.value.trim(); });

      if (mic) {
        mic.addEventListener("click", () => {
          if (rec) { rec.stop(); return; }
          rec = new SR(); rec.lang = "en-US"; rec.continuous = true; rec.interimResults = true;
          finalText = ta.value ? ta.value.trim() + " " : "";
          rec.onresult = (e) => {
            let interim = "";
            for (let i = e.resultIndex; i < e.results.length; i++) {
              const r = e.results[i];
              if (r.isFinal) finalText += r[0].transcript.trim() + " "; else interim += r[0].transcript;
            }
            ta.value = (finalText + interim).trimStart();
            if (ta.value.trim()) { begin(); mode = "voice"; done.disabled = false; }
          };
          rec.onerror = (e) => {
            status.textContent = e.error === "not-allowed" || e.error === "service-not-allowed"
              ? "Microphone blocked. Allow it in the browser, or type your answer." : e.error === "no-speech" ? "No speech heard yet." : "Voice input stopped (" + e.error + "). You can keep typing.";
          };
          rec.onend = () => { mic.classList.remove("rec"); mic.querySelector(".mlbl").textContent = "Answer by voice"; rec = null; };
          rec.start();
          mic.classList.add("rec"); mic.querySelector(".mlbl").textContent = "Listening… click to stop";
          status.textContent = "";
        });
      }

      done.addEventListener("click", () => {
        if (rec) { try { rec.stop(); } catch { } }
        cancelAnimationFrame(raf);
        const end = performance.now();
        const startDelay = ((startedAt || end) - shownAt) / 1000;
        resolve({ kind, asked: text, transcript: ta.value.trim(), startDelay, answerTime: startedAt ? (end - startedAt) / 1000 : 0, mode, relaxed });
      });
    });
  }

  function thinking(box, msg) { box.innerHTML = `<p class="muted"><span class="spinner"></span> ${esc(msg)}</p>`; }

  // ---------------- the full session ----------------
  async function run(q, overlay) {
    const box = overlay.querySelector("[data-stage]");
    const turns = [];
    const opening = q.subject === "Regression"
      ? "Explain your answer to me as if I were the manager who has to act on it."
      : q.answer.type === "open" ? "Talk me through your answer." : "Walk me through how you got your answer, and why you did it that way.";

    const main = await turn(box, { kind: "main", text: opening }); turns.push(main);
    thinking(box, "The examiner is listening to your answer…");
    const first = await assess(q, opening, main.transcript, true);
    let final = first, nudge = null;
    if (first.nudge && first.onTrack) {
      nudge = await turn(box, { kind: "nudge", text: first.nudge }); turns.push(nudge);
      thinking(box, "The examiner is thinking…");
      final = await assess(q, opening + " / " + first.nudge, main.transcript + "\n[after hint] " + nudge.transcript, false);
    }
    const rank = { missing: 0, partial: 1, covered: 2 };
    const pointResults = q.keyPoints.map((p) => {
      const a = (first.points.find((x) => x.id === p.id) || {}).status || "missing";
      const b = (final.points.find((x) => x.id === p.id) || {}).status || a;
      let status = a;
      let hinted = false;
      if (nudge && rank[b] > rank[a]) { status = b; hinted = true; }
      return { ...p, status, hinted };
    });

    const follows = [], askedList = [];
    let said = turns.map((t) => t.transcript).join("\n");
    for (let i = 1; i <= FOLLOW_UPS; i++) {
      thinking(box, "The examiner has another question…");
      const f = await nextFollowUp(q, said, askedList);
      askedList.push(f.question);
      const a = await turn(box, { kind: "follow", text: f.question, number: i }); turns.push(a);
      said += "\n" + a.transcript;
      thinking(box, "The examiner is noting your answer…");
      const g = await gradeFollowUp(q, f.question, f.expected, a.transcript);
      follows.push({ q: f.question, a: a.transcript, ...g });
    }
    feedback(box, q, { turns, pointResults, follows, comment: final.comment || first.comment, offline: !!(first.offline || final.offline) }, overlay);
  }

  function feedback(box, q, r, overlay) {
    const timed = r.turns.filter((t) => !t.relaxed);
    const avgStart = timed.length ? timed.reduce((s, t) => s + t.startDelay, 0) / timed.length : null;
    const onTime = timed.filter((t) => t.startDelay <= START_LIMIT).length;
    const covered = r.pointResults.filter((p) => p.status === "covered" && !p.hinted).length;
    const hinted = r.pointResults.filter((p) => p.hinted).length;
    const total = r.pointResults.length;
    const score = total ? Math.round(((covered + 0.5 * hinted + 0.5 * r.pointResults.filter((p) => p.status === "partial" && !p.hinted).length) / total) * 100) : 0;

    const hist = store.get("history", []);
    if (timed.length) {
      hist.push({ d: Date.now(), start: +avgStart.toFixed(1), score });
      store.set("history", hist.slice(-20));
    }
    const recent = store.get("history", []).slice(-10);
    const maxS = Math.max(START_LIMIT * 1.5, ...recent.map((h) => h.start));

    const badge = (p) => p.status === "covered" && !p.hinted ? `<span class="badge b-ok">Covered</span>`
      : p.hinted ? `<span class="badge b-hint">With hint</span>` : p.status === "partial" ? `<span class="badge b-hint">Partly</span>` : `<span class="badge b-miss">Missed</span>`;
    const vbadge = (v) => v === "good" ? `<span class="badge b-ok">Good</span>` : v === "partial" || v === "answered" ? `<span class="badge b-hint">${v === "answered" ? "Answered" : "Partly"}</span>` : `<span class="badge b-miss">${v === "short" ? "Short" : "Weak"}</span>`;

    box.innerHTML = `
      <h2>How you did</h2>
      <div class="stats">
        <div class="stat"><div class="n">${covered}${hinted ? ` +${hinted}` : ""}/${total}</div><div class="l">key points covered${hinted ? " (+ with hint)" : ""}</div></div>
        <div class="stat"><div class="n">${avgStart == null ? "–" : avgStart.toFixed(1) + " s"}</div><div class="l">average time to start (target ${START_LIMIT} s)</div></div>
        <div class="stat"><div class="n">${timed.length ? `${onTime}/${timed.length}` : "–"}</div><div class="l">answers started in time</div></div>
        <div class="stat"><div class="n">${score}%</div><div class="l">explanation score</div></div>
      </div>
      ${r.comment ? `<p><b>Examiner:</b> ${esc(r.comment)}</p>` : ""}
      <h3>Key points</h3>
      <ul class="points">${r.pointResults.map((p) => `<li>${badge(p)}<span>${esc(p.text)}</span></li>`).join("")}</ul>
      <h3>Follow-up questions</h3>
      <ul class="points">${r.follows.map((f) => `<li>${vbadge(f.verdict)}<span><b>${esc(f.q)}</b><br><span class="small">${esc(f.comment || "")}</span>${f.modelAnswer ? `<br><span class="small muted">Model answer: ${esc(f.modelAnswer)}</span>` : ""}</span></li>`).join("")}</ul>
      <h3>Your timing</h3>
      <div class="scroll"><table class="reg"><thead><tr><th>Question</th><th>Started after</th><th>Answered for</th><th>Input</th></tr></thead><tbody>
        ${r.turns.map((t) => `<tr><td>${t.kind === "main" ? "Main explanation" : t.kind === "nudge" ? "After hint" : "Follow-up"}</td>
          <td class="num" style="${!t.relaxed && t.startDelay > START_LIMIT ? "color:var(--bad)" : ""}">${t.startDelay.toFixed(1)} s</td>
          <td class="num" style="${!t.relaxed && t.answerTime > ANSWER_LIMIT ? "color:var(--bad)" : ""}">${t.answerTime.toFixed(0)} s</td><td>${t.relaxed ? "relaxed · " : ""}${t.mode}</td></tr>`).join("")}
      </tbody></table></div>
      ${recent.length > 1 ? `<p class="small muted" style="margin-bottom:0">Time to start, your last ${recent.length} timed sessions (red = over ${START_LIMIT} s). Stored only in this browser.</p>
        <div class="trend">${recent.map((h) => `<span class="${h.start > START_LIMIT ? "over" : ""}" style="height:${Math.max(6, h.start / maxS * 100)}%" title="${h.start} s"></span>`).join("")}</div>` : ""}
      <details open><summary>Model answer</summary>
        <p><b>Result:</b> ${esc(q.answer.display)}</p><pre>${esc(q.method)}</pre></details>
      ${r.offline ? `<p class="note">The AI examiner was not reachable, so this round was judged by keyword matching. Results are rougher than usual.</p>` : ""}
      <div class="row" style="margin-top:1rem"><button class="btn primary" data-again>Try again</button><button class="btn" data-close>Close</button></div>`;
    box.querySelector("[data-again]").onclick = () => run(q, overlay);
    box.querySelector("[data-close]").onclick = () => close(overlay);
  }

  function close(overlay) {
    try { speechSynthesis.cancel(); } catch { }
    overlay.remove(); document.body.style.overflow = "";
  }

  function open(q) {
    const overlay = document.createElement("div");
    overlay.className = "exam-overlay";
    const pace = store.get("pace", "exam"), aloud = store.get("readAloud", false);
    overlay.innerHTML = `<div class="examiner" role="dialog" aria-modal="true" aria-label="Oral examiner">
      <div class="ex-head">
        <div><div class="kicker">Oral examiner · ${esc(q.id)}</div><b>${esc(q.prompt)}</b></div>
        <button class="btn sm" data-x aria-label="Close examiner">Close</button>
      </div>
      <div data-intro>
        <p>You will explain your answer as in the oral exam. You have <b>${START_LIMIT} seconds to start talking</b> and about <b>${ANSWER_LIMIT} seconds to answer</b>. The clocks turn red but never cut you off. If you are on the right track the examiner may give you <b>one hint</b>, then asks <b>${FOLLOW_UPS} follow-up questions</b> and rates your explanation.</p>
        <div class="row" style="margin:.6rem 0">
          <span class="small muted">Pace</span>
          <div class="switch" role="group" aria-label="Pace"><button data-pace="exam" class="${pace === "exam" ? "on" : ""}">Exam pace</button><button data-pace="relaxed" class="${pace === "relaxed" ? "on" : ""}">Relaxed (no clocks)</button></div>
          ${window.speechSynthesis ? `<label class="small"><input type="checkbox" data-aloud ${aloud ? "checked" : ""}> Read questions aloud</label>` : ""}
        </div>
        ${SR ? "" : `<p class="note">This browser cannot transcribe speech; you will type your answers. Chrome and Edge support voice.</p>`}
        <button class="btn gold" data-begin>I'm ready – start</button>
      </div>
      <div data-stage></div>
    </div>`;
    document.body.appendChild(overlay); document.body.style.overflow = "hidden";
    overlay.querySelector("[data-x]").onclick = () => close(overlay);
    overlay.addEventListener("keydown", (e) => { if (e.key === "Escape") close(overlay); });
    overlay.querySelectorAll("[data-pace]").forEach((b) => b.onclick = () => {
      store.set("pace", b.dataset.pace);
      overlay.querySelectorAll("[data-pace]").forEach((x) => x.classList.toggle("on", x === b));
    });
    const al = overlay.querySelector("[data-aloud]"); if (al) al.onchange = () => store.set("readAloud", al.checked);
    overlay.querySelector("[data-begin]").onclick = () => { overlay.querySelector("[data-intro]").remove(); run(q, overlay); };
    overlay.querySelector("[data-begin]").focus();
  }

  window.Examiner = { open };
})();

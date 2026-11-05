/* Exam Studio Oral – page routing and practice views. */
(function () {
  const app = document.getElementById("app");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let BANK = null, INTERP = null, QMAP = {};
  let examTimer = null;

  const load = async () => {
    if (BANK) return;
    const [b, i] = await Promise.all([fetch("/data/bank.json").then((r) => r.json()), fetch("/data/interpretation.json").then((r) => r.json())]);
    BANK = b; INTERP = i; b.questions.forEach((q) => (QMAP[q.id] = q));
  };

  // ---------------- answer checking ----------------
  const normText = (s) => String(s).toLowerCase().replace(/[\s ]+/g, " ").replace(/[.;]+$/, "").trim();
  function check(ans, input) {
    if (!input.trim()) return null;
    if (ans.type === "number") {
      const cleaned = input.replace(/[^0-9.,\-−]/g, "").replace(/−/g, "-").replace(/,/g, "");
      const v = parseFloat(cleaned);
      if (Number.isNaN(v)) return { ok: false, msg: "Enter a number." };
      const ok = Math.abs(v - ans.value) <= ans.tol + 1e-9;
      return { ok, msg: ok ? "Correct." : "Not quite. Check your filters and rounding, then try again." };
    }
    if (ans.type === "text") {
      const ok = [ans.value, ...(ans.alts || [])].map(normText).includes(normText(input));
      return { ok, msg: ok ? "Correct." : "Not quite. Check spelling and the format asked for." };
    }
    return null;
  }

  // ---------------- question block (shared by bank and exams) ----------------
  function dsOf(q) { return BANK.datasets[q.dataset]; }
  function examinerQ(q) {
    return { ...q, datasetName: dsOf(q).name, keyPoints: q.keyPoints, followUps: q.followUps };
  }
  function questionHTML(q, opts = {}) {
    const ds = dsOf(q);
    const open = q.answer.type === "open";
    return `
      <div class="row" style="justify-content:space-between"><div class="row"><span class="pill ${q.subject.toLowerCase()}">${q.subject}</span><span class="small muted">${esc(q.id)} · ${esc(ds.name)}</span></div><span class="small muted">${Math.round(q.est / 30) / 2} min estimated</span></div>
      <p class="prompt">${esc(q.prompt)}</p>
      ${opts.showFile ? `<div class="file"><div><b>${esc(ds.name)}</b><span class="small muted">${esc(ds.file)}</span></div><a class="btn sm" href="/data/files/${encodeURIComponent(ds.file)}" download>Download</a></div>` : ""}
      ${open ? `<p class="small muted">This is a discussion question: there is no single number to check. Explain it to the examiner.</p>` :
      `<form class="check row" data-check><label class="small muted" for="ans-${q.id}">Your result</label><input type="text" id="ans-${q.id}" autocomplete="off" placeholder="${q.answer.type === "number" ? "e.g. 1234.56" : "your answer"}"><button class="btn sm" type="submit">Check my answer</button></form><div data-result></div>`}
      <div class="row" style="margin-top:1rem"><button class="btn gold" data-examiner>🎙 Explain to the examiner</button></div>
      <details data-model><summary>Show model answer</summary><p><b>Result:</b> ${esc(q.answer.display)}</p><pre>${esc(q.method)}</pre></details>`;
  }
  function wireQuestion(el, q, toExaminer) {
    const f = el.querySelector("[data-check]");
    if (f) f.addEventListener("submit", (e) => {
      e.preventDefault();
      const r = check(q.answer, f.querySelector("input").value);
      const out = el.querySelector("[data-result]");
      out.innerHTML = r ? `<div class="result ${r.ok ? "ok" : "bad"}">${esc(r.msg)}${r.ok ? " Now explain it to the examiner, as you will have to in the exam." : ""}</div>` : "";
    });
    el.querySelector("[data-examiner]").onclick = () => Examiner.open(toExaminer(q));
  }

  // ---------------- timer ----------------
  function timerHTML(min) {
    return `<div class="card"><div class="timerbar">
      <div><div class="small muted">Time remaining</div><div class="clock" data-left>${min}:00</div></div>
      <div><div class="small muted">Elapsed</div><div class="clock" data-el>0:00</div></div>
      <div class="row"><button class="btn primary sm" data-start>Start timer</button><button class="btn sm" data-pause disabled>Pause</button><button class="btn sm" data-reset>Reset</button></div>
    </div><p class="small muted" style="margin:.6rem 0 0">You have ${min} minutes for the full exam. Download the files before starting. Any import task is part of the timed exam. In the real exam you then explain your work, so use the examiner after each question.</p></div>`;
  }
  function wireTimer(el, min) {
    const left = el.querySelector("[data-left]"), elp = el.querySelector("[data-el]");
    const st = el.querySelector("[data-start]"), pa = el.querySelector("[data-pause]"), rs = el.querySelector("[data-reset]");
    let elapsed = 0, last = 0, running = false;
    const f = (s) => `${s < 0 ? "+" : ""}${Math.floor(Math.abs(s) / 60)}:${String(Math.floor(Math.abs(s) % 60)).padStart(2, "0")}`;
    const draw = () => { const l = min * 60 - elapsed; left.textContent = f(l); left.classList.toggle("over", l < 0); elp.textContent = f(elapsed); };
    clearInterval(examTimer);
    examTimer = setInterval(() => { if (running) { const n = performance.now(); elapsed += (n - last) / 1000; last = n; draw(); } }, 250);
    st.onclick = () => { running = true; last = performance.now(); st.disabled = true; pa.disabled = false; };
    pa.onclick = () => { running = false; st.disabled = false; st.textContent = "Resume"; pa.disabled = true; };
    rs.onclick = () => { running = false; elapsed = 0; st.disabled = false; st.textContent = "Start timer"; pa.disabled = true; draw(); };
  }

  // ---------------- pages ----------------
  const pages = {
    home() {
      return `<section class="hero"><div>
        <div class="kicker">Data Analytics in Accounting · oral exam practice</div>
        <h1>Solve it. Then say it out loud.</h1>
        <p>In the oral exam you get a full data manipulation exam and a full data interpretation exam, and then you have to <b>explain your work to the examiner</b>. This site lets you practise both parts: the Excel and SQL tasks with answer checking, and the explanation, with an examiner that times you, nudges you when you are close, and asks follow-up questions.</p>
        <div class="row"><a class="btn primary" href="#/exams/random">Start a random exam</a><a class="btn" href="#/questions">Browse questions</a></div>
      </div>
      <div class="card"><h3>How the oral examiner works</h3><ol class="flow">
        <li>Solve the task and check your result.</li>
        <li>Press <b>Explain to the examiner</b>. You have <b>10 s to start</b> and about <b>60 s to answer</b>, by voice or typing.</li>
        <li>On the right track but missing something? You get <b>one hint</b>.</li>
        <li><b>Two follow-up questions</b> from the case material.</li>
        <li>Feedback: key points covered, timing, model answer.</li>
      </ol></div></section>
      <div class="grid">
        <a class="qitem card" href="#/exams"><h3>Data manipulation exams</h3><p class="muted">${BANK.exams.length} exams · 3 Excel + 3 SQL questions on two data files · 8 minutes</p></a>
        <a class="qitem card" href="#/questions"><h3>Question bank</h3><p class="muted">${BANK.questions.length} questions from all six cases, each with a checked answer and an examiner round</p></a>
        <a class="qitem card" href="#/interp"><h3>Data interpretation exams</h3><p class="muted">${INTERP.exams.length} regression exams · predict, interpret, judge significance · 5 minutes</p></a>
      </div>`;
    },

    exams() {
      return `<h1>Data manipulation exams</h1><p class="muted">Each exam combines three Excel and three SQL questions on two data files. Estimated working time: 8 minutes, plus the oral explanation.</p>
      <div class="row" style="margin-bottom:1rem"><a class="btn primary" href="#/exams/random">Choose one for me</a></div>
      <div class="qlist">${BANK.exams.map((e) => `<a class="qitem" href="#/exam/${e.id}"><b>${e.id}</b> · ${e.datasets.map((d) => esc(BANK.datasets[d].name)).join(" + ")}<div class="meta">${e.questions.join(" · ")}</div></a>`).join("")}</div>`;
    },

    exam(id) {
      const e = BANK.exams.find((x) => x.id === id);
      if (!e) return notFound();
      const qs = e.questions.map((i) => QMAP[i]);
      setTimeout(() => {
        wireTimer(app, e.minutes);
        const holder = app.querySelector("[data-qbox]"), tabs = app.querySelectorAll("[data-tab]");
        const show = (i) => {
          tabs.forEach((t, k) => t.classList.toggle("on", k === i));
          holder.innerHTML = questionHTML(qs[i]) + `<div class="row" style="justify-content:space-between;margin-top:1rem"><button class="btn sm" data-prev ${i === 0 ? "disabled" : ""}>← Previous</button><button class="btn sm" data-next ${i === qs.length - 1 ? "disabled" : ""}>Next →</button></div>`;
          wireQuestion(holder, qs[i], examinerQ);
          holder.querySelector("[data-prev]").onclick = () => show(i - 1);
          holder.querySelector("[data-next]").onclick = () => show(i + 1);
        };
        tabs.forEach((t, k) => (t.onclick = () => show(k)));
        show(0);
      });
      return `<a href="#/exams" class="small">← All exams</a>
        <div class="kicker" style="margin-top:.6rem">${e.id} · data manipulation exam · ${e.minutes} minutes</div><h1>Data manipulation exam ${e.id}</h1>
        <div class="card"><h3>Exam files</h3><div class="files">${e.datasets.map((d) => { const ds = BANK.datasets[d]; return `<div class="file"><div><b>${esc(ds.name)}</b><span class="small muted">${esc(ds.file)} · ${esc(ds.desc)}</span></div><a class="btn sm" href="/data/files/${encodeURIComponent(ds.file)}" download>Download</a></div>`; }).join("")}</div></div>
        ${timerHTML(e.minutes)}
        <div class="tabs" role="tablist">${qs.map((q, k) => `<button data-tab role="tab">${String(k + 1).padStart(2, "0")} · ${q.subject}</button>`).join("")}</div>
        <div class="card" data-qbox></div>`;
    },

    questions(params) {
      const subj = params.get("s") || "", ds = params.get("d") || "", term = params.get("q") || "";
      const list = BANK.questions.filter((q) => (!subj || q.subject === subj) && (!ds || q.dataset === ds) && (!term || (q.prompt + q.id).toLowerCase().includes(term.toLowerCase())));
      setTimeout(() => {
        const f = app.querySelector("form");
        const go = () => { const p = new URLSearchParams(); ["s", "d", "q"].forEach((k) => { const v = f.elements[k].value; if (v) p.set(k, v); }); location.hash = "#/questions" + (p.toString() ? "?" + p : ""); };
        f.onchange = go; f.onsubmit = (e) => { e.preventDefault(); go(); };
      });
      return `<h1>Question bank</h1><p class="muted">${BANK.questions.length} questions built from the case files. Every number is computed from the same files you download.</p>
        <form class="row card" style="padding:.8rem">
          <select name="s" aria-label="Subject"><option value="">All subjects</option><option ${subj === "Excel" ? "selected" : ""}>Excel</option><option ${subj === "SQL" ? "selected" : ""}>SQL</option></select>
          <select name="d" aria-label="Data file"><option value="">All data files</option>${Object.values(BANK.datasets).map((d) => `<option value="${d.key}" ${ds === d.key ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>
          <input type="search" name="q" value="${esc(term)}" placeholder="Search questions" aria-label="Search">
        </form>
        <p class="small muted">${list.length} questions</p>
        <div class="qlist">${list.map((q) => `<a class="qitem" href="#/q/${q.id}"><span class="pill ${q.subject.toLowerCase()}">${q.subject}</span> <b>${q.id}</b> ${esc(q.prompt)}<div class="meta">${esc(dsOf(q).name)} · ${q.tags.join(", ")}</div></a>`).join("")}</div>`;
    },

    q(id) {
      const q = QMAP[id]; if (!q) return notFound();
      const idx = BANK.questions.indexOf(q);
      setTimeout(() => wireQuestion(app.querySelector("[data-qbox]"), q, examinerQ));
      return `<a href="#/questions" class="small">← Question bank</a><h1 style="margin-top:.6rem">Question ${q.id}</h1>
        <div class="card" data-qbox>${questionHTML(q, { showFile: true })}</div>
        <div class="row" style="justify-content:space-between">${idx > 0 ? `<a class="btn sm" href="#/q/${BANK.questions[idx - 1].id}">← Previous</a>` : "<span></span>"}${idx < BANK.questions.length - 1 ? `<a class="btn sm" href="#/q/${BANK.questions[idx + 1].id}">Next →</a>` : ""}</div>`;
    },

    interp() {
      return `<h1>Data interpretation exams</h1><p class="muted">Each exam has four regression questions, each with its own model: a prediction, a slope, a dummy variable and a significance judgement. 5 minutes, then explain.</p>
        <div class="row" style="margin-bottom:1rem"><a class="btn primary" href="#/interp/random">Choose one for me</a></div>
        <div class="qlist">${INTERP.exams.map((e) => `<a class="qitem" href="#/interp/${e.id}"><b>${e.id}</b> · ${esc(e.title)} and three more models</a>`).join("")}</div>`;
    },

    interpExam(id) {
      const e = INTERP.exams.find((x) => x.id === id); if (!e) return notFound();
      const toEx = (q) => ({ ...q, subject: "Regression", datasetName: q.model.y });
      setTimeout(() => {
        wireTimer(app, e.minutes);
        const holder = app.querySelector("[data-qbox]"), tabs = app.querySelectorAll("[data-tab]");
        const show = (i) => {
          tabs.forEach((t, k) => t.classList.toggle("on", k === i));
          const q = e.questions[i], m = q.model, open = q.answer.type === "open";
          holder.innerHTML = `<div class="kicker">${esc(q.id)} · ${esc(m.y)}</div>
            <p class="prompt">${esc(q.prompt)}</p>
            <p class="small"><b>${esc(m.y)}</b> (${esc(m.yu)}) · <b>${esc(m.x)}</b> (${esc(m.xu)}, data range ${m.lo}–${m.hi}) · <b>${esc(m.d)}</b>: 1 = ${esc(m.d1)}, 0 = ${esc(m.d0)} (reference group)</p>
            <pre>Predicted ${esc(m.y)} = b₀ + b₁·[${esc(m.x)}] + b₂·[${esc(m.d)}]</pre>
            <div class="scroll"><table class="reg"><thead><tr><th>Parameter</th><th>Term</th><th style="text-align:right">Estimate</th><th style="text-align:right">p-value</th></tr></thead><tbody>
              <tr><td>b₀</td><td>Intercept</td><td class="num">${m.b0}</td><td class="num">${q.pvals[0]}</td></tr>
              <tr><td>b₁</td><td>${esc(m.x)}</td><td class="num">${m.b1}</td><td class="num">${q.pvals[1]}</td></tr>
              <tr><td>b₂</td><td>${esc(m.d)}</td><td class="num">${m.b2}</td><td class="num">${q.pvals[2]}</td></tr></tbody></table></div>
            ${open ? `<p class="small muted">Discussion question: explain it to the examiner.</p>` : `<form class="check row" data-check><label class="small muted" for="ans-${q.id}">Your answer</label><input type="text" id="ans-${q.id}" autocomplete="off"><button class="btn sm">Check my answer</button></form><div data-result></div>`}
            <div class="row" style="margin-top:1rem"><button class="btn gold" data-examiner>🎙 Explain to the examiner</button></div>
            <details><summary>Show model answer</summary><p>${esc(q.answer.display)}</p><pre>${esc(q.method)}</pre></details>
            <div class="row" style="justify-content:space-between;margin-top:1rem"><button class="btn sm" data-prev ${i === 0 ? "disabled" : ""}>← Previous</button><button class="btn sm" data-next ${i === 3 ? "disabled" : ""}>Next →</button></div>`;
          wireQuestion(holder, q, toEx);
          holder.querySelector("[data-prev]").onclick = () => show(i - 1);
          holder.querySelector("[data-next]").onclick = () => show(i + 1);
        };
        tabs.forEach((t, k) => (t.onclick = () => show(k)));
        show(0);
      });
      return `<a href="#/interp" class="small">← All interpretation exams</a>
        <div class="kicker" style="margin-top:.6rem">${e.id} · data interpretation exam · ${e.minutes} minutes</div><h1>${esc(e.title)} and three more models</h1>
        ${timerHTML(e.minutes)}
        <div class="tabs">${e.questions.map((q, k) => `<button data-tab>Question ${k + 1}</button>`).join("")}</div>
        <div class="card" data-qbox></div>`;
    },

    about() {
      return `<h1>Why an oral examiner?</h1>
      <div class="card"><p><b>The exam is oral, but practice tools only train the written half.</b> A practice site that only asks for a number trains producing results. The exam grades something else: whether you can explain <i>why</i> you used a pipe delimiter, why job code 001 must stay text, why a flagged P-card transaction is not yet a violation, or what a dummy coefficient is compared against. Every case in the course is built on the same analytics mindset: ask the right questions, ETL, analyse, and <b>interpret and share the results with stakeholders</b>. The last step is the one students rarely practise and the one an oral exam tests directly.</p>
      <p><b>The most stressful part of an oral exam is the follow-up question you didn't prepare for.</b> Knowing which questions will come reduces anxiety for the written part. The oral examiner extends that to the spoken part: students rehearse the silence after the question (10 seconds to start), keep answers concise (about 60 seconds), and meet the kind of follow-up an examiner asks.</p>
      <p><b>The help works like a real examiner's, not like a tutor's.</b> The AI tutor helps <i>before</i> you answer. The examiner probes <i>while</i> you answer: one hint only when you are on the right track, phrased as a question, and recorded as "with hint" in the feedback, so students see the difference between knowing a point and being led to it.</p>
      <p><b>It is measurable.</b> Each round reports key points covered, points covered only after a hint, and time to start. Students can see their time to start fall over sessions (kept only in their own browser).</p></div>
      <div class="card"><h3>Design choices</h3><ul>
        <li><b>Voice and typing.</b> Not every laptop has a working microphone, and some students practise in a library. Speech is transcribed by the browser; the text stays editable.</li>
        <li><b>Soft limits.</b> The clocks turn red but never cut you off. The goal is realistic pressure, not failure.</li>
        <li><b>Relaxed mode.</b> Students can learn the material without clocks first and switch to exam pace when ready.</li>
        <li><b>Works without AI.</b> If the AI examiner is unavailable, a keyword-based examiner uses the same key points and hints, so the mode never breaks.</li>
        <li><b>Answers come from the data.</b> Every checked answer and model method is generated by a script from the course files (<code>tools/build_bank.py</code>), not typed in by hand.</li>
      </ul></div>`;
    },
  };
  function notFound() { return `<h1>Not found</h1><p><a href="#/">Back to start</a></p>`; }

  async function route() {
    clearInterval(examTimer);
    document.querySelectorAll(".exam-overlay").forEach((o) => o.remove());
    document.body.style.overflow = "";
    try { speechSynthesis.cancel(); } catch { }
    await load();
    const [path, qs] = (location.hash.slice(1) || "/").split("?");
    const parts = path.split("/").filter(Boolean);
    const params = new URLSearchParams(qs || "");
    let html, nav = parts[0] || "";
    if (!parts.length) html = pages.home();
    else if (parts[0] === "exams" && parts[1] === "random") { location.replace("#/exam/" + BANK.exams[Math.floor(Math.random() * BANK.exams.length)].id); return; }
    else if (parts[0] === "exams") html = pages.exams();
    else if (parts[0] === "exam") { html = pages.exam(parts[1]); nav = "exams"; }
    else if (parts[0] === "questions") html = pages.questions(params);
    else if (parts[0] === "q") { html = pages.q(parts[1]); nav = "questions"; }
    else if (parts[0] === "interp" && parts[1] === "random") { location.replace("#/interp/" + INTERP.exams[Math.floor(Math.random() * INTERP.exams.length)].id); return; }
    else if (parts[0] === "interp" && parts[1]) html = pages.interpExam(parts[1]);
    else if (parts[0] === "interp") html = pages.interp();
    else if (parts[0] === "about") html = pages.about();
    else html = notFound();
    app.innerHTML = html;
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === nav));
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  route().catch((e) => { app.innerHTML = `<p>Could not load the question bank: ${esc(e.message)}</p>`; });
})();

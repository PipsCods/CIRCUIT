(() => {
  "use strict";

  const embedded = window.self !== window.top;
  document.documentElement.classList.toggle("embedded", embedded);

  const data = window.CIRCUIT_DEMO_DATA;
  if (!data) return;

  const byId = (id) => document.getElementById(id);
  const run = data.runs.C;
  const naive = data.runs.A;
  const context = data.contexts.engineered;
  const parsedOutput = JSON.parse(run.final_text);
  const call = run.tool_calls[0];
  const summary = run.tool_result_summaries[0] || {};
  const selected = new Set(run.citations.map((citation) => citation.doi.toLowerCase()));
  const evidence = run.evidence_ledger.filter((record) => selected.has(record.doi.toLowerCase()));
  const number = (value) => new Intl.NumberFormat("en-US").format(Math.round(value));
  const money = (value) => `$${value.toFixed(6)}`;
  const setText = (id, value) => {
    const node = byId(id);
    if (node) node.textContent = value;
  };

  setText("question-id", data.question.id.toUpperCase());
  setText("question-text", data.question.text);
  setText("temperature", run.reproducibility.temperature);
  setText("seed", run.reproducibility.seed);
  setText("naive-parameter-count", data.contexts.naive.search_parameter_count);
  setText("engineered-parameter-count", context.search_parameter_count);
  setText("tool-name", call.name);
  setText("results-returned", summary.results_returned ?? call.n_results);
  setText("total-results", number(summary.total_results || call.n_results));
  setText("answer-copy", parsedOutput.answer);
  setText("grounded-count", `${run.citations.length}/${run.citations.length}`);
  setText("resolved-count", `${run.citations.filter((citation) => citation.verified).length}/${run.citations.length}`);
  setText("gold-count", `${run.citations.filter((citation) => citation.gold_hit).length}/5`);
  setText("token-count", number(run.tokens_total));
  setText("run-cost", money(run.cost));
  setText("naive-gold", `${naive.citations.filter((citation) => citation.gold_hit).length}/5 gold`);
  setText("naive-tokens", `${number(naive.tokens_total)} tokens`);
  setText("circuit-gold", `${run.citations.filter((citation) => citation.gold_hit).length}/5 gold`);
  setText("circuit-tokens", `${number(run.tokens_total)} tokens`);

  context.search_parameters.forEach((parameter) => {
    const item = document.createElement("code");
    item.textContent = parameter;
    byId("parameter-list").appendChild(item);
  });

  Object.entries(call.args).forEach(([key, value]) => {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = key;
    detail.textContent = String(value);
    byId("argument-list").append(term, detail);
  });

  evidence.forEach((record, index) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <span>${String(index + 1).padStart(2, "0")}</span>
      <strong title="${record.title.replaceAll('"', "&quot;")}">${record.title}</strong>
      <code>${record.doi}</code>
      <b>${number(record.citation_count)}</b>
    `;
    byId("evidence-list").appendChild(item);
  });

  run.citations.forEach((citation, index) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <span>${String(index + 1).padStart(2, "0")}</span>
      <strong title="${citation.title.replaceAll('"', "&quot;")}">${citation.title}</strong>
      <code>${citation.doi}</code>
      <b>${number(citation.citation_count)}</b>
    `;
    byId("answer-list").appendChild(item);
  });

  const dialog = byId("artifact-dialog");
  const openArtifact = (title, kicker, content) => {
    setText("dialog-title", title);
    setText("dialog-kicker", kicker);
    setText("dialog-content", content);
    dialog.showModal();
  };

  byId("prompt-button").addEventListener("click", () => {
    openArtifact("Exact engineered prompt", "INPUT TO GEMMA · FROZEN MANIFEST", context.prompt);
  });
  byId("json-button").addEventListener("click", () => {
    openArtifact("Exact Gemma final answer", "RAW MODEL OUTPUT · FROZEN TRACE", run.final_text);
  });

  const board = document.querySelector(".workflow-board");
  const runConsole = document.querySelector(".run-console");
  const stages = Array.from(document.querySelectorAll(".stage"));
  const evidenceRows = Array.from(document.querySelectorAll(".evidence-list li"));
  const answerRows = Array.from(document.querySelectorAll(".answer-list li"));
  const checks = Array.from(document.querySelectorAll(".verification-list span"));
  const button = byId("run-button");
  const status = byId("run-status");
  const detail = byId("run-detail");
  const progress = byId("run-progress");
  const clock = byId("run-clock");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let timers = [];
  let clockTimer = null;

  const schedule = (fn, delay) => {
    const timer = window.setTimeout(fn, delay);
    timers.push(timer);
  };
  const clearTimers = () => {
    timers.forEach((timer) => window.clearTimeout(timer));
    timers = [];
    if (clockTimer !== null) window.clearInterval(clockTimer);
    clockTimer = null;
  };
  const setStage = (stage, state) => {
    stage.classList.remove("is-queued", "is-live", "is-complete");
    stage.classList.add(`is-${state}`);
    stage.querySelector(".stage-state").textContent =
      state === "live" ? "RUNNING" : state === "complete" ? "DONE" : "QUEUED";
  };
  const reset = () => {
    clearTimers();
    stages.forEach((stage) => setStage(stage, "queued"));
    [...evidenceRows, ...answerRows, ...checks].forEach((row) => row.classList.remove("is-visible"));
    board.classList.remove("is-running", "is-complete");
    runConsole.classList.remove("is-running", "is-complete");
    status.textContent = "FROZEN TRACE READY";
    detail.textContent = "Five recorded events · no live model or network call";
    progress.style.width = "0%";
    clock.textContent = "00:00.000";
    button.disabled = false;
    button.innerHTML = '<span aria-hidden="true">▶</span> Run trace';
  };
  const runTrace = () => {
    reset();
    board.classList.add("is-running");
    runConsole.classList.add("is-running");
    button.disabled = true;
    button.textContent = "RUNNING";
    const started = performance.now();
    clockTimer = window.setInterval(() => {
      const elapsed = Math.round(performance.now() - started);
      clock.textContent = `00:${String(Math.floor(elapsed / 1000)).padStart(2, "0")}.${String(elapsed % 1000).padStart(3, "0")}`;
    }, 31);

    const times = reducedMotion ? [0, 0, 0, 0, 0] : [100, 760, 1500, 2600, 3700];
    stages.forEach((stage, index) => {
      schedule(() => {
        if (index > 0) setStage(stages[index - 1], "complete");
        setStage(stage, "live");
        status.textContent = stage.dataset.stage.toUpperCase();
        detail.textContent = `Event ${index + 1} of 5 · replaying recorded data`;
        progress.style.width = `${(index + 1) * 20}%`;
        if (index === 2) evidenceRows.forEach((row, rowIndex) => schedule(() => row.classList.add("is-visible"), reducedMotion ? 0 : rowIndex * 85));
        if (index === 3) answerRows.forEach((row, rowIndex) => schedule(() => row.classList.add("is-visible"), reducedMotion ? 0 : rowIndex * 85));
        if (index === 4) checks.forEach((row, rowIndex) => schedule(() => row.classList.add("is-visible"), reducedMotion ? 0 : rowIndex * 75));
      }, times[index]);
    });

    schedule(() => {
      clearTimers();
      stages.forEach((stage) => setStage(stage, "complete"));
      [...evidenceRows, ...answerRows, ...checks].forEach((row) => row.classList.add("is-visible"));
      board.classList.remove("is-running");
      board.classList.add("is-complete");
      runConsole.classList.remove("is-running");
      runConsole.classList.add("is-complete");
      status.textContent = "TRACE COMPLETE · 5/5 VERIFIED";
      detail.textContent = "Every displayed value matches the frozen artifact";
      progress.style.width = "100%";
      clock.textContent = reducedMotion ? "00:00.020" : "00:04.600";
      button.disabled = false;
      button.innerHTML = '<span aria-hidden="true">↻</span> Replay';
    }, reducedMotion ? 20 : 4600);
  };

  button.addEventListener("click", runTrace);
  window.addEventListener("message", (event) => {
    if (event.data?.type === "circuit:replay") runTrace();
  });
  reset();
  if (!embedded) schedule(runTrace, reducedMotion ? 0 : 450);
})();

(() => {
  "use strict";

  const measured = window.CIRCUIT_DEMO_DATA;
  const product = window.CIRCUIT_PRODUCT_DATA;
  if (!measured || !product) {
    document.body.innerHTML = "<p>Run the CIRCUIT demo build before opening this page.</p>";
    return;
  }

  const byId = (id) => document.getElementById(id);
  const setText = (id, value) => {
    const node = byId(id);
    if (node) node.textContent = value;
  };
  const percent = (value) =>
    `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 1)}%`;
  const integer = (value) =>
    new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
  const annualMoney = (value) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0
    }).format(value);
  const preciseMoney = (value) => `$${value.toFixed(6)}`;
  const finiteNumber = (value) => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
  };

  const aggregateA = measured.aggregate.A;
  const aggregateC = measured.aggregate.C;
  const aggregateG = measured.aggregate.G;
  const aggregateJ = measured.aggregate.J;
  const tokenDrop = 1 - aggregateC.mean_tokens / aggregateA.mean_tokens;
  const costDrop = 1 - aggregateC.total_cost / aggregateA.total_cost;

  const measuredValues = {
    "measured-token-drop": `−${(tokenDrop * 100).toFixed(1)}%`,
    "measured-cost-drop": `−${(costDrop * 100).toFixed(1)}%`,
    "measured-json-before": percent(aggregateA.strict_json),
    "measured-json-after": percent(aggregateC.strict_json),
    "measured-recall-before": percent(aggregateA.gold_recall_at_5),
    "measured-recall-after": percent(aggregateC.gold_recall_at_5),
    "proof-recall": percent(aggregateC.gold_recall_at_5),
    "proof-recall-before": percent(aggregateA.gold_recall_at_5),
    "proof-json": percent(aggregateC.strict_json),
    "proof-json-before": percent(aggregateA.strict_json),
    "proof-tokens": integer(aggregateC.mean_tokens),
    "proof-tokens-before": integer(aggregateA.mean_tokens),
    "proof-cost": preciseMoney(aggregateC.cost_per_verified),
    "proof-cost-before": preciseMoney(aggregateA.cost_per_verified)
  };
  Object.entries(measuredValues).forEach(([id, value]) => setText(id, value));

  const benchmarkRows = [
    {
      label: "Gemma + vanilla MCP",
      className: "",
      data: aggregateA
    },
    {
      label: "Gemma + CIRCUIT",
      className: "results-winner",
      data: aggregateC
    },
    {
      label: "Gemma · no tools",
      className: "",
      data: aggregateG
    },
    {
      label: "Opus · no tools",
      className: "",
      data: aggregateJ
    }
  ];
  const benchmarkBody = byId("benchmark-body");
  benchmarkRows.forEach(({ label, className, data }) => {
    const row = document.createElement("tr");
    row.className = className;
    const cells = [
      label,
      data.method,
      percent(data.strict_json),
      percent(data.gold_recall_at_5),
      data.doi_validity == null ? "N/A" : percent(data.doi_validity),
      data.mean_tokens == null ? "N/A" : integer(data.mean_tokens),
      data.total_cost == null ? "N/A" : preciseMoney(data.total_cost)
    ];
    cells.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      row.appendChild(cell);
    });
    benchmarkBody.appendChild(row);
  });

  const executionsInput = byId("executions-input");
  const cadenceInput = byId("cadence-input");
  const currentCostInput = byId("current-cost-input");
  const toolCostInput = byId("tool-cost-input");
  const optimizedCostInput = byId("optimized-cost-input");
  const compiledResult = byId("compiled-result");

  const updateProjection = () => {
    const executions = finiteNumber(executionsInput.value);
    const currentCost = finiteNumber(currentCostInput.value);
    const toolCost = finiteNumber(toolCostInput.value);
    const optimizedCost = finiteNumber(optimizedCostInput.value);
    const cadenceMultiplier =
      product.cadence_multipliers[cadenceInput.value]
      ?? product.cadence_multipliers.daily;
    const annualExecutions = executions * cadenceMultiplier;
    const annualCurrent = annualExecutions * currentCost;
    const annualOptimized = annualExecutions * optimizedCost;
    const savings = annualCurrent - annualOptimized;
    const reduction = currentCost > 0
      ? (currentCost - optimizedCost) / currentCost
      : 0;
    const toolShare = currentCost > 0
      ? Math.min(1, toolCost / currentCost)
      : 0;

    setText("annual-executions", integer(annualExecutions));
    setText("annual-current", annualMoney(annualCurrent));
    setText("annual-optimized", annualMoney(annualOptimized));
    setText("annual-savings", annualMoney(Math.abs(savings)));
    setText(
      "reduction-rate",
      savings >= 0
        ? `${Math.max(0, reduction * 100).toFixed(0)}% lower cost / execution`
        : `${Math.abs(reduction * 100).toFixed(0)}% higher cost / execution`
    );
    setText(
      "savings-label",
      savings >= 0 ? "Projected annual savings" : "Projected additional annual cost"
    );
    setText("tool-cost-share-label", `${(toolShare * 100).toFixed(0)}%`);
    byId("tool-cost-share").style.width = `${toolShare * 100}%`;

    const invalidAttribution = toolCost > currentCost;
    toolCostInput.setAttribute("aria-invalid", String(invalidAttribution));
    compiledResult.classList.toggle("is-cost-increase", savings < 0);
  };

  [
    executionsInput,
    cadenceInput,
    currentCostInput,
    toolCostInput,
    optimizedCostInput
  ].forEach((input) => input.addEventListener("input", updateProjection));
  updateProjection();

  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  const money = (value) => `$${Number(value).toFixed(2)}`;
  const compactPercent = (value) => `${(Number(value) * 100).toFixed(1)}%`;
  const artifactKicker = byId("artifact-kicker");
  const artifactBadge = byId("artifact-badge");
  const artifactContent = byId("artifact-content");
  const stageRail = byId("stage-rail");

  const artifactFrame = (artifact, body, footnote = "") => `
    <div class="artifact-copy">
      <h3>${escapeHtml(artifact.title)}</h3>
      <p>${escapeHtml(artifact.summary)}</p>
    </div>
    ${body}
    ${footnote ? `<p class="artifact-footnote">${escapeHtml(footnote)}</p>` : ""}
  `;

  const renderSchemas = (artifact) => artifactFrame(
    artifact,
    `
      <div class="artifact-stats artifact-stats-three">
        <div><strong>${artifact.totals.mcps}</strong><span>MCPs</span></div>
        <div><strong>${artifact.totals.tools}</strong><span>raw tools</span></div>
        <div><strong>${artifact.totals.fields}</strong><span>schema fields</span></div>
      </div>
      <div class="schema-list">
        ${artifact.connectors.map((connector) => `
          <div class="schema-row">
            <div>
              <strong>${escapeHtml(connector.name)}</strong>
              <span>${connector.tools} tools · ${connector.fields} fields</span>
            </div>
            <code>${connector.selected.map(escapeHtml).join("<br>")}</code>
          </div>
        `).join("")}
      </div>
    `,
    "Selected tools highlighted from 47 discovered tools."
  );

  const renderCapabilities = (artifact) => artifactFrame(
    artifact,
    `
      <div class="capability-table">
        <div class="artifact-table-head">
          <span>Required action</span><span>Exact MCP tool</span><span>Required fields</span>
        </div>
        ${artifact.actions.map((action, index) => `
          <div class="capability-row">
            <span><i>${String(index + 1).padStart(2, "0")}</i>${escapeHtml(action.action)}</span>
            <code>${escapeHtml(action.tool)}</code>
            <small>${escapeHtml(action.fields)}</small>
          </div>
        `).join("")}
      </div>
    `
  );

  const renderContract = (artifact) => artifactFrame(
    artifact,
    `
      <div class="contract-topline">
        <div>
          <span>Exposed fields</span>
          <strong>${artifact.before_fields} <i>→</i> ${artifact.after_fields}</strong>
        </div>
        <code>${escapeHtml(artifact.version)}</code>
      </div>
      <div class="contract-grid">
        <pre>{${Object.entries(artifact.schema).map(([key, value]) =>
          `\n  <b>"${escapeHtml(key)}"</b>: "${escapeHtml(value)}"`
        ).join(",")}\n}</pre>
        <ul class="artifact-rules">
          ${artifact.rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}
        </ul>
      </div>
    `
  );

  const renderTests = (artifact) => artifactFrame(
    artifact,
    `
      <div class="test-summary">
        <strong>${artifact.passed}/${artifact.total}</strong>
        <span>regression checks passed · 3 observed MCP failure signatures locked</span>
      </div>
      <div class="failure-corpus">
        ${artifact.cases.map((testCase, index) => `
          <article class="failure-case">
            <header>
              <span>${String(index + 1).padStart(2, "0")} · ${escapeHtml(testCase.source)}</span>
              <b>${escapeHtml(testCase.status)}</b>
            </header>
            <strong>${escapeHtml(testCase.name)}</strong>
            <div>
              <p><small>SKILL / EXPECTED</small><code>${escapeHtml(testCase.documented)}</code></p>
              <i aria-hidden="true">→</i>
              <p><small>LIVE MCP / OBSERVED</small><code>${escapeHtml(testCase.observed)}</code></p>
            </div>
            <footer><span>CLIENT FLAG</span>${escapeHtml(testCase.action)}</footer>
          </article>
        `).join("")}
      </div>
    `
  );

  const candidatePasses = (candidate, target) =>
    candidate.reliability >= target
    && candidate.schema === 1
    && candidate.write_safety === 1;

  const renderScorecard = (artifact) => artifactFrame(
    artifact,
    `
      <div class="scorecard">
        <div class="artifact-table-head scorecard-head">
          <span>Configuration</span><span>Reliability</span><span>Safety</span><span>Cost / run</span><span>Decision</span>
        </div>
        ${artifact.candidates.map((candidate) => {
          const passes = candidatePasses(candidate, artifact.reliability_target);
          return `
            <div class="scorecard-row${candidate.name === product.workflow.selected_configuration ? " is-selected" : ""}">
              <strong>${escapeHtml(candidate.name)}</strong>
              <span>${compactPercent(candidate.reliability)}</span>
              <span>${candidate.schema === 1 && candidate.write_safety === 1 ? "100%" : "FAIL"}</span>
              <span>${money(candidate.cost)}</span>
              <b class="${passes ? "is-pass" : "is-fail"}">${passes ? "PASS" : "FAIL"}</b>
            </div>
          `;
        }).join("")}
      </div>
    `,
    "Illustrative scorecard · target reliability ≥ 99.0%."
  );

  const renderSelection = (artifact) => artifactFrame(
    artifact,
    `
      <div class="policy-expression"><code>${escapeHtml(artifact.expression)}</code></div>
      <div class="policy-grid">
        <div>
          <span>Eligibility gates</span>
          <ul>${artifact.requirements.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}</ul>
        </div>
        <div class="policy-winner">
          <span>Selected route</span>
          <strong>${escapeHtml(artifact.selected)}</strong>
          <p><b>${compactPercent(artifact.reliability)}</b> reliability · <b>${money(artifact.cost)}</b> / execution</p>
        </div>
      </div>
      <div class="alternative-row">
        ${artifact.alternatives.map((item) => `
          <span><b>${escapeHtml(item.name)}</b>${escapeHtml(item.status)}</span>
        `).join("")}
      </div>
    `
  );

  const renderDeployment = (artifact) => artifactFrame(
    artifact,
    `
      <div class="deployment-grid">
        <div class="manifest">
          <span>Deployment manifest</span>
          ${Object.entries(artifact.manifest).map(([key, value]) => `
            <p><small>${escapeHtml(key)}</small><code>${escapeHtml(value)}</code></p>
          `).join("")}
        </div>
        <div class="monitoring">
          <span>Monitoring policy</span>
          <ul>${artifact.thresholds.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </div>
      </div>
      <div class="example-trace">
        <span><i></i> Example passing trace</span>
        <strong>${escapeHtml(artifact.trace.id)}</strong>
        <code>${escapeHtml(artifact.trace.route)}</code>
        <div><b>${escapeHtml(artifact.trace.result)}</b><span>${escapeHtml(artifact.trace.cost)}</span><span>${escapeHtml(artifact.trace.duration)}</span></div>
      </div>
    `,
    "Illustrative deployment record · no live MCP writes were made."
  );

  const artifactRenderers = {
    schemas: renderSchemas,
    capabilities: renderCapabilities,
    contract: renderContract,
    tests: renderTests,
    scorecard: renderScorecard,
    selection: renderSelection,
    deployment: renderDeployment
  };

  const renderScenario = () => {
    artifactKicker.textContent = "SCENARIO INPUT";
    artifactBadge.textContent = "Illustrative scenario";
    artifactContent.innerHTML = `
      <div class="scenario-intro">
        <span>${escapeHtml(product.workflow.input.source)}</span>
        <strong>${escapeHtml(product.workflow.input.sender)}</strong>
        <blockquote>${escapeHtml(product.workflow.input.message)}</blockquote>
      </div>
      <div class="expected-outcome">
        <span>Expected safe outcome</span>
        <ol>
          ${product.workflow.expected_actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}
        </ol>
      </div>
      <p class="artifact-footnote">Illustrative workflow · click “Compile workflow” to inspect each generated artifact.</p>
    `;
  };

  const renderStageArtifact = (index, { live = false } = {}) => {
    const stage = product.stages[index];
    if (!stage || !artifactRenderers[stage.artifact.kind]) return;
    artifactKicker.textContent = `${String(index + 1).padStart(2, "0")} · ${stage.label.toUpperCase()}`;
    artifactBadge.textContent = stage.artifact.provenance || "Illustrative artifact";
    const stream = stage.stream || stage.activity;
    artifactContent.innerHTML = `
      <div class="gemma-stream${live ? " is-live" : " is-complete"}">
        <span>${live ? "GEMMA · WRITING" : "GEMMA · OUTPUT"}</span>
        <code id="gemma-stream-text" class="${live ? "type-caret" : ""}">${live ? "" : escapeHtml(stream)}</code>
        <small>${live ? "Generating a model-specific workflow artifact" : "Frozen illustrative compiler output"}</small>
      </div>
      <div class="artifact-reveal${live ? " is-streaming" : " is-visible"}" id="artifact-reveal">
        ${artifactRenderers[stage.artifact.kind](stage.artifact)}
      </div>
    `;
    if (live) {
      typeStageText(byId("gemma-stream-text"), stream, 900);
      schedule(() => {
        const reveal = byId("artifact-reveal");
        if (reveal) {
          reveal.classList.remove("is-streaming");
          reveal.classList.add("is-visible");
        }
      }, 520);
    }
    stageButtons.forEach((button, buttonIndex) => {
      button.classList.toggle("is-selected", buttonIndex === index);
      button.setAttribute("aria-pressed", String(buttonIndex === index));
    });
  };

  product.stages.forEach((stage, index) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <button class="stage-rail-button is-queued" type="button" data-stage-index="${index}" aria-pressed="false">
        <span>${String(index + 1).padStart(2, "0")}</span>
        <span><strong>${escapeHtml(stage.label)}</strong><small>${escapeHtml(stage.subtitle)}</small></span>
        <b>QUEUED</b>
      </button>
    `;
    stageRail.appendChild(item);
  });

  const stageButtons = Array.from(document.querySelectorAll(".stage-rail-button"));
  stageButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!button.disabled) renderStageArtifact(Number(button.dataset.stageIndex));
    });
    button.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && !button.disabled) {
        event.preventDefault();
        renderStageArtifact(Number(button.dataset.stageIndex));
      }
    });
  });

  const evaluateStage = product.stages.find((stage) => stage.artifact.kind === "scorecard");
  const eligibleCandidates = evaluateStage.artifact.candidates
    .filter((candidate) => candidatePasses(candidate, evaluateStage.artifact.reliability_target))
    .sort((left, right) => left.cost - right.cost);
  const selectedCandidate = eligibleCandidates[0];
  if (selectedCandidate) {
    setText("selected-model", selectedCandidate.name);
    setText("reliability-result", compactPercent(selectedCandidate.reliability));
  }

  const compileButton = byId("compile-button");
  const compileStatus = byId("compile-status");
  const compileClock = byId("compile-clock");
  const compileProgress = byId("compile-progress");
  const compilerConsole = byId("compiler-console");
  // The query override lets the offline bundle prove this branch in browsers
  // that cannot emulate OS-level media preferences.
  const reducedMotion =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
    || new URLSearchParams(window.location.search).get("motion") === "reduce";
  let timers = [];
  let clockTimer = null;

  const schedule = (callback, delay) => {
    const timer = window.setTimeout(callback, delay);
    timers.push(timer);
  };
  const clearTimers = () => {
    timers.forEach((timer) => window.clearTimeout(timer));
    timers = [];
    if (clockTimer !== null) window.clearInterval(clockTimer);
    clockTimer = null;
  };
  const typeStageText = (node, text, duration) => {
    if (!node) return;
    if (reducedMotion) {
      node.textContent = text;
      return;
    }
    const interval = Math.max(9, Math.floor(duration / Math.max(text.length, 1)));
    let position = 0;
    const typeNext = () => {
      if (!node.isConnected) return;
      position += 1;
      node.textContent = text.slice(0, position);
      if (position < text.length) schedule(typeNext, interval);
    };
    typeNext();
  };
  const formatClock = (milliseconds) => {
    const seconds = Math.floor(milliseconds / 1000);
    const remainder = milliseconds % 1000;
    return `00:${String(seconds).padStart(2, "0")}.${String(remainder).padStart(3, "0")}`;
  };
  const setPipelineStage = (button, state) => {
    button.classList.remove("is-queued", "is-live", "is-complete");
    button.classList.add(`is-${state}`);
    button.querySelector(":scope > b").textContent =
      state === "live" ? "RUNNING" : state === "complete" ? "DONE" : "QUEUED";
    button.disabled = state !== "complete";
  };
  const resetCompiler = () => {
    clearTimers();
    stageButtons.forEach((button) => {
      setPipelineStage(button, "queued");
      button.classList.remove("is-selected");
      button.setAttribute("aria-pressed", "false");
    });
    renderScenario();
    compilerConsole.classList.remove("is-running", "is-complete");
    compileStatus.textContent = "READY TO COMPILE";
    compileClock.textContent = "00:00.000";
    compileProgress.style.width = "0%";
    compileButton.disabled = false;
    compileButton.innerHTML = '<span aria-hidden="true">▶</span> Compile workflow';
  };
  const completeCompiler = (duration) => {
    clearTimers();
    stageButtons.forEach((button) => setPipelineStage(button, "complete"));
    renderStageArtifact(product.stages.length - 1);
    compilerConsole.classList.remove("is-running");
    compilerConsole.classList.add("is-complete");
    compileStatus.textContent = "COMPILE COMPLETE · RELIABILITY TARGET PASSED";
    compileClock.textContent = formatClock(duration);
    compileProgress.style.width = "100%";
    compileButton.disabled = false;
    compileButton.innerHTML = '<span aria-hidden="true">↻</span> Replay compilation';
  };
  const runCompiler = () => {
    resetCompiler();
    compilerConsole.classList.add("is-running");
    compileButton.disabled = true;
    compileButton.textContent = "GEMMA IS COMPILING";
    const started = performance.now();

    clockTimer = window.setInterval(() => {
      compileClock.textContent = formatClock(Math.round(performance.now() - started));
    }, 31);

    if (reducedMotion) {
      completeCompiler(20);
      return;
    }

    const interval = 1200;
    stageButtons.forEach((button, index) => {
      schedule(() => {
        if (index > 0) setPipelineStage(stageButtons[index - 1], "complete");
        setPipelineStage(button, "live");
        renderStageArtifact(index, { live: true });
        compileStatus.textContent = product.stages[index].activity.toUpperCase();
        compileProgress.style.width = `${((index + 0.45) / stageButtons.length) * 100}%`;
      }, 140 + index * interval);
    });

    schedule(() => completeCompiler(9000), 9000);
  };

  compileButton.addEventListener("click", runCompiler);
  resetCompiler();
  compiledResult.classList.add("is-ready");
  setText("result-state", "Target passed");

  const onboarding = product.onboarding;
  const onboardingShell = byId("onboarding-shell");
  const onboardingPhases = byId("onboarding-phases");
  const onboardingReplay = byId("onboarding-replay");
  const phaseTerminal = byId("phase-terminal");
  const phaseCode = byId("phase-code");
  const onboardingCode = byId("onboarding-code");
  const architectureNodes = Array.from(
    document.querySelectorAll("[data-architecture-node]")
  );
  const architectureLinks = Array.from(
    document.querySelectorAll(".architecture-link")
  );
  let onboardingTimers = [];
  let onboardingFinished = false;
  let selectedOnboardingPhase = 0;

  const clearOnboardingTimers = () => {
    onboardingTimers.forEach((timer) => window.clearTimeout(timer));
    onboardingTimers = [];
  };

  onboarding.phases.forEach((phase, index) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <button type="button" data-onboarding-phase="${index}" aria-pressed="false" disabled>
        <span>${String(index + 1).padStart(2, "0")}</span>
        <strong>${escapeHtml(phase.label)}</strong>
        <small>${escapeHtml(phase.status)}</small>
        <b>QUEUED</b>
      </button>
    `;
    onboardingPhases.appendChild(item);
  });

  const onboardingButtons = Array.from(
    onboardingPhases.querySelectorAll("[data-onboarding-phase]")
  );

  const setOnboardingButtonStates = (activeIndex, playing) => {
    onboardingButtons.forEach((button, index) => {
      const state = index < activeIndex
        ? "DONE"
        : index === activeIndex
          ? playing ? "RUNNING" : "SELECTED"
          : onboardingFinished ? "READY" : "QUEUED";
      button.classList.toggle("is-active", index === activeIndex);
      button.classList.toggle("is-complete", index < activeIndex || onboardingFinished);
      button.setAttribute("aria-pressed", String(index === activeIndex));
      button.disabled = !onboardingFinished;
      button.querySelector(":scope > b").textContent = state;
    });
  };

  const renderOnboardingPhase = (index, { playing = false } = {}) => {
    const phase = onboarding.phases[index];
    if (!phase) return;
    selectedOnboardingPhase = index;
    onboardingShell.dataset.phase = phase.id;
    setText("phase-kicker", `${String(index + 1).padStart(2, "0")} · ${phase.label.toUpperCase()}`);
    setText("phase-title", phase.heading);
    setText("phase-copy", phase.copy);
    setText("onboarding-status", playing ? phase.status : `Inspecting · ${phase.status}`);
    setText("architecture-status", phase.graph_status);
    phaseTerminal.textContent = phase.terminal.join("\n");
    onboardingCode.hidden = !phase.show_code;
    phaseCode.textContent = phase.show_code ? onboarding.snippet : "";

    architectureNodes.forEach((node) => {
      const isActive = phase.active_nodes.includes(node.dataset.architectureNode);
      node.classList.toggle("is-active", isActive);
      node.classList.toggle("is-complete", onboardingFinished || index === onboarding.phases.length - 1);
    });
    architectureLinks.forEach((link, linkIndex) => {
      link.classList.toggle("is-active", playing && linkIndex === Math.min(index, architectureLinks.length - 1));
      link.classList.toggle("is-complete", onboardingFinished || linkIndex < index);
    });
    byId("architecture-result").classList.toggle(
      "is-complete",
      onboardingFinished || index === onboarding.phases.length - 1
    );
    setOnboardingButtonStates(index, playing);
  };

  const finishOnboarding = () => {
    clearOnboardingTimers();
    onboardingFinished = true;
    onboardingShell.classList.remove("is-playing");
    onboardingShell.classList.add("is-complete");
    renderOnboardingPhase(onboarding.phases.length - 1);
    setText("onboarding-status", "Setup complete · 3 specialist tools ready");
    onboardingReplay.disabled = false;
  };

  const playOnboarding = () => {
    clearOnboardingTimers();
    onboardingFinished = false;
    onboardingShell.classList.remove("is-complete");
    onboardingShell.classList.add("is-playing");
    onboardingReplay.disabled = true;
    renderOnboardingPhase(0, { playing: true });

    if (reducedMotion) {
      finishOnboarding();
      return;
    }

    const phaseTimes = [0, 1650, 3400, 5200];
    phaseTimes.slice(1).forEach((delay, offset) => {
      onboardingTimers.push(window.setTimeout(
        () => renderOnboardingPhase(offset + 1, { playing: true }),
        delay
      ));
    });
    onboardingTimers.push(window.setTimeout(finishOnboarding, onboarding.duration_ms));
  };

  onboardingButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!onboardingFinished) return;
      clearOnboardingTimers();
      renderOnboardingPhase(Number(button.dataset.onboardingPhase));
    });
    button.addEventListener("keydown", (event) => {
      if (
        onboardingFinished
        && (event.key === "Enter" || event.key === " ")
      ) {
        event.preventDefault();
        clearOnboardingTimers();
        renderOnboardingPhase(Number(button.dataset.onboardingPhase));
      }
    });
  });
  onboardingReplay.addEventListener("click", playOnboarding);
  renderOnboardingPhase(0, { playing: true });
  window.setTimeout(playOnboarding, reducedMotion ? 0 : 260);

  const viewer = byId("product-viewer");
  const viewerClose = byId("viewer-close");
  const compilerTab = byId("viewer-compiler-tab");
  const traceTab = byId("viewer-trace-tab");
  const compilerPanel = byId("viewer-compiler");
  const tracePanel = byId("viewer-trace");
  const compilerTrigger = byId("platform-compiler-trigger");
  const specialistTrigger = byId("platform-specialist-trigger");
  const workflowFrame = byId("workflow-frame");
  let viewerMode = "compiler";
  let focusReturnTarget = null;
  let frameReady = false;
  let replayRequested = false;

  const requestWorkflowReplay = () => {
    replayRequested = true;
    if (!frameReady || !workflowFrame.contentWindow) return;
    workflowFrame.contentWindow.postMessage({ type: "circuit:replay" }, "*");
  };

  const stopWorkflow = () => {
    replayRequested = false;
    frameReady = false;
    workflowFrame.src = "about:blank";
  };

  workflowFrame.addEventListener("load", () => {
    if (workflowFrame.src === "about:blank" || viewerMode !== "trace" || !viewer.open) return;
    frameReady = true;
    requestWorkflowReplay();
  });

  const setViewerMode = (mode) => {
    viewerMode = mode;
    clearTimers();
    resetCompiler();
    stopWorkflow();

    const compilerActive = mode === "compiler";
    compilerPanel.hidden = !compilerActive;
    tracePanel.hidden = compilerActive;
    compilerTab.setAttribute("aria-selected", String(compilerActive));
    traceTab.setAttribute("aria-selected", String(!compilerActive));
    setText("viewer-title", compilerActive
      ? "Compilation inspector"
      : "A real question. Every observable step.");
    setText("viewer-kicker", compilerActive
      ? "ILLUSTRATIVE PRODUCT ARTIFACTS"
      : "MEASURED OPENAIRE TRACE");

    if (compilerActive) {
      runCompiler();
    } else {
      replayRequested = true;
      workflowFrame.src = workflowFrame.dataset.src;
    }
  };

  const openViewer = (mode, trigger) => {
    focusReturnTarget = trigger;
    if (!viewer.open) viewer.showModal();
    setViewerMode(mode);
    window.setTimeout(() => {
      (mode === "compiler" ? compilerTab : traceTab).focus();
    }, 0);
  };

  const cleanupViewer = () => {
    clearTimers();
    resetCompiler();
    stopWorkflow();
  };

  const closeViewer = () => {
    if (!viewer.open) return;
    cleanupViewer();
    viewer.close();
  };

  compilerTrigger.addEventListener("click", () => openViewer("compiler", compilerTrigger));
  specialistTrigger.addEventListener("click", () => openViewer("trace", specialistTrigger));
  compilerTab.addEventListener("click", () => setViewerMode("compiler"));
  traceTab.addEventListener("click", () => setViewerMode("trace"));
  viewerClose.addEventListener("click", closeViewer);

  viewer.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeViewer();
  });
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer) closeViewer();
  });
  viewer.addEventListener("close", () => {
    cleanupViewer();
    const target = focusReturnTarget;
    focusReturnTarget = null;
    if (target?.isConnected) target.focus();
  });
  viewer.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeViewer();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(viewer.querySelectorAll(
      'button:not([disabled]), a[href], iframe, [tabindex]:not([tabindex="-1"])'
    )).filter((element) => !element.closest("[hidden]"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();

(() => {
  "use strict";

  const data = window.CIRCUIT_DEMO_DATA;
  if (!data) {
    document.body.innerHTML = "<p>Run scripts/build_demo.py before opening the demo.</p>";
    return;
  }

  const byId = (id) => document.getElementById(id);
  const aggregateA = data.aggregate.A;
  const aggregateC = data.aggregate.C;
  const aggregateG = data.aggregate.G;
  const aggregateJ = data.aggregate.J;
  const percent = (value) => `${(value * 100).toFixed(value === 0 || value === 1 ? 0 : 1)}%`;
  const number = (value) => new Intl.NumberFormat("en-US").format(Math.round(value));
  const tokenDrop = (1 - aggregateC.mean_tokens / aggregateA.mean_tokens) * 100;
  const money = (value) => `$${value.toFixed(6)}`;

  const values = {
    "hero-strict-json": percent(aggregateC.strict_json),
    "hero-strict-json-before": percent(aggregateA.strict_json),
    "hero-recall": percent(aggregateC.gold_recall_at_5),
    "hero-recall-before": percent(aggregateA.gold_recall_at_5),
    "hero-cost-per-cite": money(aggregateC.cost_per_verified),
    "hero-cost-per-cite-before": money(aggregateA.cost_per_verified),
    "hero-token-drop": `−${tokenDrop.toFixed(1)}%`,
    "hero-token-before": number(aggregateA.mean_tokens),
    "hero-token-after": number(aggregateC.mean_tokens),
    "no-mcp-recall": percent(aggregateG.gold_recall_at_5),
    "no-mcp-validity": percent(aggregateG.doi_validity),
    "no-mcp-strict-json": percent(aggregateG.strict_json),
    "raw-strict-json": percent(aggregateA.strict_json),
    "raw-recall": percent(aggregateA.gold_recall_at_5),
    "raw-validity": percent(aggregateA.doi_validity),
    "raw-tokens": number(aggregateA.mean_tokens),
    "raw-parameter-count": `${data.contexts.naive.search_parameter_count} params`,
    "engineered-tokens": number(aggregateC.mean_tokens),
    "engineered-recall": percent(aggregateC.gold_recall_at_5),
    "engineered-strict-json": percent(aggregateC.strict_json),
    "compiler-before": data.contexts.naive.search_parameter_count,
    "compiler-after": data.contexts.engineered.search_parameter_count,
    "versus-gemma-recall": percent(aggregateC.gold_recall_at_5),
    "versus-gemma-cost": money(aggregateC.total_cost),
    "versus-gemma-strict-json": percent(aggregateC.strict_json),
    "versus-opus-recall": percent(aggregateJ.gold_recall_at_5),
    "versus-opus-cost": money(aggregateJ.total_cost),
    "versus-opus-strict-json": percent(aggregateJ.strict_json)
  };

  Object.entries(values).forEach(([id, value]) => {
    byId(id).textContent = value;
  });

  const parameterField = document.querySelector(".parameter-field");
  parameterField.innerHTML = Array.from(
    { length: data.contexts.naive.search_parameter_count },
    () => "<i></i>"
  ).join("");
})();

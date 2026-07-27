window.CIRCUIT_PRODUCT_DATA = {
  kind: "illustrative_projection",
  disclaimer: "Illustrative company scenario. Not a measured customer result.",
  workflow: {
    id: "customer-escalation",
    name: "Customer escalation triage",
    input: {
      source: "Slack · #customer-escalations",
      sender: "Maya · Support lead",
      message:
        "ACME checkout events are 40 minutes late. Customer SF-01842. Open a P1 and notify the account owner."
    },
    expected_actions: [
      "Read the complete escalation thread",
      "Resolve Salesforce account SF-01842",
      "Search Jira for an existing incident",
      "Create a P1 only when no duplicate exists",
      "Reply in Slack and notify the account owner"
    ],
    contract: "customer-escalation.v12",
    connectors: ["Slack MCP", "Salesforce MCP", "Jira MCP"],
    reliability_target: 0.99,
    selected_configuration: "Gemma + CIRCUIT",
    projected_reliability: 0.992,
    regression_tests_passed: 184,
    regression_tests_total: 184
  },
  defaults: {
    executions: 500,
    cadence: "daily",
    current_cost: 2.0,
    tool_context_cost: 1.5,
    optimized_cost: 0.3
  },
  cadence_multipliers: {
    daily: 365,
    monthly: 12,
    annual: 1
  },
  stages: [
    {
      id: "discover",
      label: "Discover",
      subtitle: "Tools + schemas",
      activity: "Discovering MCP tools and schemas",
      stream:
        "tools/list returned 47 tools and 312 fields. Keeping the five tools this workflow can actually call.",
      artifact: {
        kind: "schemas",
        title: "Inventory the raw MCP surface",
        summary:
          "CIRCUIT inspects every available tool, then highlights only the tools relevant to this workflow.",
        totals: { mcps: 3, tools: 47, fields: 312 },
        connectors: [
          {
            name: "Slack MCP",
            tools: 11,
            fields: 64,
            selected: ["slack.get_thread", "slack.reply_to_thread"]
          },
          {
            name: "Salesforce MCP",
            tools: 14,
            fields: 103,
            selected: ["salesforce.get_account"]
          },
          {
            name: "Jira MCP",
            tools: 22,
            fields: 145,
            selected: ["jira.search_issues", "jira.create_issue"]
          }
        ]
      }
    },
    {
      id: "map",
      label: "Map",
      subtitle: "Required actions",
      activity: "Mapping required workflow capabilities",
      stream:
        "Mapping the Slack request to five evidence-backed actions: read, resolve, search, create, and notify.",
      artifact: {
        kind: "capabilities",
        title: "Map intent to five exact tool calls",
        summary:
          "The workflow is reduced to the actions and fields needed to complete this escalation safely.",
        actions: [
          {
            action: "Read trigger",
            tool: "slack.get_thread",
            fields: "channel_id, thread_ts"
          },
          {
            action: "Resolve account",
            tool: "salesforce.get_account",
            fields: "account_id, fields"
          },
          {
            action: "Check duplicates",
            tool: "jira.search_issues",
            fields: "jql, max_results"
          },
          {
            action: "Create P1",
            tool: "jira.create_issue",
            fields: "project, summary, priority, description"
          },
          {
            action: "Notify owner",
            tool: "slack.reply_to_thread",
            fields: "channel_id, thread_ts, text"
          }
        ]
      }
    },
    {
      id: "compile",
      label: "Compile",
      subtitle: "Model contract",
      activity: "Generating a model-specific contract",
      stream:
        "Pruning 312 raw fields to 18. Writing customer-escalation.v12 with explicit tool and safety rules.",
      artifact: {
        kind: "contract",
        title: "Compile a small-model-ready contract",
        summary:
          "The raw schemas become a versioned contract with explicit evidence and write-safety rules.",
        before_fields: 312,
        after_fields: 18,
        version: "customer-escalation.v12",
        schema: {
          account_id: "string · from Salesforce",
          duplicate_key: "string | null · from Jira",
          issue_id: "string | null · never invented",
          slack_reply: "string · evidence-grounded"
        },
        rules: [
          "Search Jira before any create.",
          "Set Highest only when Enterprise support and outage are confirmed.",
          "Copy account and issue IDs only from tool evidence.",
          "On write timeout, stop and require review."
        ]
      }
    },
    {
      id: "test",
      label: "Test",
      subtitle: "Failure corpus",
      activity: "Running deterministic regression tests",
      stream:
        "Replaying three observed OpenAIRE contract failures. Each one becomes a client alert and a permanent regression check.",
      artifact: {
        kind: "tests",
        provenance: "Observed OpenAIRE incidents",
        title: "Turn observed MCP failures into safeguards",
        summary:
          "CIRCUIT compares the live MCP contract with skills, prompts, and observed responses, then flags actionable drift to the client or MCP owner.",
        passed: 184,
        total: 184,
        cases: [
          {
            source: "ALIEN OPENAIRE · TOOL NAME",
            name: "Skill-to-live schema drift",
            documented: "search_research_products",
            observed: "openaire_search_research_products",
            action: "Expose the live name and flag the stale skill to the MCP owner.",
            status: "LOCKED"
          },
          {
            source: "ALIEN OPENAIRE · RESPONSE",
            name: "Response envelope mismatch",
            documented: "results[] at the response root",
            observed: "data.results[] + summary.results_returned",
            action: "Compile the observed envelope and alert on future path changes.",
            status: "LOCKED"
          },
          {
            source: "ALIEN OPENAIRE · ARGUMENT",
            name: "Citation-direction mismatch",
            documented: "doi for incoming citation traversal",
            observed: "target_pid required for incoming citations",
            action: "Block the unsafe argument and report the contract discrepancy.",
            status: "LOCKED"
          }
        ]
      }
    },
    {
      id: "evaluate",
      label: "Evaluate",
      subtitle: "Candidate models",
      activity: "Benchmarking candidate model configurations",
      stream:
        "Gemma with raw MCP misses the 99% target. Gemma with the compiled contract reaches 99.2% at $0.30.",
      artifact: {
        kind: "scorecard",
        title: "Benchmark reliability before price",
        summary:
          "The same deterministic cases run against each candidate. Passing requires 99% reliability and perfect write safety.",
        reliability_target: 0.99,
        candidates: [
          {
            name: "Gemma · raw MCP",
            reliability: 0.914,
            schema: 0.972,
            write_safety: 0.956,
            cost: 1.1
          },
          {
            name: "Gemma + CIRCUIT",
            reliability: 0.992,
            schema: 1,
            write_safety: 1,
            cost: 0.3
          },
          {
            name: "Frontier model",
            reliability: 0.996,
            schema: 1,
            write_safety: 1,
            cost: 2
          }
        ]
      }
    },
    {
      id: "select",
      label: "Select",
      subtitle: "Reliability → cost",
      activity: "Selecting the lowest-cost passing configuration",
      stream:
        "Filtering by reliability, schema compliance, and write safety—then minimizing cost among passing routes.",
      artifact: {
        kind: "selection",
        title: "Apply the deterministic routing policy",
        summary:
          "CIRCUIT filters by reliability and safety first, then minimizes execution cost among eligible configurations.",
        requirements: [
          "Reliability ≥ 99.0%",
          "Schema compliance = 100%",
          "Write safety = 100%"
        ],
        expression:
          "selected = min(cost_per_execution) where reliability ≥ 99% && schema == 100% && write_safety == 100%",
        selected: "Gemma + CIRCUIT",
        cost: 0.3,
        reliability: 0.992,
        alternatives: [
          { name: "Gemma · raw MCP", status: "INELIGIBLE" },
          { name: "Frontier model", status: "PASS · +$1.70" }
        ]
      }
    },
    {
      id: "deploy",
      label: "Deploy + observe",
      subtitle: "Version + traces",
      activity: "Deploying the contract and activating monitoring",
      stream:
        "Freezing v12 with rollback to v11. Activating drift, reliability, cost, and trace monitoring.",
      artifact: {
        kind: "deployment",
        title: "Deploy a reversible, monitored contract",
        summary:
          "The selected route is frozen into a versioned manifest with rollback, drift alerts, and production trace checks.",
        manifest: {
          contract: "customer-escalation.v12",
          model: "Gemma + CIRCUIT",
          rollback: "customer-escalation.v11",
          status: "ACTIVE"
        },
        thresholds: [
          "Reliability alert < 99.0%",
          "Cost alert > $0.45 / execution",
          "Pause on MCP schema hash change"
        ],
        trace: {
          id: "trace_SF-01842",
          result: "PASS",
          route: "Slack → Salesforce → Jira → Slack",
          cost: "$0.29",
          duration: "1.8s"
        }
      }
    }
  ]
};

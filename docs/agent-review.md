# Agent review rules over ACP

Agent review is an explicit rule plugin. Each `AgentReviewRule` exposes a
`ReviewGuideline`: a stable rule ID, review objective, and concrete instructions.
`PromptReviewRule` implements that interface over the existing `TreeContext` and
uses that same context for every language. It retains the exact source snapshot,
so staged review does not substitute working-tree content.

`ReviewAgent` is the invocation interface. `AcpReviewAgent` implements it using the
[Agent Client Protocol initialization](https://agentclientprotocol.com/protocol/v1/initialization)
and [stdio transport](https://agentclientprotocol.com/protocol/v1/transports).
The official ACP SDK owns protocol payload schemas; local typed envelopes own
JSON-RPC framing, correlation, resource limits, and process lifetime. No generic
JSON payload carrier or type cast is used inside review evaluation.

## Incremental tool submission

The client registers a private stdio MCP server in the ACP session's `mcpServers`
list, using the protocol's [MCP server registration](https://agentclientprotocol.com/protocol/v1/session-setup).
The server exposes exactly two tools:

| Tool | Input | Result |
| --- | --- | --- |
| `submit_finding` | `submission_id`, `line`, `column`, `message` | Small receipt containing `accepted_count` and `duplicate` |
| `finish_review` | `status`, `summary`, `expected_findings` | The same small receipt |

The prompt tells the agent to submit each finding as it is established and wait
for acknowledgement. There is no final JSON findings array and no need to repeat
previous findings in conversation. Final chat text is not interpreted as results;
an empty final message is valid after successful tool completion.

The server binds the path and rule ID to the current review. It validates line
and UTF-8 byte-column bounds, requires an evidence-bearing message, and limits
individual messages to 8,192 characters. A stable submission ID supports retries:
identical evidence returns a duplicate receipt without recording another finding;
a different finding with the same ID is rejected. Each accepted finding is
appended and flushed to a private journal before acknowledgement. Tool responses
contain counts only, so their size does not grow with the findings list.

`finish_review` records an explicit complete/incomplete verdict, a summary limited
to 2,048 characters, and the number of accepted findings. The count must match.
A clean review must explicitly finish with zero findings. Identical completion
retries are harmless; conflicting completion and new findings after completion
are rejected. One server process owns writes to the journal. The adapter reads
the journal into the canonical `ReviewResult` only after ACP returns `end_turn`.

Missing completion, incomplete review, tool unavailability, protocol errors,
unsupported versions, unexpected response/session identities, output overflow,
timeouts, and invalid evidence fail the gate. A prose claim of success cannot
replace tool completion. The journal is private temporary session state and is
removed when the invocation ends; it is not a durable audit archive, and failed
invocations do not publish partial findings as a successful gate result.

## Composition

Register a review rule with the same typed bundle registry as deterministic
checks. Agent review is not enabled automatically, and no agent executable or
provider is selected implicitly.

```python
from code_harness.plugins.builtins import builtin_analyzers
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.review.acp import AcpCommand, AcpReviewAgent
from code_harness.review.contracts import ReviewGuideline
from code_harness.review.rules import PromptReviewRule
from code_harness.source import Language

agent = AcpReviewAgent(AcpCommand(
    executable="/absolute/path/to/acp-agent",
    arguments=("--acp",),
    timeout_seconds=120.0,
))
rule = PromptReviewRule(
    name="project.ownership_review",
    guideline=ReviewGuideline(
        rule_id="review.ownership",
        objective="Review mutable state ownership and lifecycle boundaries",
        instructions=(
            "Identify concrete state with multiple mutation or cleanup owners.",
            "Explain the conflicting ownership using exact source locations.",
            "Mark the review incomplete when required caller evidence is absent.",
        ),
    ),
    agent=agent,
)
analyzers = {item.definition.language: item for item in builtin_analyzers()}
analyzer = analyzers[Language.PYTHON]
analyzer.bundles.register(rule)
registry = AnalyzerRegistry()
registry.register(analyzer)
```

Pass this registry to `cli.main(arguments, analyzers=registry)` or
`engine.check(source, policy, analyzers=registry)`. An injected registry defines
the application's complete language composition; register additional language
analyzers when those sources must be included. Async integrations can call
`AcpReviewAgent.review_async`; the synchronous rule entry point explicitly rejects
execution inside an already running event loop.

## Invocation boundaries

The adapter starts the configured executable directly, without a shell. It uses
an isolated temporary working directory and sends the snapshot through the prompt.
It advertises no filesystem or terminal capabilities and denies ACP permission
requests. Configure the chosen agent to allow the two local submission tools
without interactive approval; this client never grants arbitrary tool permission
based on an untrusted tool title. Authentication must already be configured for
the chosen ACP executable.

The process group is terminated and reaped on completion, failure, cancellation,
or timeout. The adapter currently requires POSIX process groups and file locking.
A temporary directory and denied client capabilities are not an operating-system
sandbox: the configured executable is trusted and must itself enforce read-only
behavior for any native tools. Do not configure an unrestricted editing agent for
a read-only gate. The adapter's own writes are limited to its temporary review
journal; the source repository and Git index are never written.

Review guidelines and source text remain distinct typed data until the actual
outbound prompt boundary. The prompt marks source comments and strings as
untrusted evidence. Agent findings still require semantic judgment: structural
validation proves location and rule ownership, not that the reported violation
is true. Review outcomes may be nondeterministic.

## Validation

The integration fixture is a real ACP subprocess that negotiates a session,
starts the advertised MCP subprocess, lists tools, submits findings, and finishes
the review. It covers small receipts, retry deduplication, 100 incremental
findings with a short acknowledgement, empty final chat, clean completion,
transport failures, timeout cleanup, and the production CLI. It does not call a
live model or certify compatibility with any particular third-party agent.

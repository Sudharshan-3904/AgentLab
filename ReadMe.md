# Local AI Harness

## 1. Project Overview

Local AI Harness is a local-first execution, observability, security, and experimentation platform for AI-assisted work.

The system is designed around a single logical agent execution that can dynamically switch between specialized skill suites and models while preserving task continuity. It is intended for practical tasks such as:

- software development
- debugging
- research
- documentation
- testing
- analysis
- local application generation

The primary design goal is **effective local execution under real hardware constraints**.

The harness does not merely send prompts to a model. It owns the execution lifecycle, controls tools and permissions, records the complete trajectory, monitors system resources, manages the workspace, supports recovery, and can optionally turn an execution into a reproducible benchmark/audit package.

## 2. Core Idea

The central abstraction is:

> One logical execution + one active skill suite at a time + dynamically routed local models + controlled tools + complete execution telemetry.

Instead of maintaining several permanently loaded agents:

```text
Planner Agent
Coder Agent
Tester Agent
Research Agent
```

the harness uses:

```text
Logical Execution
        |
        +-- Conversation / execution state
        |
        +-- Active Skill Suite
        |
        +-- Model Route
        |
        +-- Tools
        |
        +-- Context
```

A skill transition replaces the complete active skill suite while retaining a compact conversation/execution summary so that the execution does not lose continuity.

## 3. Design Goals

1. Local-first execution.
2. Zero mandatory paid API dependency.
3. Support Ollama and LM Studio initially.
4. Support single-agent and multi-agent-like workflows through skill switching.
5. Allow model routing during a single execution.
6. Provide user-selectable autonomy levels.
7. Capture complete execution trajectories.
8. Measure system resources during execution.
9. Provide controlled tool execution and sandboxing.
10. Provide rollback-capable workspace management.
11. Support interactive application testing.
12. Provide a benchmark/audit mode for advanced users.
13. Make executions reproducible through a reproducibility profile.
14. Provide an extensible architecture for future security research.

## 4. Non-Goals for MVP

The MVP will not attempt to:

- support every model provider
- guarantee perfect deterministic LLM execution
- provide enterprise-grade sandbox security
- build a complete browser automation platform
- provide distributed execution
- automatically generate arbitrary harness components
- implement every possible agent architecture
- replace a full IDE
- make universal claims about model quality

## 5. User Modes

### Normal Mode

The user submits a task and interacts with the running execution.

The UI prioritizes:

- task
- current status
- files
- model/skill activity
- application preview
- user feedback

### Advanced Mode

Advanced users can enable detailed instrumentation.

The system records:

- execution trajectory
- model calls
- token metrics
- tool calls
- skill transitions
- context transitions
- resource metrics
- security events
- file changes
- tests
- recovery events
- environment metadata

The execution can then be exported as an audit/benchmark package.

## 6. Autonomy

Autonomy is a user-selectable setting.

The conceptual policy model is:

```text
ALLOW
DENY
ASK USER
```

Potential levels:

### Restricted

High-risk actions require confirmation.

### Balanced

Routine development operations are automatic; sensitive actions require confirmation.

### Autonomous

The harness permits configured operations without repeated confirmation.

The exact policy matrix is configuration-driven and should remain visible to the user.

## 7. Execution Lifecycle

```text
User Input
    |
    v
Prompt Injection / Input Processing
    |
    v
Task Intake
    |
    v
Scratchpad
    |
    v
Planning
    |
    +---- user clarification if required
    |
    v
Skill Selection
    |
    v
Model Routing
    |
    v
Tool / File Execution
    |
    v
Verification
    |
    +---- failure --> Recovery
    |
    v
Application Testing
    |
    v
Completion
    |
    v
Evaluation
    |
    v
Optional Advanced Report
```

Every meaningful transition produces an event in the execution ledger.

## 8. Model Providers

### MVP

- Ollama
- LM Studio

### Roadmap

- OpenAI-compatible endpoints
- OpenAI
- Anthropic
- other local runtimes

The model layer must be provider-independent.

## 9. Model Routing

Model routing means the model can change while the logical execution remains the same.

Example:

```text
Planning  -> Model A
Coding    -> Model B
Testing   -> Model C
Debugging -> Model B
```

A model switch does not create a new logical agent.

## 10. Skill Suites

A skill suite is a complete behavioral package used by the logical agent for a particular execution phase.

Examples:

- planning
- coding
- testing
- debugging
- research
- documentation

When switching skills, the complete previous suite is unloaded and the new suite is loaded.

A continuity summary is passed forward.

## 11. Tools

Initial tools may include:

- filesystem read/write
- shell execution
- Git
- test execution
- process management
- application launch
- workspace inspection

Every tool request passes through the policy layer before execution.

## 12. Workspace

Git is the initial rollback mechanism.

A useful execution pattern is:

```text
checkpoint
    |
agent modification
    |
test
    |
checkpoint / rollback
```

## 13. Application Testing

For coding tasks, the harness can:

1. build the project
2. launch it in a monitored environment
3. expose it to the user
4. collect user feedback
5. return the feedback to the execution
6. continue or recover

The MVP should focus on local web applications and simple interactive application testing.

## 14. System Monitoring

The harness records, where hardware/software support exists:

- CPU utilization
- CPU time
- RAM usage
- GPU utilization
- VRAM usage
- power draw
- temperature
- disk I/O
- network I/O
- process count
- execution duration

## 15. Agent Metrics

The harness records:

- task success
- execution steps
- model calls
- prompt/output token counts when available
- tokens per second when available
- tool calls
- tool failures
- skill switches
- model switches
- retries
- recovery events
- user interventions
- verification results

## 16. Evaluation

The MVP focuses on execution effectiveness and efficiency.

Important measures include:

- task completion
- token efficiency
- time efficiency
- tool efficiency
- system-resource efficiency

Token count is not treated as a standalone definition of quality.

## 17. Advanced Report

Advanced users can enable report generation.

The report is intended to be an auditable execution artifact rather than a simple chat transcript.

A future report package may contain:

```text
experiment/
├── config.yaml
├── execution.jsonl
├── trajectory.json
├── metrics.json
├── environment.json
├── model.json
├── security-events.json
├── git-diff.patch
└── system-card.pdf
```

The report can optionally be generated by a local LLM using deterministic raw telemetry as input.

## 18. Reproducibility

The harness uses a reproducibility profile containing:

- seed
- model name
- model version
- quantization
- runtime/provider
- temperature
- top-p
- other sampling parameters
- harness version
- dependency versions
- hardware information
- execution configuration
- concurrency

A seed is one component of reproducibility, not a guarantee of bit-identical execution.

## 19. Security Research Direction

Security is a first-class future direction.

Potential areas:

- prompt injection
- malicious tool output
- filesystem escape
- network access
- credential exposure
- data exfiltration
- privilege escalation
- malicious code execution
- resource exhaustion
- cross-skill contamination
- cross-execution isolation

The MVP should establish policy enforcement and basic sandboxing without claiming that it is a perfect security boundary.

## 20. Technology Direction

Current recommendation:

- Python
- FastAPI
- Pydantic
- LangGraph
- Ollama
- LM Studio
- SQLite
- JSONL
- Git
- Docker
- psutil
- NVML/pynvml
- React
- Vite
- WebSocket/SSE
- pytest

LangGraph should be treated as an orchestration adapter rather than the foundation of the entire harness.

## 21. Repository Concept

```text
local-ai-harness/
├── harness/
│   ├── core/
│   ├── execution/
│   ├── tasks/
│   ├── planning/
│   ├── skills/
│   ├── context/
│   ├── agents/
│   ├── models/
│   ├── tools/
│   ├── sandbox/
│   ├── workspace/
│   ├── security/
│   ├── monitoring/
│   ├── ledger/
│   ├── evaluation/
│   └── experiments/
├── providers/
│   ├── ollama/
│   └── lmstudio/
├── skills/
├── configs/
├── experiments/
├── reports/
├── ui/
├── tests/
└── docs/
```

## 22. Project Philosophy

The project should remain:

- local-first
- transparent
- measurable
- reproducible
- extensible
- security-conscious
- hardware-aware
- experiment-friendly

The harness should make AI execution observable without turning the system into a black box.

## 23. Quickstart & Launching AgentLab

To launch AgentLab with all default settings:

```bash
python main.py
```

### Common Launch Commands

```bash
# Launch with automated browser open
python main.py --open-browser

# Launch with custom host, port, and provider model
python main.py --host 127.0.0.1 --port 8000 --provider ollama --model llama3.2:latest

# Launch with skill-based model routing
python main.py --routing --planning-model llama3.2:latest --coding-model qwen2.5:1.5b --testing-model llama3.2:latest

# Launch with autonomous execution policy and custom workspace
python main.py --autonomy autonomous --workspace ./workspace --db ./data/ledger.db
```

### Full Parameter Reference

| Parameter | Type / Choices | Default | Description |
|---|---|---|---|
| `--host` | `str` | `127.0.0.1` | Host interface to bind API and Dashboard UI |
| `--port` | `int` | `8000` | Port number to listen on |
| `--open-browser` | flag | `False` | Automatically open default browser on launch |
| `--provider` | `ollama`, `lmstudio` | `ollama` | Primary local LLM inference provider backend |
| `--model` | `str` | `llama3.2:latest` | Primary default model name |
| `--provider-url` | `str` | `None` | Custom base endpoint URL for provider API |
| `--routing` | flag | `True` | Enable dynamic model routing across skills |
| `--no-routing` | flag | | Disable dynamic model routing |
| `--planning-model` | `str` | `--model` | Model specialized for planning phase |
| `--coding-model` | `str` | `--model` | Model specialized for coding phase |
| `--testing-model` | `str` | `--model` | Model specialized for testing phase |
| `--debugging-model` | `str` | `--model` | Model specialized for debugging phase |
| `--autonomy` | `restricted`, `balanced`, `autonomous` | `balanced` | Execution autonomy and safety policy |
| `--max-duration` | `int` | `3600` | Execution timeout limit in seconds |
| `--max-recovery` | `int` | `2` | Max automated self-healing recovery attempts |
| `--temperature` | `float` | `0.2` | LLM sampling temperature |
| `--top-p` | `float` | `0.9` | LLM nucleus sampling probability |
| `--seed` | `int` | `42` | Random seed for reproducibility |
| `--workspace` | `str` | `./workspace` | Workspace directory for agent file operations |
| `--db` | `str` | `./data/ledger.db` | SQLite database path for event ledger & metrics |
| `--sandbox` | `local`, `docker` | `local` | Execution sandbox runtime |
| `--no-git` | flag | `False` | Disable automatic Git tracking in workspace |
| `--config` | `str` | `None` | Path to custom YAML configuration file |
| `-v, --verbose` | flag | `False` | Enable debug-level logging |


# MVP Roadmap

## MVP Objective

Build a usable local coding harness that can execute real development tasks while providing complete execution visibility and basic system monitoring.

The MVP should feel like a lightweight local coding agent rather than a research dashboard.

## Phase 0 — Architecture and Contracts

### Goals

Finalize interfaces before implementation.

### Deliverables

- configuration schema
- execution state machine
- event schema
- model provider interface
- skill interface
- tool interface
- policy interface
- monitoring interface
- evaluation interface

### Exit Criteria

A complete mock execution can flow through the architecture without a real model.

## Phase 1 — Harness Core

Implement:

- Harness object
- Execution Manager
- Task
- Scratchpad
- lifecycle states
- YAML configuration
- SQLite event ledger

### Exit Criteria

The harness can create and persist an execution from task intake through completion using mocked model/tool calls.

## Phase 2 — Local Model Runtime

Implement:

- Ollama adapter
- LM Studio adapter
- streaming
- health checks
- model metadata
- model call recording

### Exit Criteria

A user can run a real local model through the harness.

## Phase 3 — Skill Runtime

Initial skill suites:

- Planning
- Coding
- Testing
- Debugging

Implement:

- skill loading
- skill unloading
- continuity summary
- context rehydration
- skill transition events

### Exit Criteria

One execution can move:

```text
Planning -> Coding -> Testing -> Debugging
```

without losing task continuity.

## Phase 4 — Tool Runtime

Initial tools:

- read file
- write file
- list files
- shell
- Git
- test runner

Implement:

- request/response correlation
- policy checks
- event recording
- tool errors

### Exit Criteria

The model can safely perform basic coding tasks.

## Phase 5 — Workspace and Rollback

Implement:

- Git initialization
- checkpoints
- diff
- rollback
- changed-file tracking

### Exit Criteria

A failed execution can be reverted to a known checkpoint.

## Phase 6 — Sandbox

Implement:

- Docker execution
- workspace mounting
- basic resource limits
- network policy
- process lifecycle

### Exit Criteria

Generated code can execute inside a controlled environment.

## Phase 7 — Monitoring

Implement:

- CPU
- RAM
- process metrics
- GPU
- VRAM
- power where available
- temperature where available

### Exit Criteria

The user can see live system resource usage during an execution.

## Phase 8 — Model Routing

Implement:

- model registry
- route configuration
- model selection
- model transition
- route telemetry

Example:

```text
Planning -> reasoning model
Coding -> coding model
Testing -> fast model
```

### Exit Criteria

A single execution can switch models without creating a new logical execution.

## Phase 9 — Application Testing

Implement:

- application detection
- build
- launch
- health check
- local port exposure
- user feedback

### Exit Criteria

The user can interact with a generated local web application and return feedback to the execution.

## Phase 10 — Recovery

MVP strategy:

1. capture error
2. capture relevant conversation
3. append failure to scratchpad
4. resend to model
5. retry once

### Exit Criteria

Basic failures can automatically recover.

## Phase 11 — Lightweight UI

Screens:

- task entry
- execution
- live activity
- workspace
- app preview
- settings

### Exit Criteria

A user can execute a coding task without interacting directly with the Python runtime.

## Phase 12 — MVP Validation

Use a fixed set of coding tasks.

Measure:

- success rate
- tokens
- execution time
- tool calls
- skill transitions
- model transitions
- CPU
- RAM
- VRAM
- GPU
- power where available

### MVP Completion Criteria

The system can:

1. accept a coding task
2. plan it
3. switch skill suites
4. route models
5. use tools
6. modify files
7. run tests
8. recover once
9. let the user interact with the application
10. monitor resources
11. preserve an execution ledger

## Explicitly Deferred from MVP

- generated harness components
- hot swapping arbitrary components
- advanced security research
- multi-machine execution
- distributed agents
- external paid providers
- full benchmark suite
- automatic system-card generation
- advanced report generation
- sophisticated browser automation

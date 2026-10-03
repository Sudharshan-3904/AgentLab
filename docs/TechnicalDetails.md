# Technical Details

## 1. Configuration

Initial harness configuration is YAML.

```yaml
harness:
    name: local-coding-harness
    version: 0.1

execution:
    autonomy: balanced
    max_duration_seconds: 3600
    max_recovery_attempts: 1

model:
    default_provider: ollama
    default_model: llama3.2

routing:
    enabled: true

sampling:
    temperature: 0.2
    top_p: 0.9
    seed: 42

workspace:
    root: ./workspace
    git_enabled: true

sandbox:
    runtime: docker
    network: false

monitoring:
    cpu: true
    ram: true
    gpu: true
    vram: true
    power: true
    temperature: true

reporting:
    advanced_mode: false
```

## 2. Reproducibility Profile

A reproducibility profile should be generated for every benchmark execution.

```yaml
reproducibility:
    seed: 42

model:
    provider: ollama
    name: llama3.2
    version: unknown
    quantization: unknown

sampling:
    temperature: 0.2
    top_p: 0.9

runtime:
    harness_version: 0.1
    python_version: ...
    os: ...
    backend_version: ...

hardware:
    cpu: ...
    ram_gb: ...
    gpu: ...
    vram_gb: ...

execution:
    concurrency: 1
```

## 3. Event Schema

All execution events should have:

```json
{
    "event_id": "...",
    "execution_id": "...",
    "timestamp": "...",
    "type": "...",
    "source": "...",
    "payload": {}
}
```

Recommended event categories:

- TASK_RECEIVED
- TASK_DECOMPOSED
- CLARIFICATION_REQUESTED
- SKILL_LOADED
- SKILL_UNLOADED
- MODEL_SELECTED
- MODEL_REQUEST
- MODEL_RESPONSE
- TOOL_REQUEST
- TOOL_POLICY_DECISION
- TOOL_RESPONSE
- FILE_CHANGE
- CHECKPOINT
- ROLLBACK
- TEST_STARTED
- TEST_RESULT
- USER_FEEDBACK
- ERROR
- RECOVERY_STARTED
- RECOVERY_COMPLETED
- RESOURCE_SAMPLE
- SECURITY_EVENT
- EXECUTION_COMPLETED

## 4. Tool Request/Response Pairing

Every request should have a correlation ID.

```text
tool_request_id
   |
   +-- request
   |
   +-- policy decision
   |
   +-- execution
   |
   +-- response
```

This allows latency and failure analysis.

## 5. Model Call Schema

```json
{
    "call_id": "...",
    "execution_id": "...",
    "provider": "ollama",
    "model": "llama3.2:latest",
    "temperature": 0.2,
    "top_p": 0.9,
    "seed": 42,
    "started_at": "...",
    "completed_at": "...",
    "prompt_tokens": 1234,
    "output_tokens": 567,
    "duration_ms": 12000
}
```

Token metrics must be marked unavailable if the provider cannot provide reliable counts.

## 6. Skill Transition

A transition should create:

```text
SKILL_UNLOAD
   |
CONVERSATION_SUMMARY
   |
SKILL_LOAD
   |
CONTEXT_REHYDRATION
```

The summary should preserve:

- current objective
- completed work
- pending work
- relevant decisions
- constraints
- discovered information
- known failures
- next verification step

It should not blindly copy the complete previous context.

## 7. Context Modeler

The Context Modeler decides what enters the model context.

Possible sources:

- user prompt
- scratchpad
- continuity summary
- relevant files
- tool output
- test output
- project rules
- active skill
- security policy

The context modeler should record a manifest of included context.

## 8. System Metrics

Sampling should occur at a configurable interval.

```yaml
monitoring:
    interval_ms: 500
```

Metrics:

### CPU

- utilization
- user time
- system time

### Memory

- RSS
- system RAM used
- system RAM available

### GPU

- utilization
- VRAM used
- VRAM free
- power draw
- temperature

### Process

- process CPU
- process memory
- child processes

## 9. Power Measurement

Power draw availability depends on hardware.

NVIDIA GPUs may expose power telemetry through NVML.

CPU package power depends heavily on platform.

The system should therefore record:

```text
available
unavailable
unsupported
```

rather than inventing values.

## 10. Scratchpad Schema

```json
{
    "objective": "...",
    "constraints": [],
    "assumptions": [],
    "subtasks": [],
    "verification": [],
    "clarifications": [],
    "completed": [],
    "failed": [],
    "pending": []
}
```

## 11. Workspace State

Workspace state should be associated with:

```text
execution_id
git_commit
modified_files
created_files
deleted_files
checkpoint
```

## 12. Recovery

MVP recovery is deliberately simple:

```text
Failure
  |
capture failure context
  |
append to scratchpad
  |
resend relevant failed conversation/context
  |
retry
```

Recovery attempts must be recorded.

Future recovery can use:

- rollback
- alternate skill
- alternate model
- modified context
- diagnosis
- strategy change

## 13. Testing Environment

The testing manager should expose:

```text
Application
   |
Docker container
   |
mapped local port
   |
UI preview
```

The harness records:

- startup time
- health status
- process state
- logs
- exit status
- user feedback

## 14. Evaluation Metrics

The harness should separate raw metrics from derived metrics.

### Raw

- token count
- time
- CPU
- RAM
- VRAM
- power
- tool calls

### Derived

- tokens/minute
- tokens/success
- resource peak
- resource average
- model-call success rate
- tool success rate
- recovery rate
- execution efficiency

## 15. Benchmark Definition

```yaml
benchmark:
    name: coding-basic-v1
    version: 1

tasks:
    - id: task-001
      prompt: ...
    - id: task-002
      prompt: ...

execution:
    repetitions: 10
    seed: 42

models:
    - llama3.2
    - qwen-coder

evaluation:
    success: test_pass
```

## 16. Report Generation

```text
Raw Events
   |
Normalizer
   |
Metric Engine
   |
Experiment Summary
   |
Local LLM (optional)
   |
System Card / Technical Report
```

The LLM receives structured raw data and should not be responsible for calculating primary measurements.

## 17. Audit Package

```text
audit-package/
├── manifest.json
├── config.yaml
├── reproducibility.yaml
├── execution.jsonl
├── trajectory.json
├── metrics.json
├── security.json
├── environment.json
├── model.json
├── workspace.diff
└── report.pdf
```

## 18. Database

SQLite is appropriate for MVP because it is:

- local
- zero-cost
- transactional
- queryable
- portable
- easy to back up

JSONL should be retained for event-stream portability and audit purposes.

## 19. UI

React + Vite.

Initial screens:

1. Task
2. Execution
3. Workspace
4. Live activity
5. Application preview
6. Settings
7. Execution history
8. Benchmark results

## 20. API

```text
POST /executions
GET  /executions/{id}
POST /executions/{id}/feedback
POST /executions/{id}/cancel
GET  /executions/{id}/events
GET  /executions/{id}/metrics
GET  /executions/{id}/export
POST /benchmarks
GET  /benchmarks/{id}
```

## 21. Testing Strategy

### Unit tests

- configuration
- policy
- routing
- event schema
- scratchpad
- skill manager

### Integration tests

- Ollama
- LM Studio
- Docker
- Git
- monitoring

### Harness tests

- complete coding task
- tool denial
- user confirmation
- model switching
- skill switching
- recovery
- rollback

### Benchmark tests

- repeatability
- metric collection
- export validity

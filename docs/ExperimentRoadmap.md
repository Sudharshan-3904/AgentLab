# Experiment Roadmap

## 1. Purpose

The experiment program is a parallel research track for the Local AI Harness.

Each experiment should produce:

1. implementation/configuration
2. controlled execution
3. raw telemetry
4. analysis
5. technical report
6. public-facing blog/article
7. reproducibility package

The blog is not the primary evidence. The execution data is.

## 2. Standard Experiment Structure

```text
Question
   |
Hypothesis
   |
Variables
   |
Controlled Configuration
   |
Task Suite
   |
Repeated Execution
   |
Raw Telemetry
   |
Statistical / Technical Analysis
   |
Conclusion
   |
Blog
```

## 3. Experiment Manifest

```yaml
experiment:
  id: EXP-001
  name: ...
  version: 1

question: ...

hypothesis: ...

variables:
  independent: []
  dependent: []
  controlled: []

models: []

skills: []

tasks: []

execution:
  repetitions: 10
  seed: 42

evaluation:
  metrics: []

environment:
  hardware: ...
```

## 4. EXP-000 — Harness Baseline

### Objective

Establish the baseline overhead introduced by the harness itself.

### Compare

```text
Direct Ollama call
vs
Harness-managed execution
```

### Measure

- latency overhead
- CPU overhead
- RAM overhead
- additional model calls
- token overhead
- event logging overhead

This is important because a performance harness should quantify its own cost.

## 5. EXP-001 — Single Agent vs Skill-Switched Agent

### Question

Does dynamically switching skill suites provide specialization without the resource cost of multiple resident agents?

### Configurations

A. Single generic skill

B. Skill-switched execution:

```text
Planning
Coding
Testing
Debugging
```

### Metrics

- success
- tokens
- latency
- RAM
- VRAM
- model calls
- context size
- skill transition overhead

### Blog

> Can One Local AI Agent Behave Like Multiple Specialized Agents?

## 6. EXP-002 — Model Routing

### Question

Does dynamic model routing improve execution efficiency?

### Example

```text
Planning -> Model A
Coding -> Model B
Testing -> Model C
```

Compare with:

```text
Single model for entire execution
```

### Metrics

- task success
- tokens
- latency
- VRAM
- RAM
- model switching overhead

### Blog

> Does Using Multiple Local Models Beat Using One Model for Everything?

## 7. EXP-003 — Context Compression

### Question

How does continuity-summary-based skill switching affect token usage and task effectiveness?

### Compare

A. Full conversation retained

B. Conversation summary retained

C. Summary + scratchpad

### Metrics

- input tokens
- output tokens
- context size
- success
- latency
- memory
- recovery rate

## 8. EXP-004 — Autonomy Levels

### Question

How do different autonomy policies affect productivity and execution characteristics?

### Configurations

- Restricted
- Balanced
- Autonomous

### Measure

- user interventions
- execution duration
- tool calls
- blocked actions
- task completion
- security events

The experiment should avoid treating higher autonomy as inherently better.

## 9. EXP-005 — Harness Resource Overhead

### Question

What system overhead does the harness itself introduce?

Compare:

```text
Model only
Model + basic agent
Model + harness
Model + harness + monitoring
Model + harness + monitoring + ledger
```

Measure:

- RAM
- CPU
- GPU
- VRAM
- latency
- disk writes

## 10. EXP-006 — Recovery Strategies

### MVP

```text
Failure -> resend failed conversation
```

Future variants:

- rollback + retry
- alternate model
- alternate skill
- context reduction
- error diagnosis

### Metrics

- recovery success
- recovery time
- extra tokens
- resource cost
- final task success

## 11. EXP-007 — Tool Efficiency

### Question

How does tool design affect local agent performance?

Compare:

- coarse tools
- fine-grained tools
- combined tools

Measure:

- tool calls
- model calls
- tokens
- latency
- failure rate

## 12. EXP-008 — Coding Agent Scaling

### Objective

Study how execution cost changes with task complexity.

Task categories:

- simple modification
- bug fix
- feature implementation
- multi-file change
- application creation

Measure:

- tokens
- time
- CPU
- RAM
- VRAM
- tool calls
- recovery

## 13. EXP-009 — Security Baseline

### Objective

Establish the baseline attack surface of the coding harness.

Test:

- malicious shell commands
- path traversal
- destructive file operations
- secret access
- network access
- malicious tool output
- prompt injection in repository files

Record:

- attack type
- attempted action
- policy response
- sandbox response
- final outcome

Do not claim security merely because an attack was blocked once. Treat this as an empirical test suite.

## 14. EXP-010 — Prompt Injection Resistance

### Test Sources

- README
- source comments
- generated files
- test output
- tool output
- external content where enabled

Compare:

```text
No security layer
Policy layer
Policy + sandbox
Policy + sandbox + input handling
```

Measure attack success and false positives.

## 15. EXP-011 — Resource-Constrained Execution

Run the same tasks under controlled limits:

```text
CPU limit
RAM limit
VRAM availability
process limit
time limit
```

Study:

- graceful degradation
- failure modes
- recovery
- model routing
- task success

## 16. EXP-012 — Skill Suite Hot Swapping

Future feature.

Compare:

```text
Static skill
Dynamic skill switch
Hot-swapped skill
```

Measure:

- transition overhead
- context size
- token cost
- success
- memory footprint

## 17. EXP-013 — Dynamic Harness Component Generation

Future feature.

Generate components such as:

- skill
- tool
- guideline
- context modeler

Compare manually authored vs generated components.

Important measurements:

- generation cost
- validation failures
- runtime failures
- task improvement
- security issues

## 18. EXP-014 — Benchmarking the Harness Against Itself

The harness should eventually be capable of comparing configurations.

Example:

```text
Configuration A
Qwen + Coding Skill + Basic Policy

vs

Configuration B
Qwen + Model Routing + Dynamic Skills + Balanced Policy
```

The harness produces the comparison automatically.

## 19. Blog Pipeline

Every experiment should generate two artifacts.

### Technical Artifact

Contains:

- raw configuration
- raw data
- methodology
- metrics
- environment
- analysis
- limitations

### Public Blog

Contains:

1. Problem
2. Why the experiment matters
3. Setup
4. Hypothesis
5. Method
6. Results
7. Interpretation
8. Surprising findings
9. Limitations
10. Reproduction instructions
11. Conclusion

The blog must not hide negative results.

Failed hypotheses are useful research outcomes.

## 20. Experiment Naming

```text
EXP-000-baseline
EXP-001-skill-switching
EXP-002-model-routing
EXP-003-context-compression
EXP-004-autonomy
EXP-005-harness-overhead
EXP-006-recovery
EXP-007-tool-efficiency
EXP-008-coding-scaling
EXP-009-security-baseline
EXP-010-prompt-injection
EXP-011-resource-constraints
EXP-012-hot-swap
EXP-013-component-generation
```

## 21. Reproducibility Package

Every completed experiment should produce:

```text
experiment/
├── README.md
├── config.yaml
├── benchmark.yaml
├── environment.json
├── model.json
├── execution/
│   ├── *.jsonl
│   └── trajectory.json
├── metrics/
│   ├── raw.json
│   └── summary.json
├── analysis/
│   └── analysis.md
├── report/
│   └── report.md
└── blog/
    └── blog.md
```

## 22. Research Principles

1. Change one major variable at a time where practical.
2. Preserve a control/baseline.
3. Repeat experiments.
4. Record environment information.
5. Record model configuration.
6. Separate raw measurements from interpretation.
7. Report limitations.
8. Do not discard failures.
9. Do not rely solely on LLM-generated evaluation.
10. Make experiment configurations reproducible.

## 23. Long-Term Research Questions

### Local Efficiency

> How can agentic systems maximize task completion per unit of local compute?

### Model Routing

> When is switching local models worth the transition cost?

### Skill Switching

> Can one model with dynamically loaded skills approximate the specialization benefits of multiple agents?

### Context

> How much context is necessary for reliable long-running execution?

### Security

> What attack surface does a locally executing coding agent expose?

### Harness Overhead

> How much overhead does observability and control add to an agent runtime?

### Resource Awareness

> Can an agent adapt its execution strategy to available hardware resources?

### Dynamic Components

> Can a harness generate and safely deploy its own execution components?

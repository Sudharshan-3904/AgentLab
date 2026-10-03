# Architecture

## 1. Architectural Principle

The harness owns the execution lifecycle.

Frameworks such as LangGraph are implementation components inside the harness, not the architectural authority.

```text
                    USER
                     |
                     v
              +-------------+
              | UI / Client |
              +------+------+
                     |
                     v
              +-------------+
              | Harness API |
              +------+------+
                     |
                     v
        +---------------------------+
        |       Harness Core        |
        |                           |
        | Task / Planning           |
        | Skill Management          |
        | Model Routing             |
        | Context Management        |
        | Policy / Security         |
        | Workspace                 |
        | Recovery                  |
        | Evaluation                |
        +---+---------+---------+---+
            |         |         |
            v         v         v
         Model      Tools     Sandbox
        Runtime    Runtime    Runtime
            |         |         |
            +---------+---------+
                      |
                      v
                Event / Ledger
                      |
             +--------+--------+
             |                 |
             v                 v
        Live Monitor      Reports /
                          Experiments
```

## 2. Core Components

### 2.1 Harness Core

Owns:

- lifecycle
- execution IDs
- configuration
- task state
- scratchpad
- planning
- skill transitions
- model routing
- recovery
- evaluation
- event generation

### 2.2 Harness API

FastAPI exposes:

- create execution
- submit task
- update user feedback
- inspect execution state
- stream events
- manage workspace
- launch testing environment
- export execution

WebSocket or SSE is used for live execution updates.

### 2.3 Execution Manager

The execution manager is the central state machine.

```text
CREATED
  |
INTAKE
  |
PLANNING
  |
EXECUTING
  |
VERIFYING
  |   |  RECOVERY
  |     |
  |     +--> EXECUTING
  |
TESTING
  |
COMPLETED
```

Failure and cancellation are first-class states.

### 2.4 Task Intake

Converts user input into an internal task object.

The input processing stage identifies:

- objective
- constraints
- requested output
- project context
- explicit user preferences
- potential clarification requirements

Prompt-injection resistance is part of the intake/security roadmap.

### 2.5 Scratchpad

The scratchpad is the execution's structured state.

It contains:

- objective
- constraints
- subtasks
- verification criteria
- assumptions
- discovered facts
- pending questions
- completed tasks
- failures
- recovery information

The scratchpad should be stored outside the model context so it remains inspectable.

### 2.6 Planner

The planner:

- decomposes tasks
- creates execution order
- identifies verification points
- identifies clarification points
- determines likely skill requirements
- can request user clarification

The planner should use an interface so multiple implementations can exist.

### 2.7 Skill Manager

The Skill Manager maintains exactly one active skill suite for the MVP.

A transition:

```text
Active Suite A
      |
summary generation
      |
unload
      |
load Suite B
      |
inject continuity summary
```

The full previous skill suite is replaceable without losing task continuity.

### 2.8 Model Router

The Model Router selects the inference backend/model based on execution requirements.

Example:

```text
Task phase -> Model route

Planning  -> reasoning model
Coding    -> coding model
Testing   -> fast model
Debugging -> coding/reasoning model
```

The router records:

- selected provider
- model
- configuration
- selection reason
- start/end time

### 2.9 Model Provider Interface

```python
class ModelProvider:
    def generate(...)
    def stream(...)
    def health(...)
    def metadata(...)
```

Initial implementations:

- Ollama
- LM Studio

Future implementations:

- OpenAI
- Anthropic
- generic OpenAI-compatible APIs

### 2.10 Tool Manager

Every tool invocation follows:

```text
Model request
    |
Tool request
    |
Policy evaluation
    |
ALLOW / DENY / ASK
    |
Sandbox execution
    |
Tool result
    |
Ledger
```

Tool requests and responses are paired.

### 2.11 Policy Engine

The user chooses an autonomy level.

The policy engine resolves whether an operation is:

- allowed
- denied
- confirmation-required

Policy should consider:

- tool
- target
- path
- command
- network
- process
- resource requirements
- current autonomy level

### 2.12 Sandbox

The MVP uses Docker-based isolation.

The sandbox should provide:

- workspace mount
- controlled network
- process boundary
- resource limits where practical
- application launch environment

Security claims must remain conservative.

### 2.13 Workspace Manager

Git is the initial rollback mechanism.

The Workspace Manager tracks:

- current revision
- modified files
- checkpoints
- diff
- rollback events

### 2.14 Testing Manager

Responsible for:

- build
- launch
- health check
- user interaction endpoint
- feedback collection
- shutdown

For MVP, local web applications are the primary target.

### 2.15 Monitoring Manager

Collects:

#### Hardware

- CPU
- RAM
- GPU
- VRAM
- power
- temperature

#### Process

- CPU time
- memory
- process count
- child processes

#### I/O

- disk
- network

### 2.16 Event Ledger

SQLite stores structured event metadata.

JSONL can provide an append-only event stream.

Example event:

```json
{
  "execution_id": "exec-001",
  "timestamp": "...",
  "type": "TOOL_REQUEST",
  "source": "coding_skill",
  "tool": "shell",
  "request": {
    "command": "pytest"
  }
}
```

### 2.17 Evaluation Engine

The evaluation engine derives deterministic metrics from raw events.

Examples:

- total execution time
- model time
- tool time
- verification time
- token count
- model calls
- skill switches
- tool calls
- retries
- resource averages
- resource peaks
- task completion

### 2.18 Report Generator

Report generation is optional.

The deterministic layer prepares the dataset.

A local model may then generate narrative analysis.

The generated report must distinguish:

- measured facts
- derived metrics
- model-generated interpretation

## 3. Data Flow

```text
User
 |
 v
Input
 |
 v
Task
 |
 v
Scratchpad
 |
 v
Planner
 |
 v
Skill + Model Router
 |
 +--> Model Request --> Model
 |
 +--> Tool Request --> Policy --> Sandbox --> Tool Result
 |
 +--> Context Update
 |
 v
Verification
 |
 +--> Recovery
 |
 v
Completion
 |
 v
Evaluation
 |
 +--> Normal result
 |
 +--> Advanced report
```

## 4. Logical Execution vs Physical Processes

A logical agent execution does not imply a separate model process.

The same execution can route through multiple models and multiple skill suites.

This is central to local resource efficiency.

## 5. Future Dynamic Component System

Future harness components:

- skills
- tools
- guidelines
- context modelers
- policies
- evaluators
- model routers

will be represented as loadable components.

The component manager will eventually support runtime hot swapping.

## 6. Security Boundary

The security model has several layers:

```text
User
 |
Harness
 |
Policy
 |
Sandbox
 |
Tool
 |
Host
```

The harness should never assume that model output is trusted.

## 7. Recommended Dependency Boundaries

```text
Core
 ├── does not depend on UI
 ├── does not depend directly on Ollama
 └── does not depend directly on LangGraph

Adapters
 ├── LangGraph
 ├── Ollama
 ├── LM Studio
 └── Docker

UI
 └── talks to API only
```

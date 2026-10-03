# AgentLab Frontend Dashboard

The lightweight, standalone web interface for the Local AI Coding Harness.

## Features
- **Task Entry**: Create and configure autonomous coding executions.
- **Execution Monitor**: Real-time lifecycle states, scratchpad viewer, active skill suite, and active model.
- **Workspace**: View git checkpoints, revisions, and diffs.
- **Live Activity**: Real-time event stream from the execution ledger with JSONL export.
- **App Preview**: Live iframe preview of launched local applications with feedback and rating submission.
- **Settings**: Local model selection, routing rules, sampling temperature.
- **History & Benchmarks**: Historical execution logs and benchmark performance results.

## Usage
Served automatically by the AgentLab backend API server (`backend/harness/ui/server.py`) at `http://127.0.0.1:8000/`.
Can also be previewed by opening `index.html` in any modern web browser or served via any static HTTP server.

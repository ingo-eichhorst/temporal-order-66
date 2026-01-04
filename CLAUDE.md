# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a multi-agent crash recovery demonstration system using Temporal workflows and the Agent-to-Agent (A2A) protocol. The system proves that Temporal provides durability guarantees for agent communication even when agents crash mid-conversation.

**Core Demo**: Agent A sends 3 messages to Agent B. Message 3 triggers a crash (`sys.exit(1)`) in Agent B, which then recovers automatically via Docker restart and Temporal workflow replay, continuing processing with no data loss or duplicates.

## Architecture

### Two-Agent System

- **Agent A** (TypeScript/Node.js): Initiator agent on port 8081
  - Sends 3 messages via A2A protocol
  - Receives replies and signals its Temporal workflow
  - Includes demo driver endpoint on port 8082

- **Agent B** (Python): Responder agent on port 8080
  - Receives A2A messages, processes with LLM (LM Studio)
  - Crashes on message 3 when detecting `[[TRIGGER:EXECUTE_ORDER_66]]`
  - Uses Temporal workflow for durable state and crash recovery
  - Optional Langfuse integration for LLM observability

### Infrastructure Services

- **Temporal Server**: Workflow orchestration (ports 7233 gRPC, 8233 UI)
- **PostgreSQL**: Shared database for Temporal and Langfuse
- **Langfuse** (optional): LLM observability UI on port 3000
- **LM Studio**: External local LLM server (not in docker-compose)

## Common Commands

### Environment Setup

```bash
# Copy environment template and configure LM Studio
cp .env.example .env

# Required: Edit LM_STUDIO_BASE_URL and LM_STUDIO_MODEL in .env
# Optional: Configure Langfuse keys after starting system
```

### Docker Operations

```bash
# Build and start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs (all services or specific agent)
docker-compose logs -f
docker-compose logs -f agent-b

# Restart specific agent
docker-compose restart agent-b

# Stop and remove all services
docker-compose down

# Remove all data (volumes)
docker-compose down -v
```

### Running the Demo

```bash
# Trigger 3-turn conversation with crash at turn 3
curl -X POST http://localhost:8082/start-task \
  -H "Content-Type: application/json" \
  -d '{"taskId": "demo-1", "turns": 3}'

# Check task status
curl http://localhost:8082/status/demo-1

# Manual A2A message to Agent B
curl -X POST http://localhost:8080/a2a/message/send \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "taskId": "test-1",
      "messageId": "m-test",
      "replyTo": "http://agent-a:8081/a2a/message/send",
      "content": "Test message"
    },
    "id": "req-test"
  }'
```

### Agent Development

**Agent A (TypeScript)**:
```bash
cd agent-a

# Install dependencies
npm install

# Build TypeScript
npm run build

# Run locally (requires Temporal running)
npm run dev       # Server only
npm run worker    # Worker only
npm run demo      # Demo driver only
```

**Agent B (Python)**:
```bash
cd agent-b

# Install dependencies
pip install -r requirements.txt

# Run locally (requires Temporal and LM Studio running)
python -m src.server   # FastAPI server
python -m src.worker   # Temporal worker
```

## Key Implementation Patterns

### Crash Recovery Pattern (Agent B)

The crash recovery is implemented in `agent-b/src/workflows/task_workflow.py:inbound_message()`:

1. **Idempotency Check** (line 77): Skip if message already processed
2. **Durable Persist** (line 86): Append to workflow state BEFORE crash detection
3. **Crash Trigger** (line 103): Detect `EXECUTE_ORDER_66` AFTER persist, call `crash_worker` activity
4. **Process Message** (line 126): Call LLM via `process_message` activity
5. **Outbox Pattern** (line 149): Create reply in state with `sent: False`
6. **Send Reply** (line 164): Only send if `sent == False`, then mark `sent: True`

This ensures:
- Messages are never lost (persisted before crash)
- No duplicate sends (outbox pattern prevents replay duplication)
- Deterministic replay (workflow history reconstructs exact state)

### A2A Protocol (JSON-RPC 2.0)

All agent-to-agent messages use this envelope structure:

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "taskId": "demo-1",
    "messageId": "m1",
    "replyTo": "http://agent-a:8081/a2a/message/send",
    "content": "Hello"
  },
  "id": "req-123"
}
```

See `shared/schemas/a2a-message.schema.json` for full JSON schema.

### Temporal Workflow Patterns

**Agent A** (`agent-a/src/workflows/initiator-workflow.ts`):
- Single workflow per task: `initiator-{taskId}`
- Sends messages via `sendA2AMessage` activity
- Receives replies via `replyReceivedSignal` signal
- Exposes state via `getStateQuery` query

**Agent B** (`agent-b/src/workflows/task_workflow.py`):
- Single workflow per task: `task-{taskId}`
- Starts on first message using SignalWithStart pattern in `server.py`
- Receives messages via `inbound_message` signal
- Processes via activities: `crash_worker`, `process_message`, `send_a2a_message`
- Workflow completes after 3 messages (5 min timeout)

### Temporal Configuration

- **Namespace**: `a2a-demo`
- **Task Queues**: `agent-a-tasks`, `agent-b-tasks`
- **Retry Policy** (activities):
  - Initial interval: 1s
  - Backoff coefficient: 2x
  - Maximum interval: 10s
  - Maximum attempts: 3

## File Organization

### Agent A Structure (TypeScript)
```
agent-a/src/
├── workflows/
│   └── initiator-workflow.ts    # Main workflow: sends 3 messages
├── activities/
│   └── send-a2a-message.ts      # HTTP POST to Agent B
├── server.ts                     # A2A endpoint + agent card
├── demo-driver.ts                # Demo trigger endpoint (port 8082)
└── worker.ts                     # Temporal worker process
```

### Agent B Structure (Python)
```
agent-b/src/
├── workflows/
│   └── task_workflow.py          # Main workflow: crash recovery
├── activities/
│   ├── crash_worker.py           # sys.exit(1) trigger
│   ├── process_message.py        # LLM call + Langfuse tracing
│   └── send_a2a_message.py       # Reply to Agent A
├── server.py                      # FastAPI A2A endpoint
└── worker.py                      # Temporal worker process
```

## Environment Variables

**Required** (set in `.env`):
- `LM_STUDIO_BASE_URL`: e.g., `http://host.docker.internal:1234/v1`
- `LM_STUDIO_MODEL`: e.g., `google/gemma-3-1b`

**Optional** (for Langfuse observability):
- `LANGFUSE_PUBLIC_KEY`: Generate from http://localhost:3000 after startup
- `LANGFUSE_SECRET_KEY`: Generate from http://localhost:3000 after startup

**Auto-configured** (in docker-compose.yml):
- `TEMPORAL_SERVER=temporal:7233`
- `TEMPORAL_NAMESPACE=a2a-demo`
- `AGENT_A_URL=http://agent-a:8081`
- `AGENT_B_URL=http://agent-b:8080`
- `LANGFUSE_HOST=http://langfuse:3000`

## Observability

### Temporal UI
- **URL**: http://localhost:8233
- **Workflow ID pattern**: `initiator-{taskId}` or `task-{taskId}`
- **View**: Event History tab shows all signals, activities, and state changes
- **Verify**: Check for 3 `inbound_message` signals and activity completions

### Langfuse UI (Optional)
- **URL**: http://localhost:3000
- **Setup**: Create account → Settings → API Keys → Add to `.env` → Restart agents
- **Search**: Filter by `taskId=demo-1` to see all LLM traces
- **Verify**: Trace for message `m3` exists (proves LLM called post-recovery)

### Docker Logs
- **Structured JSON**: Logs include `taskId`, `messageId`, `event` fields for correlation
- **Key events to watch**:
  - `"event": "inbound_persisted"` - Message durably saved
  - `"event": "crash_triggered"` - Order 66 detected
  - `exit code 1` - Container crash
  - `"Successfully connected to Temporal"` - Post-recovery startup
  - `"event": "reply_sent"` - Reply completed

## Workflow Determinism Rules

Temporal workflows must be **deterministic** to enable replay. When modifying workflows:

1. **Never** use non-deterministic operations in workflow code:
   - No `random()`, `uuid()`, `Date.now()`, or `time.time()`
   - No file I/O, network calls, or external state reads
   - Use `workflow.now()` for timestamps, `workflow.random()` for randomness

2. **Always** use activities for non-deterministic operations:
   - LLM API calls
   - HTTP requests (A2A messages)
   - Database queries
   - External process execution (crash trigger)

3. **State updates** are deterministic and safe:
   - Appending to arrays in workflow state
   - Updating dictionaries
   - Signal handlers modifying state

## A2A Endpoints Reference

### Agent Card Discovery
```bash
curl http://localhost:8081/a2a/.well-known/agent-card  # Agent A
curl http://localhost:8080/a2a/.well-known/agent-card  # Agent B
```

### Message Send
```bash
POST http://localhost:8081/a2a/message/send  # To Agent A
POST http://localhost:8080/a2a/message/send  # To Agent B
```

## Testing Crash Recovery

To verify crash recovery works correctly:

1. **Start demo**: `curl -X POST http://localhost:8082/start-task -H "Content-Type: application/json" -d '{"taskId": "test-1", "turns": 3}'`

2. **Watch Agent B logs**: `docker-compose logs -f agent-b`

3. **Verify sequence**:
   - Message m1 processed → reply r-m1 sent
   - Message m2 processed → reply r-m2 sent
   - Message m3 received → "durably persisted"
   - Crash trigger detected → "EXECUTING ORDER 66"
   - Container exits (code 1)
   - Docker restarts container
   - Temporal replays workflow from history
   - Message m3 processing resumes → reply r-m3 sent
   - **No duplicate sends** (check workflow state in Temporal UI)

4. **Verify in Temporal UI**:
   - Open http://localhost:8233
   - Search workflow: `task-test-1`
   - Event History shows: 3 signals, 9 activities (3 process + 3 send + up to 3 crash attempts)
   - Workflow status: Completed

5. **Check container restart count**:
   ```bash
   docker inspect agent-b | grep RestartCount
   # Should show "RestartCount": 1 or higher
   ```

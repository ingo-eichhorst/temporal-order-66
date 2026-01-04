# A2A + Temporal Multi-Agent Reference System

A demonstration of crash recovery in multi-agent systems using Temporal workflows and the Agent-to-Agent (A2A) communication protocol.

## Overview

This system demonstrates how **Temporal workflows** provide durability guarantees for agent communication even when agents crash mid-conversation. The demo features:

- **Agent A** (TypeScript/Node.js): Initiator agent that sends 3 messages
- **Agent B** (Python): Responder agent that crashes on message 3 and recovers automatically
- **Temporal Server**: Orchestrates workflows with complete durability
- **Langfuse**: Observability for LLM API calls
- **A2A Protocol**: JSON-RPC 2.0 based agent-to-agent messaging

### Core Demo: Crash Recovery

1. Agent A sends message 3 containing `[[TRIGGER:EXECUTE_ORDER_66]]`
2. Agent B receives and **durably persists** the message to Temporal
3. Agent B detects the trigger and **crashes** (via `sys.exit(1)`)
4. Docker restarts the Agent B container
5. Temporal **replays the workflow history** to rebuild state
6. Agent B **continues processing** from where it left off
7. All 3 messages receive responses with **no duplicates** and **no data loss**

## Architecture

```
┌─────────────┐         A2A/HTTP         ┌─────────────┐
│  Agent A    │◄────────────────────────►│  Agent B    │
│  (Port 8081)│     JSON-RPC 2.0         │  (Port 8080)│
│  TypeScript │                          │   Python    │
└──────┬──────┘                          └──────┬──────┘
       │                                        │
       │         Temporal gRPC                  │
       └────────────────┬───────────────────────┘
                        │
                   ┌────▼─────┐
                   │ Temporal │
                   │  Server  │
                   │(Port 7233)│
                   └─────┬────┘
                         │
                   ┌─────▼─────┐
                   │PostgreSQL │
                   └───────────┘

Additional Services:
- Temporal UI: http://localhost:8233
- Langfuse UI: http://localhost:3000
- Demo Driver: http://localhost:8082
```

## Prerequisites

- **Docker** 24+ and **Docker Compose** 2.x
- **LM Studio Local Server**: Run LM Studio with `google/gemma-3-1b` loaded and the API server enabled

## Quick Start

### 1. Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and set your LM Studio connection
nano .env  # or use your preferred editor
```

**Minimum Required Configuration** in `.env`:
```env
LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO_MODEL=google/gemma-3-1b
```

**Optional - Langfuse Observability**:
Langfuse runs locally by default with no external keys needed. If you want to enable LLM tracing:

1. Start the system: `docker-compose up -d`
2. Open Langfuse UI: http://localhost:3000
3. Create an account (data stays local)
4. Generate API keys from Settings → API Keys
5. Add to `.env`:
   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-your-generated-key
   LANGFUSE_SECRET_KEY=sk-lf-your-generated-key
   ```
6. Restart agents: `docker-compose restart agent-a agent-b`

> **Note**: The system works without Langfuse keys, but you won't see LLM traces in the UI.

### 2. Start the System

```bash
# Build and start all services
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# Check logs to verify all services are running
docker-compose logs -f
```

Expected services:
- `postgres` - Shared database for Temporal and Langfuse (port 5432)
- `temporal` - Workflow server (ports 7233, 8233)
- `langfuse` - Observability UI (port 3000)
- `agent-a` - Initiator (ports 8081, 8082)
- `agent-b` - Responder (port 8080)

### 3. Run the Crash Recovery Demo

```bash
# Trigger a 3-turn conversation with crash at turn 3
curl -X POST http://localhost:8082/start-task \
  -H "Content-Type: application/json" \
  -d '{"taskId": "demo-1", "turns": 3}'

# Expected response:
# {
#   "success": true,
#   "taskId": "demo-1",
#   "workflowId": "initiator-demo-1",
#   "message": "Task demo-1 started..."
# }
```

### 4. Observe the Crash and Recovery

#### Monitor Agent B Logs

```bash
# Watch Agent B crash and restart
docker-compose logs -f agent-b

# Look for these key events:
# 1. "Message m3 durably persisted"
# 2. "EXECUTING ORDER 66 - Worker process will now terminate"
# 3. Container restarts
# 4. "Successfully connected to Temporal server" (after restart)
# 5. "Reply r-m3 sent successfully"
```

#### View Temporal UI

Open http://localhost:8233 in your browser:

1. Search for workflow ID: `task-demo-1`
2. View the **Event History** tab
3. Observe all 3 `inbound_message` signals
4. See activity executions (process_message, send_a2a_message)
5. Verify workflow status: **Completed**

#### View Langfuse Traces (Optional)

If you configured Langfuse API keys, open http://localhost:3000 in your browser:

1. Sign in (create account on first visit)
2. Search for `taskId=demo-1`
3. Verify **3 traces** exist (one per message)
4. Check that trace for message `m3` exists (proves LLM called after crash)

> **Note**: If you didn't configure Langfuse keys, you'll see "Langfuse not configured, skipping tracing" in Agent B logs. The system still works perfectly!

#### Check Docker Container Restart

```bash
# View container restart count
docker inspect agent-b | grep RestartCount

# View full crash log
docker-compose logs agent-b | grep -E "exit|restart|crash|ORDER_66"
```

## Validation Checklist

After running the demo, verify these outcomes:

### Functional Requirements

- [ ] Agent A sent 3 messages (m1, m2, m3)
- [ ] Agent B received all 3 messages
- [ ] Agent B crashed on message 3 (logs show `exit code 1`)
- [ ] Docker restarted Agent B container
- [ ] Agent B sent 3 replies (r-m1, r-m2, r-m3)
- [ ] Agent A received all 3 replies
- [ ] No duplicate messages sent (check workflow state in Temporal UI)

### Observability Requirements

- [ ] Temporal UI shows workflow `task-demo-1` completed
- [ ] Event history shows 3 `inbound_message` signals
- [ ] Activity executions visible (process_message × 3, send_a2a_message × 3)
- [ ] Docker logs show structured JSON with correlation IDs

**Optional - If Langfuse configured**:
- [ ] Langfuse shows 3 traces for taskId demo-1
- [ ] Trace for message m3 exists (proves LLM was called post-recovery)

### Durability Requirements

- [ ] Message m3 was persisted before crash (logs show "durably persisted")
- [ ] Workflow replay correctly reconstructed state
- [ ] Outbox pattern prevented duplicate sends
- [ ] All activities completed exactly once

## Project Structure

```
/workspace
├── docker-compose.yml          # Multi-service orchestration
├── .env.example                # Environment template
├── README.md                   # This file
│
├── docker/
│   └── postgres-init.sh        # Creates temporal & langfuse databases
│
├── shared/
│   └── schemas/
│       ├── a2a-message.schema.json    # A2A protocol spec
│       └── agent-card.schema.json      # Agent discovery spec
│
├── agent-a/                    # TypeScript initiator
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── workflows/
│       │   └── initiator-workflow.ts   # 3-turn conversation logic
│       ├── activities/
│       │   └── send-a2a-message.ts     # HTTP POST to Agent B
│       ├── server.ts                    # A2A endpoint (port 8081)
│       ├── demo-driver.ts              # Demo trigger (port 8082)
│       └── worker.ts                    # Temporal worker
│
└── agent-b/                    # Python responder
    ├── Dockerfile
    ├── requirements.txt
    ├── pyproject.toml
    └── src/
        ├── workflows/
        │   └── task_workflow.py         # Crash recovery workflow
        ├── activities/
        │   ├── crash_worker.py          # sys.exit(1) trigger
        │   ├── process_message.py       # LLM call + Langfuse
        │   └── send_a2a_message.py      # Reply to Agent A
        ├── server.py                     # FastAPI A2A endpoint (port 8080)
        └── worker.py                     # Temporal worker
```

## Key Implementation Details

### Crash Recovery Mechanism (Agent B)

The crash recovery is implemented in `/workspace/agent-b/src/workflows/task_workflow.py`:

1. **Idempotency Check**: Skip if message already processed
   ```python
   if any(m["message_id"] == message_id for m in self.state.inbound_messages):
       return  # Already processed
   ```

2. **Durable Persist**: Append to workflow state BEFORE crash detection
   ```python
   self.state.inbound_messages.append({...})  # Temporal acknowledges
   ```

3. **Crash Trigger**: Detect trigger AFTER persist
   ```python
   if "EXECUTE_ORDER_66" in content:
       await workflow.execute_activity(crash_worker, ...)  # sys.exit(1)
   ```

4. **Outbox Pattern**: Prevent duplicate sends during replay
   ```python
   if not outbound["sent"]:
       await workflow.execute_activity(send_a2a_message, ...)
       outbound["sent"] = True
   ```

### A2A Protocol (JSON-RPC 2.0)

All agent-to-agent messages use this envelope:

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

## Troubleshooting

### Agent B fails to start

**Error**: `Failed to connect to LM Studio`

**Solution**: Ensure LM Studio is running, the local server is enabled, and `LM_STUDIO_BASE_URL` is reachable from Docker

### Temporal connection refused

**Error**: `Failed to connect to Temporal: connection refused`

**Solution**: Wait longer for Temporal to be healthy
```bash
docker-compose ps temporal  # Should show "healthy"
docker-compose logs temporal  # Check for errors
```

### No crash occurs

**Error**: Agent B doesn't crash on message 3

**Solution**: Check Agent B logs for crash trigger detection
```bash
docker-compose logs agent-b | grep "EXECUTE_ORDER_66"
```

### Langfuse UI shows no traces

**Error**: Traces not appearing in Langfuse

**Solution**:
1. Check Langfuse API keys are set correctly in `.env`
2. Verify Langfuse service is healthy: `docker-compose ps langfuse`
3. Check Agent B logs for Langfuse connection errors

### Docker out of resources

**Error**: Services not starting due to resource limits

**Solution**: Increase Docker resource limits (CPU, memory) in Docker Desktop settings

## Advanced Usage

### Check Task Status

```bash
curl http://localhost:8082/status/demo-1
```

### Query Workflow State

Using Temporal CLI (tctl):
```bash
docker exec -it temporal-admin-tools tctl workflow query \
  --workflow_id initiator-demo-1 \
  --query_type getState
```

### Manual A2A Message Send

```bash
curl -X POST http://localhost:8080/a2a/message/send \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "taskId": "test-1",
      "messageId": "m-test",
      "replyTo": "http://agent-a:8081/a2a/message/send",
      "content": "Manual test message"
    },
    "id": "req-test"
  }'
```

### View Agent Cards

```bash
# Agent A metadata
curl http://localhost:8081/a2a/.well-known/agent-card

# Agent B metadata
curl http://localhost:8080/a2a/.well-known/agent-card
```

## Cleanup

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove built images
docker-compose down --rmi all
```

## Technical Details

### Technology Stack

- **Agent A**: TypeScript 5.x, Node.js 20.x, Express, Temporal TypeScript SDK
- **Agent B**: Python 3.11+, FastAPI, Uvicorn, Temporal Python SDK, OpenAI-compatible LM Studio client, Langfuse
- **Infrastructure**: Docker, Temporal 1.24.2, PostgreSQL 14, Langfuse

### Database Configuration

- **Single PostgreSQL Instance**: Shared between Temporal and Langfuse for resource efficiency
  - Database: `temporal` - Used by Temporal Server
  - Database: `langfuse` - Used by Langfuse
  - User: `postgres` / Password: `postgres`
  - Created automatically via `/docker/postgres-init.sh`

### Temporal Configuration

- **Namespace**: `a2a-demo`
- **Task Queues**:
  - `agent-a-tasks` for Agent A worker
  - `agent-b-tasks` for Agent B worker
- **Workflow IDs**:
  - Agent A: `initiator-{taskId}`
  - Agent B: `task-{taskId}`

### Retry Policies

Activities use exponential backoff:
- **Initial interval**: 1 second
- **Backoff coefficient**: 2x
- **Maximum interval**: 10 seconds
- **Maximum attempts**: 3

## References

- [Temporal Documentation](https://docs.temporal.io/)
- [A2A Protocol Specification](https://anthropic.com/research/building-effective-agents)
- [LM Studio API Docs](https://lmstudio.ai/docs/api)
- [Langfuse Documentation](https://langfuse.com/docs)

## License

MIT License - See LICENSE file for details

## Contributing

This is a reference implementation for educational purposes. Contributions welcome via pull requests.

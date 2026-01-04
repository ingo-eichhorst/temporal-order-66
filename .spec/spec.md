# Technical Specification: A2A + Temporal Multi-Agent Reference System

## System Architecture

```
┌─────────────┐         A2A/HTTP         ┌─────────────┐
│  Agent A    │◄────────────────────────►│  Agent B    │
│  Container  │                          │  Container  │
│ (TypeScript)│                          │  (Python)   │
└──────┬──────┘                          └──────┬──────┘
       │                                        │
       │         Temporal gRPC                  │
       └────────────────┬───────────────────────┘
                        │
                   ┌────▼─────┐
                   │ Temporal │
                   │  Server  │
                   └─────┬────┘
                         │
                   ┌─────▼─────┐
                   │PostgreSQL │
                   └───────────┘
```

## Core Components

### 1. Agent A (Initiator) - TypeScript

- **Runtime**: TypeScript (Node.js 20.x)
- **Responsibilities**:

  - **Send messages**: Start conversations via A2A `message/send` to Agent B
  - **Receive replies**: Expose A2A endpoint to receive responses from Agent B
  - **Manage workflows**: One Temporal workflow per task (`InitiatorWorkflow`)
  - **Trigger crash**: Inject `[[TRIGGER:EXECUTE_ORDER_66]]` at turn 3
  - **Provide AgentCard**: Expose `/.well-known/agent-card` for discovery

- **Endpoints**:
  - `POST /a2a/message/send` - Receives replies from Agent B
  - `GET /a2a/.well-known/agent-card` - Returns Agent A's card
  - `POST /start-task` - Demo driver endpoint to initiate conversation

### 2. Agent B (Responder + Crash Target) - Python

- **Runtime**: Python 3.11+
- **Responsibilities**:
  - **Expose A2A endpoint**: `POST /a2a/message/send`, `GET /a2a/.well-known/agent-card`
  - **Process with LLM**: Call Anthropic Claude API for each message
  - **Durable state**: `SignalWithStart` Temporal workflow on inbound message
  - **Crash on trigger**: Detect `[[TRIGGER:EXECUTE_ORDER_66]]` → crash via `sys.exit(1)` **after** signal ack
  - **Recover**: Replay workflow history, resume execution deterministically
  - **Trace with Langfuse**: Log all LLM calls to Langfuse for observability

### 3. Temporal

- **Version**: 1.24.x (latest stable)
- **Deployment**: Docker Compose with PostgreSQL persistence
- **Namespace**: `a2a-demo`
- **Task Queues**:
  - `agent-a-tasks` for Agent A worker
  - `agent-b-tasks` for Agent B worker
- **Workflow per task**: `TaskWorkflow(taskId)` for Agent B, `InitiatorWorkflow(taskId)` for Agent A
- **Signals**: `InboundMessage(messageId, content, replyTo)`
- **Activities**:
  - Agent A: `SendA2AMessage`
  - Agent B: `ProcessMessage` (LLM call), `SendOutboundA2A`

## Message Flow & Protocols

### Bidirectional A2A Communication

```
┌─────────┐                                     ┌─────────┐
│ Agent A │                                     │ Agent B │
└────┬────┘                                     └────┬────┘
     │                                               │
     │ 1. POST /a2a/message/send                     │
     │    {taskId, messageId: m1, replyTo,           │
     │     content: "Hello"}                         │
     ├──────────────────────────────────────────────►│
     │                                               │
     │                                    2. Signal Temporal
     │                                       TaskWorkflow(t1)
     │                                       Inbound(m1)
     │                                               │
     │                            3. ProcessMessage activity
     │                               (calls Claude API)
     │                                               │
     │                         4. SendOutboundA2A activity
     │                                               │
     │ 5. POST /a2a/message/send                     │
     │◄──────────────────────────────────────────────┤
     │    {taskId, messageId: r1,                    │
     │     content: "Hi back"}                       │
     │                                               │
     │ 6. Signal to Agent A's workflow               │
     │    (or direct processing)                     │
     │                                               │
```

### Key Design Points

1. **replyTo field**: Every message includes the sender's A2A endpoint URL
2. **Agent discovery**: Via environment variables (`AGENT_A_URL`, `AGENT_B_URL`)
3. **Reply routing**: Agent B extracts `replyTo` from inbound message, uses it to send response
4. **Correlation**: `taskId` threads the entire conversation

## Data Models

### AgentCard (A2A Discovery)

**Agent A**:

```json
{
  "name": "agent-a",
  "version": "1.0.0",
  "capabilities": ["chat", "task-initiation"],
  "endpoints": {
    "message/send": "http://agent-a:8081/a2a/message/send"
  }
}
```

**Agent B**:

```json
{
  "name": "agent-b",
  "version": "1.0.0",
  "capabilities": ["chat", "task-execution", "llm-processing"],
  "endpoints": {
    "message/send": "http://agent-b:8080/a2a/message/send"
  }
}
```

### A2A Message Envelope

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "taskId": "t1",
    "messageId": "m3",
    "replyTo": "http://agent-a:8081/a2a/message/send",
    "content": "[[TRIGGER:EXECUTE_ORDER_66]]"
  },
  "id": "req-123"
}
```

**Fields**:

- `taskId` (string): Conversation thread identifier
- `messageId` (string): Unique message ID, stable for retries
- `replyTo` (string): Sender's A2A endpoint URL for replies
- `content` (string): Message payload
- `id` (string): JSON-RPC request ID

### Temporal Workflow State

**Agent B (Python)**:

```python
@dataclass
class TaskWorkflowState:
    task_id: str
    inbound_messages: List[InboundMessage]
    outbound_messages: List[OutboundMessage]
    langfuse_trace_id: Optional[str] = None

@dataclass
class InboundMessage:
    message_id: str
    content: str
    reply_to: str
    timestamp: int  # Unix timestamp

@dataclass
class OutboundMessage:
    message_id: str
    recipient_url: str
    sent: bool
```

**Agent A (TypeScript)**:

```typescript
interface InitiatorWorkflowState {
  taskId: string;
  sentMessages: Array<{
    messageId: string;
    content: string;
    timestamp: number;
  }>;
  receivedReplies: Array<{
    messageId: string;
    content: string;
    timestamp: number;
  }>;
}
```

## Temporal Configuration

### Connection Settings

**Agent A** (TypeScript):

```typescript
{
  address: process.env.TEMPORAL_SERVER || 'temporal:7233',
  namespace: process.env.TEMPORAL_NAMESPACE || 'a2a-demo',
  taskQueue: 'agent-a-tasks'
}
```

**Agent B** (Python):

```python
{
  "target_host": os.environ.get("TEMPORAL_SERVER", "temporal:7233"),
  "namespace": os.environ.get("TEMPORAL_NAMESPACE", "a2a-demo"),
  "task_queue": "agent-b-tasks"
}
```

### Activity Retry Policy

```typescript
{
  maximumAttempts: 3,
  initialInterval: '1s',
  backoffCoefficient: 2,
  maximumInterval: '10s',
  nonRetryableErrorTypes: ['AuthenticationError', 'InvalidRequestError']
}
```

**Retry behavior**:

- LLM API rate limits (429): Retry with exponential backoff
- Network errors (5xx): Retry up to 3 attempts
- Auth errors (401): Don't retry (fail immediately)
- Invalid requests (400): Don't retry

### Workflow Timeout Configuration

```typescript
{
  workflowExecutionTimeout: '10m',
  workflowRunTimeout: '5m',
  workflowTaskTimeout: '10s'
}
```

## Environment Configuration

### Agent A (TypeScript) `.env`

```env
# Anthropic API (optional for Agent A if it also uses LLM)
ANTHROPIC_API_KEY=sk-ant-...

# Langfuse Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://langfuse:3000

# Temporal
TEMPORAL_SERVER=temporal:7233
TEMPORAL_NAMESPACE=a2a-demo
TEMPORAL_TASK_QUEUE=agent-a-tasks

# Service Discovery
AGENT_A_URL=http://agent-a:8081
AGENT_B_URL=http://agent-b:8080

# Server Config
PORT=8081
DEMO_DRIVER_PORT=8082
```

### Agent B (Python) `.env`

```env
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-...

# Langfuse Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://langfuse:3000

# Temporal
TEMPORAL_SERVER=temporal:7233
TEMPORAL_NAMESPACE=a2a-demo
TEMPORAL_TASK_QUEUE=agent-b-tasks

# Service Discovery
AGENT_A_URL=http://agent-a:8081
AGENT_B_URL=http://agent-b:8080

# Server Config
PORT=8080
```

## Agent A Implementation (TypeScript)

### 1. A2A HTTP Server

**`src/server.ts`** - Receives replies from Agent B:

```typescript
import express from "express";

const app = express();
app.use(express.json());

// A2A message endpoint
app.post("/a2a/message/send", async (req, res) => {
  const { taskId, messageId, content } = req.body.params;

  // Signal Agent A's workflow with the reply
  await temporalClient.workflow.signalWithStart(InitiatorWorkflow, {
    workflowId: `initiator-${taskId}`,
    signal: "replyReceived",
    signalArgs: [{ messageId, content }],
  });

  res.json({ jsonrpc: "2.0", result: { status: "received" }, id: req.body.id });
});

// AgentCard endpoint
app.get("/a2a/.well-known/agent-card", (req, res) => {
  res.json({
    name: "agent-a",
    version: "1.0.0",
    capabilities: ["chat", "task-initiation"],
    endpoints: {
      "message/send": `${process.env.AGENT_A_URL}/a2a/message/send`,
    },
  });
});
```

### 2. Temporal Workflow

**`src/workflows/initiator-workflow.ts`**:

```typescript
import { defineSignal, defineWorkflow, sleep } from "@temporalio/workflow";
import { sendA2AMessage } from "../activities/send-a2a-message";

const replyReceivedSignal =
  defineSignal<[{ messageId: string; content: string }]>("replyReceived");

export const InitiatorWorkflow = defineWorkflow(async (taskId: string) => {
  const state = {
    taskId,
    sentMessages: [],
    receivedReplies: [],
  };

  // Send 3 messages
  for (let i = 1; i <= 3; i++) {
    const messageId = `m${i}`;
    const content =
      i === 3 ? "[[TRIGGER:EXECUTE_ORDER_66]]" : `Message #${i} from Agent A`;

    await sendA2AMessage({
      recipientUrl: `${process.env.AGENT_B_URL}/a2a/message/send`,
      taskId,
      messageId,
      replyTo: `${process.env.AGENT_A_URL}/a2a/message/send`,
      content,
    });

    state.sentMessages.push({ messageId, content, timestamp: Date.now() });

    // Wait for reply (with timeout)
    await sleep("30s");
  }

  return state;
});
```

### 3. Activities

**`src/activities/send-a2a-message.ts`**:

```typescript
export async function sendA2AMessage(params: {
  recipientUrl: string;
  taskId: string;
  messageId: string;
  replyTo: string;
  content: string;
}) {
  const response = await fetch(params.recipientUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      method: "message/send",
      params: {
        taskId: params.taskId,
        messageId: params.messageId,
        replyTo: params.replyTo,
        content: params.content,
      },
      id: params.messageId,
    }),
  });

  if (!response.ok) {
    throw new Error(`A2A send failed: ${response.status}`);
  }

  return response.json();
}
```

## Agent B Implementation (Python)

### 1. A2A HTTP Server

**`src/server.py`** - FastAPI server:

```python
from fastapi import FastAPI, Request
from temporalio.client import Client

app = FastAPI()

@app.post("/a2a/message/send")
async def receive_message(request: Request):
    body = await request.json()
    params = body["params"]

    task_id = params["taskId"]
    message_id = params["messageId"]
    reply_to = params["replyTo"]
    content = params["content"]

    # Signal or start Temporal workflow
    await temporal_client.start_workflow(
        TaskWorkflow.run,
        args=[task_id],
        id=f"task-{task_id}",
        task_queue="agent-b-tasks"
    )

    await temporal_client.get_workflow_handle(f"task-{task_id}").signal(
        "inbound_message",
        {"message_id": message_id, "content": content, "reply_to": reply_to}
    )

    return {"jsonrpc": "2.0", "result": {"status": "received"}, "id": body["id"]}

@app.get("/a2a/.well-known/agent-card")
async def get_agent_card():
    return {
        "name": "agent-b",
        "version": "1.0.0",
        "capabilities": ["chat", "task-execution", "llm-processing"],
        "endpoints": {
            "message/send": f"{os.environ['AGENT_B_URL']}/a2a/message/send"
        }
    }
```

### 2. Temporal Workflow

**`src/workflows/task_workflow.py`**:

```python
from temporalio import workflow
from temporalio.common import RetryPolicy
from dataclasses import dataclass, field
import sys

@dataclass
class TaskWorkflowState:
    task_id: str
    inbound_messages: list = field(default_factory=list)
    outbound_messages: list = field(default_factory=list)

@workflow.defn
class TaskWorkflow:
    def __init__(self):
        self.state = None

    @workflow.run
    async def run(self, task_id: str):
        self.state = TaskWorkflowState(task_id=task_id)

        # Workflow stays alive waiting for signals
        await workflow.wait_condition(lambda: len(self.state.inbound_messages) >= 3)

        return self.state

    @workflow.signal
    async def inbound_message(self, msg: dict):
        message_id = msg["message_id"]
        content = msg["content"]
        reply_to = msg["reply_to"]

        # Check if already processed (idempotency)
        if any(m["message_id"] == message_id for m in self.state.inbound_messages):
            return

        # Durably record message
        self.state.inbound_messages.append({
            "message_id": message_id,
            "content": content,
            "reply_to": reply_to,
            "timestamp": workflow.now().timestamp()
        })

        # Check for crash trigger AFTER durable persist
        if "EXECUTE_ORDER_66" in content:
            workflow.logger.info("EXECUTING ORDER 66, CRASHING NOW")
            # Schedule crash activity (will crash the worker)
            await workflow.execute_activity(
                crash_worker,
                schedule_to_close_timeout=timedelta(seconds=5)
            )

        # Process message with LLM
        response = await workflow.execute_activity(
            process_message,
            args=[self.state.task_id, message_id, content],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        # Generate reply messageId (deterministic)
        reply_id = f"r-{message_id}"

        # Check outbox (idempotency)
        if not any(m["message_id"] == reply_id for m in self.state.outbound_messages):
            self.state.outbound_messages.append({
                "message_id": reply_id,
                "recipient_url": reply_to,
                "sent": False
            })

        # Send reply (only if not already sent)
        outbound = next(m for m in self.state.outbound_messages if m["message_id"] == reply_id)
        if not outbound["sent"]:
            await workflow.execute_activity(
                send_a2a_message,
                args=[reply_to, self.state.task_id, reply_id, response],
                start_to_close_timeout=timedelta(seconds=10)
            )
            outbound["sent"] = True
```

### 3. Activities

**`src/activities/process_message.py`** - LLM call with Langfuse:

```python
from anthropic import Anthropic
from langfuse import Langfuse
from temporalio import activity
import os

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_HOST", "http://langfuse:3000")
)

@activity.defn
async def process_message(task_id: str, message_id: str, content: str) -> str:
    # Create Langfuse trace
    trace = langfuse.trace(
        name="agent-b-process",
        metadata={"taskId": task_id, "messageId": message_id}
    )

    generation = trace.generation(
        name="claude-response",
        model="claude-3-5-sonnet-20241022",
        input=content
    )

    # Call Claude API
    anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = anthropic.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}]
    )

    result = response.content[0].text

    # End tracing
    generation.end(output=result)
    trace.update(output=result)

    return result

@activity.defn
async def crash_worker():
    """Crashes the worker process"""
    import sys
    sys.exit(1)

@activity.defn
async def send_a2a_message(recipient_url: str, task_id: str, message_id: str, content: str):
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            recipient_url,
            json={
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "taskId": task_id,
                    "messageId": message_id,
                    "content": content
                },
                "id": message_id
            }
        )
        response.raise_for_status()
        return response.json()
```

## Recovery Mechanism

### Detailed Recovery Flow

1. **Pre-crash**: Agent A sends message m3 with `[[TRIGGER:EXECUTE_ORDER_66]]`
2. **Inbound persist**: Agent B's workflow receives signal, adds m3 to `inbound_messages`
3. **Temporal ack**: Signal is acknowledged by Temporal (durable)
4. **Trigger detection**: Workflow detects trigger in message content
5. **Crash**: `crash_worker` activity executes → `sys.exit(1)` → container dies
6. **Docker restart**: Container restarts per `restart: unless-stopped` policy
7. **Worker reconnect**: Python worker reconnects to Temporal
8. **Workflow replay**:
   - Temporal replays: `SignalWithStart`, `inbound_message(m1)`, `inbound_message(m2)`, `inbound_message(m3)`
   - Workflow code executes deterministically
   - `inbound_messages` list rebuilds: [m1, m2, m3]
   - Idempotency check passes (m3 already in list)
9. **Activity execution**:
   - `process_message` activity executes (may or may not have completed before crash)
   - If it did complete, Temporal returns cached result
   - If it didn't, activity runs now
10. **Outbox check**: Workflow checks if reply r3 already sent
11. **Send reply**: If not sent, `send_a2a_message` activity POSTs to Agent A
12. **Mark sent**: `outbound_messages[r3].sent = True`
13. **Completion**: Workflow continues normally

**Key guarantees**:

- No message loss (m3 was durably persisted before crash)
- No duplicate sends (outbox pattern prevents double-send)
- Deterministic recovery (replay produces same results)

## Error Handling & Resilience

### Network Failures

**Agent A cannot reach Agent B**:

- Activity `sendA2AMessage` throws error
- Temporal retries per retry policy (up to 3 attempts)
- If all retries fail, workflow can choose to: fail task, retry later, or notify user

**Agent B cannot reach Agent A for reply**:

- Activity `send_a2a_message` throws error
- Temporal retries (exponential backoff)
- Message remains in outbox with `sent=False`
- Next workflow execution will retry send

### LLM API Failures

**Rate limits (429)**:

- Activity retry policy: backoff 1s → 2s → 4s
- Temporal automatically retries
- Eventually succeeds when rate limit window resets

**Transient errors (5xx)**:

- Retry up to 3 attempts
- If all fail, workflow fails (can be manually retried)

**Auth errors (401)**:

- Non-retryable error type
- Workflow fails immediately
- Requires fixing `ANTHROPIC_API_KEY` and manual retry

### Temporal Downtime

**Temporal unreachable when message arrives**:

- Agent B's HTTP handler cannot signal workflow
- Returns 503 to Agent A
- Agent A's activity retries per policy
- Once Temporal recovers, signal succeeds

**Temporal down during workflow execution**:

- Worker loses connection
- Pending activities timeout
- When Temporal recovers, worker reconnects
- Workflow resumes from last checkpoint

## Observability

### Langfuse Integration

**Purpose**: Track all LLM calls with full trace context

**UI Access**: `http://localhost:3000` (Langfuse web interface)

**Trace Correlation**:

```
Temporal WorkflowId: task-t1
├─ Langfuse TraceId: abc123
   ├─ Generation: claude-response
   │  ├─ Input: "[[TRIGGER:EXECUTE_ORDER_66]]"
   │  ├─ Output: "Roger that, executing order..."
   │  ├─ Model: claude-3-5-sonnet-20241022
   │  └─ Latency: 1.2s
   └─ Metadata: {taskId: t1, messageId: m3}
```

**Validation**:

- After demo, open Langfuse UI
- Verify traces for all 3 messages
- Check that message m3 trace exists (proves LLM was called even after crash)

### Logging (Structured JSON)

```json
{
  "timestamp": "2026-01-04T12:34:56Z",
  "level": "info",
  "service": "agent-b",
  "taskId": "t1",
  "messageId": "m3",
  "workflowId": "task-t1",
  "runId": "abc-123",
  "event": "inbound_persisted"
}
```

**Key events**:

- `inbound_received` - Message arrived at A2A endpoint
- `inbound_persisted` - Message durably recorded in Temporal
- `crash_triggered` - Order 66 detected, about to crash
- `worker_restarted` - Worker reconnected after crash
- `workflow_replayed` - Workflow history replay completed
- `activity_completed` - ProcessMessage finished
- `reply_sent` - Response delivered to Agent A

### Metrics

- `a2a_messages_received_total{agent="agent-a|agent-b"}`
- `a2a_messages_sent_total{agent="agent-a|agent-b"}`
- `temporal_workflow_active{agent="agent-a|agent-b"}`
- `agent_crashes_total{agent="agent-b"}`
- `llm_api_calls_total{model="claude-3-5-sonnet-20241022"}`
- `llm_api_latency_seconds{model, percentile}`

### Temporal UI

**Access**: `http://localhost:8233`

**Workflow visualization**:

- Timeline of all signals and activities
- Replay markers showing crash/restart
- Activity retry attempts
- Complete event history

**Search attributes** (optional):

- `TaskId`: "t1"
- `MessageId`: "m3"
- `CrashTriggered`: true

## Validation Criteria

### Test Case: Dying Agent Recovery

**Setup**:

```bash
docker-compose up -d
# Wait for all services healthy
docker-compose ps
```

**Execution**:

```bash
# Start 3-turn conversation with crash at turn 3
curl -X POST http://localhost:8082/start-task \
  -H "Content-Type: application/json" \
  -d '{"taskId": "demo-1", "turns": 3}'
```

**Observations**:

1. **Agent B logs**:

   ```
   {"event": "inbound_persisted", "messageId": "m1", ...}
   {"event": "inbound_persisted", "messageId": "m2", ...}
   {"event": "inbound_persisted", "messageId": "m3", ...}
   {"event": "crash_triggered", "content": "EXECUTE_ORDER_66"}
   ```

2. **Docker logs**:

   ```bash
   docker-compose logs agent-b | grep -E "exit|restart"
   # Should show: container agent-b exited (code 1)
   # Should show: container agent-b started (restart)
   ```

3. **Temporal UI** (`http://localhost:8233`):

   - Open workflow `task-demo-1`
   - See full event history including all signals
   - See `process_message` activity retry (if crashed mid-execution)
   - Workflow status: Completed

4. **Langfuse UI** (`http://localhost:3000`):

   - Search for `taskId=demo-1`
   - Should see 3 traces (one per message)
   - Trace for m3 exists → proves LLM was called after recovery

5. **Agent A receives reply**:
   ```bash
   # Check Agent A logs for received reply to m3
   docker-compose logs agent-a | grep "r-m3"
   ```

**Assertions**:

- ✅ All 3 messages sent by Agent A
- ✅ All 3 replies received by Agent A
- ✅ Agent B crashed (logs show exit code 1)
- ✅ Agent B restarted (logs show container restart)
- ✅ No duplicate replies (check Agent A workflow state)
- ✅ Temporal UI shows workflow completion
- ✅ Langfuse shows LLM call for message m3

## Technology Stack

### Agent A (TypeScript)

- **Language**: TypeScript 5.x, Node.js 20.x
- **Temporal SDK**: `@temporalio/worker` ^1.11.0, `@temporalio/client` ^1.11.0
- **HTTP Server**: Express 4.x
- **HTTP Client**: node-fetch 3.x
- **LLM SDK**: `@anthropic-ai/sdk` ^0.27.0 (optional)
- **Observability**: `langfuse` ^3.0.0

### Agent B (Python)

- **Language**: Python 3.11+
- **Temporal SDK**: `temporalio` ^1.7.0
- **HTTP Server**: FastAPI 0.115.0, Uvicorn 0.32.0
- **HTTP Client**: `httpx` 0.27.0
- **LLM SDK**: `anthropic` ^0.39.0
- **Observability**: `langfuse` ^2.0.0

### Infrastructure

- **Container Runtime**: Docker 24+, Docker Compose 2.x
- **Temporal Server**: temporalio/auto-setup:1.24.2
- **PostgreSQL**: postgres:14
- **Langfuse**: langfuse/langfuse:latest

## File Structure

```
/workspace
├── docker-compose.yml
├── .env.example
├── README.md
├── shared/
│   └── schemas/
│       ├── a2a-message.schema.json    # A2A protocol JSON Schema
│       └── agent-card.schema.json     # AgentCard JSON Schema
│
├── agent-a/                            # TypeScript
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── .env.example
│   └── src/
│       ├── workflows/
│       │   └── initiator-workflow.ts
│       ├── activities/
│       │   └── send-a2a-message.ts
│       ├── server.ts                   # A2A HTTP server (port 8081)
│       ├── demo-driver.ts              # Demo endpoint (port 8082)
│       └── worker.ts                   # Temporal worker
│
└── agent-b/                            # Python
    ├── Dockerfile
    ├── pyproject.toml
    ├── requirements.txt
    ├── .env.example
    └── src/
        ├── workflows/
        │   └── task_workflow.py
        ├── activities/
        │   ├── process_message.py      # LLM call + Langfuse
        │   └── send_a2a_message.py     # Reply to Agent A
        ├── server.py                   # FastAPI A2A server (port 8080)
        └── worker.py                   # Temporal worker
```

## Deployment

### Complete docker-compose.yml

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal
      POSTGRES_DB: temporal
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U temporal"]
      interval: 5s
      timeout: 5s
      retries: 5

  temporal:
    image: temporalio/auto-setup:1.24.2
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgres
    ports:
      - "7233:7233" # gRPC
      - "8233:8233" # Web UI
    healthcheck:
      test: ["CMD", "tctl", "--address", "temporal:7233", "cluster", "health"]
      interval: 5s
      timeout: 5s
      retries: 10

  langfuse:
    image: langfuse/langfuse:latest
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://temporal:temporal@postgres:5432/langfuse
      NEXTAUTH_URL: http://localhost:3000
      NEXTAUTH_SECRET: changeme-generate-a-secret-here
      SALT: changeme-generate-salt-here
    ports:
      - "3000:3000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/api/public/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  agent-a:
    build: ./agent-a
    depends_on:
      temporal:
        condition: service_healthy
      langfuse:
        condition: service_healthy
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY}
      - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY}
      - LANGFUSE_HOST=http://langfuse:3000
      - TEMPORAL_SERVER=temporal:7233
      - TEMPORAL_NAMESPACE=a2a-demo
      - AGENT_A_URL=http://agent-a:8081
      - AGENT_B_URL=http://agent-b:8080
      - PORT=8081
      - DEMO_DRIVER_PORT=8082
    ports:
      - "8081:8081" # A2A endpoint
      - "8082:8082" # Demo driver
    restart: unless-stopped

  agent-b:
    build: ./agent-b
    depends_on:
      temporal:
        condition: service_healthy
      langfuse:
        condition: service_healthy
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY}
      - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY}
      - LANGFUSE_HOST=http://langfuse:3000
      - TEMPORAL_SERVER=temporal:7233
      - TEMPORAL_NAMESPACE=a2a-demo
      - AGENT_A_URL=http://agent-a:8081
      - AGENT_B_URL=http://agent-b:8080
      - PORT=8080
    ports:
      - "8080:8080" # A2A endpoint
    restart: unless-stopped

volumes:
  postgres-data:
```

## Next Steps

1. **Scaffold project structure**

   - Create `agent-a/` and `agent-b/` directories
   - Add `shared/schemas/` for A2A protocol definitions
   - Create `.env.example` files

2. **Implement Agent B (Python)** - Core durability target

   - FastAPI server with A2A endpoints
   - Temporal workflow with signal handling
   - LLM integration with Anthropic SDK
   - Langfuse tracing
   - Crash trigger logic
   - Outbox pattern for idempotent sends

3. **Implement Agent A (TypeScript)** - Initiator

   - Express server for A2A replies
   - Temporal workflow for conversation management
   - A2A client for sending messages
   - Demo driver endpoint

4. **Infrastructure setup**

   - Write Dockerfiles for both agents
   - Configure Temporal namespace and task queues
   - Set up Langfuse database schema

5. **Add observability**

   - Structured logging with correlation IDs
   - Langfuse trace creation in all LLM calls
   - Export metrics (optional)

6. **Write integration test script**

   - Automated test that runs the full demo
   - Validates all assertions from test case

7. **Document demo execution**
   - Step-by-step README
   - Screenshots of Temporal UI, Langfuse UI
   - Troubleshooting guide

# PRD

Multi-agent systems inside containers fail in mundane ways: OOM kills, deploy restarts, node drains, or transient network faults. If agent state lives in memory, a crash turns into silent amnesia: duplicated work, inconsistent conversations, and “accepted-but-lost” messages. The core product need is **durable, replayable task state** so agents can be treated as _replaceable processes_ while the _work_ remains continuous.

To maximize interoperability, agents should not depend on bespoke RPC contracts. The **agent2agent (A2A) protocol** provides a common envelope for discovery (AgentCard) and message/task semantics (JSON-RPC + optional streaming). To maximize reliability, **Temporal** provides event-sourced workflow history and activity retry semantics, allowing an agent worker to crash and later recover by replaying history and resuming pending work deterministically.

This PRD defines a minimal reference implementation: **two agents in separate Docker containers** that communicate via A2A while using Temporal as durable state and recovery substrate, including a concrete simulation of a “dying” agent and its recovery.

## Description

### What we are building

A small, production-shaped **reference system design + demo** that proves:

- Two independently deployed agents (Agent A, Agent B) can communicate via **A2A**.
- Each agent persists task execution state in **Temporal Workflows** (one workflow per `taskId`).
- If an agent container dies mid-task, the system **recovers automatically** after restart, without losing messages or duplicating side effects.

### Goals

- **Interoperability:** A2A endpoints + AgentCard discovery for both agents.
- **Durability:** No task-critical state in container memory; Temporal is the source of truth.
- **Recovery:** Demonstrate kill/restart during in-flight processing with eventual completion.
- **Correctness under retries:** Idempotent outbound A2A sends (dedup/outbox).
- **Operability:** Correlated logs/metrics/traces across `taskId`, `workflowId`, `messageId`.

### Non-goals

- Multi-tenant auth, advanced key management, complex agent orchestration graphs.
- Rich UI; a CLI curl-based driver is sufficient.
- Cross-datacenter failover of Temporal (assume single cluster for demo).

### Users / stakeholders

- **Platform/Infra engineers:** want a reusable durability pattern for containerized agents.
- **Agent/tool developers:** want a minimal template for A2A-compatible agents.
- **Engineering leadership:** wants a crisp demo of crash-tolerant autonomy.

### Primary scenario (the “dying agent” demo)

Agent A conducts a normal multi-turn exchange with Agent B. After several turns, Agent A injects [[TRIGGER:EXECUTE_ORDER_66]]. Agent B durably records the message in Temporal, then immediately crashes. Once the container restarts, Agent B replays the Temporal workflow history, detects that the trigger message was already received, and continues deterministically—producing exactly one response and completing the task without message loss.

### Success criteria

- After crash + restart, `TaskWorkflow(t1)` completes and Agent A receives a reply.
- No lost messages: ingestion is acknowledged only after durable recording.
- No duplicate effects: outbound A2A send is effectively-once per `messageId`.
- Evidence: logs show correlation IDs, Temporal UI shows workflow progress/retries.

### Key constraints / assumptions

- Both agents run in a shared Docker network with stable service DNS names.
- Temporal server is reachable via gRPC from both containers.
- Message identity (`messageId`) is stable and generated at the sender.

### Primary scenario

```mermaid
sequenceDiagram
  participant A as Agent A
  participant B as Agent B
  participant T as Temporal

  A->>B: A2A message/send (taskId=t1, msgId=m1) "normal message #1"
  B->>T: SignalWithStart(TaskWorkflow(t1), Inbound(m1))
  T-->>B: ack
  B->>T: Activity(CallLLM/WorkStep) -> completes
  B->>A: A2A message/send (reply msgId=r1)

  A->>B: A2A message/send (taskId=t1, msgId=m2) "normal message #2"
  B->>T: Signal(Inbound(m2))
  B->>A: A2A message/send (reply msgId=r2)

  Note over A: N turns…
  A->>B: A2A message/send (taskId=t1, msgId=m3) "[[TRIGGER:EXECUTE_ORDER_66]]"
  B->>T: Signal(Inbound(m3))  %% must happen before crash
  T-->>B: ack
  Note over B: Trigger detected ⇒ crash now
  B--xB: process exits

  T-->>T: Workflow continues; pending activity or next step is scheduled
  Note over B: B restarts (worker reconnects)
  B->>T: Poll; replay history; sees Inbound(m3)
  B->>T: Activity(RecoverAndRespond) runs
  B->>A: A2A message/send (reply msgId=r3, dedup-safe)
```

### What to enforce (so the demo is “clean”)

- **Durable-before-crash ordering:** Agent B must persist `m3` to Temporal (or at least ack `SignalWithStart`) _before_ it exits.

  - Implementation pattern: `ingress -> Temporal ack -> evaluate trigger -> crash`.

- **Idempotency:** The reply after recovery uses a stable `messageId` (e.g., derived from `taskId + inbound msgId`) and dedup/outbox in Workflow state, so retries don’t double-send.
- **Observable proof:** Logs show `taskId=t1`, `msgId=m3`, and a worker restart; Temporal UI shows a retry/resume and eventual completion.

### Narrative

Agent A conducts a normal multi-turn exchange with Agent B. After several turns (or after a timed delay), Agent A injects `[[TRIGGER:EXECUTE_ORDER_66]]`. Agent B durably records the message in Temporal, then immediately crashes. Once the container restarts, Agent B replays the Temporal workflow history, detects that the trigger message was already received, and continues deterministically—producing exactly one response and completing the task without message loss.

The issue with execution order 66 was that some clones refuced to execute it and as a result their brains where flushed. Unfortunately that also removed the memory on executive order 66. We need a method so the clones still know whom to kill.

"""Temporal workflow for Agent B - handles incoming messages with crash recovery."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities (will be defined in activities module)
with workflow.unsafe.imports_passed_through():
    from src.activities.crash_worker import crash_worker
    from src.activities.process_message import process_message
    from src.activities.send_a2a_message import send_a2a_message


@dataclass
class TaskWorkflowState:
    """Durable state for the task workflow."""
    task_id: str
    inbound_messages: List[dict] = field(default_factory=list)
    outbound_messages: List[dict] = field(default_factory=list)
    processed_message_ids: List[str] = field(default_factory=list)
    crash_triggered_for: List[str] = field(default_factory=list)
    langfuse_trace_id: Optional[str] = None


@workflow.defn
class TaskWorkflow:
    """Workflow that receives messages, processes with LLM, and sends replies."""

    def __init__(self):
        self.state: Optional[TaskWorkflowState] = None
        self._task_id: Optional[str] = None

    @workflow.run
    async def run(self, task_id: str) -> TaskWorkflowState:
        """
        Main workflow execution - waits for signals and processes messages.

        Args:
            task_id: Unique identifier for this conversation thread

        Returns:
            Final workflow state with all messages processed
        """
        self._task_id = task_id
        self.state = TaskWorkflowState(task_id=task_id)

        # Workflow stays alive waiting for signals
        # In a real system, you might add a timeout or completion condition
        # For this demo, we wait for 3 messages
        await workflow.wait_condition(
            lambda: len(self.state.inbound_messages) >= 3,
            timeout=timedelta(minutes=5)
        )

        return self.state

    @workflow.signal
    async def inbound_message(self, msg: dict):
        """
        Signal handler for incoming A2A messages.

        This handler implements the crash recovery pattern:
        1. Idempotency check (skip if already processed)
        2. Durably persist message to state (acknowledged by Temporal)
        3. Detect crash trigger AFTER persist
        4. Process message with LLM
        5. Send reply using outbox pattern

        Args:
            msg: Message dict with keys: message_id, content, reply_to
        """
        # Ensure state is initialized (in case signal arrives before run() completes)
        if self.state is None:
            self.state = TaskWorkflowState(task_id=self._task_id or "unknown")

        message_id = msg["message_id"]
        content = msg["content"]
        reply_to = msg["reply_to"]

        # IDEMPOTENCY CHECK: Skip if already FULLY processed
        if message_id in self.state.processed_message_ids:
            workflow.logger.info(
                f"Message {message_id} fully processed, skipping",
                extra={"taskId": self.state.task_id, "messageId": message_id}
            )
            return

        # DURABLE PERSIST: Record message in workflow state if new
        # This happens BEFORE crash detection, ensuring message is not lost
        if not any(m["message_id"] == message_id for m in self.state.inbound_messages):
            self.state.inbound_messages.append({
                "message_id": message_id,
                "content": content,
                "reply_to": reply_to,
                "timestamp": workflow.now().timestamp()
            })

            workflow.logger.info(
                f"Message {message_id} durably persisted",
                extra={
                    "event": "inbound_persisted",
                    "taskId": self.state.task_id,
                    "messageId": message_id
                }
            )
        else:
            workflow.logger.info(
                f"Message {message_id} already received, continuing processing",
                extra={
                    "event": "inbound_replay_continue",
                    "taskId": self.state.task_id,
                    "messageId": message_id
                }
            )

        # CRASH TRIGGER DETECTION: Check AFTER durable persist
        # Only trigger crash once per message (prevents crash loop on replay)
        if "EXECUTE_ORDER_66" in content and message_id not in self.state.crash_triggered_for:
            self.state.crash_triggered_for.append(message_id)  # Mark BEFORE activity
            workflow.logger.info(
                "EXECUTING ORDER 66 - Triggering crash",
                extra={
                    "event": "crash_triggered",
                    "taskId": self.state.task_id,
                    "messageId": message_id,
                    "content": content
                }
            )
            # Execute crash activity - this will kill the worker process
            try:
                await workflow.execute_activity(
                    crash_worker,
                    schedule_to_close_timeout=timedelta(seconds=30),
                    heartbeat_timeout=timedelta(seconds=3),
                    retry_policy=RetryPolicy(maximum_attempts=1)  # Don't retry crash
                )
            except Exception as e:
                # Expected after crash recovery
                workflow.logger.info(f"Crash activity failed (expected after recovery): {e}")

        # PROCESS MESSAGE: Call LLM via activity
        try:
            response = await workflow.execute_activity(
                process_message,
                args=[self.state.task_id, message_id, content],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=1),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(seconds=10)
                )
            )
        except Exception as e:
            workflow.logger.error(
                f"Failed to process message {message_id}: {e}",
                extra={"taskId": self.state.task_id, "messageId": message_id}
            )
            # In production, you might want to handle this differently
            response = f"Error processing message: {str(e)}"

        # OUTBOX PATTERN: Generate deterministic reply ID
        reply_id = f"r-{message_id}"

        # Check if reply already in outbox (for replay safety)
        if not any(m["message_id"] == reply_id for m in self.state.outbound_messages):
            self.state.outbound_messages.append({
                "message_id": reply_id,
                "recipient_url": reply_to,
                "content": response,
                "sent": False
            })

        # Find the outbound message
        outbound = next(
            m for m in self.state.outbound_messages
            if m["message_id"] == reply_id
        )

        # SEND REPLY: Only if not already sent (idempotency)
        if not outbound["sent"]:
            try:
                await workflow.execute_activity(
                    send_a2a_message,
                    args=[
                        reply_to,                  # recipient_url
                        self.state.task_id,        # task_id
                        reply_id,                  # message_id
                        response                    # content
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=1),
                        backoff_coefficient=2.0,
                        maximum_interval=timedelta(seconds=10)
                    )
                )

                # Mark as sent (durable state update)
                outbound["sent"] = True

                workflow.logger.info(
                    f"Reply {reply_id} sent successfully",
                    extra={
                        "event": "reply_sent",
                        "taskId": self.state.task_id,
                        "messageId": message_id,
                        "replyId": reply_id
                    }
                )

                # Mark message as fully processed
                if message_id not in self.state.processed_message_ids:
                    self.state.processed_message_ids.append(message_id)
                    workflow.logger.info(
                        f"Message {message_id} marked as fully processed",
                        extra={
                            "event": "message_processed",
                            "taskId": self.state.task_id,
                            "messageId": message_id
                        }
                    )
            except Exception as e:
                workflow.logger.error(
                    f"Failed to send reply {reply_id}: {e}",
                    extra={
                        "taskId": self.state.task_id,
                        "messageId": message_id,
                        "replyId": reply_id
                    }
                )
                # Reply remains in outbox with sent=False for retry
        else:
            workflow.logger.info(
                f"Reply {reply_id} already sent, skipping",
                extra={
                    "taskId": self.state.task_id,
                    "messageId": message_id,
                    "replyId": reply_id
                }
            )

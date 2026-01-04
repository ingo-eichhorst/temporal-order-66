"""FastAPI server for Agent B - A2A HTTP endpoints."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from temporalio.client import Client

from src.workflows.task_workflow import TaskWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "extra": %(extra)s}'
)
logger = logging.getLogger(__name__)

# Global Temporal client
temporal_client: Client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI - initialize and cleanup resources."""
    global temporal_client

    # Startup: Connect to Temporal
    temporal_server = os.environ.get("TEMPORAL_SERVER", "temporal:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "a2a-demo")

    logger.info(
        f"Connecting to Temporal at {temporal_server}",
        extra={"server": temporal_server, "namespace": temporal_namespace}
    )

    try:
        temporal_client = await Client.connect(
            temporal_server,
            namespace=temporal_namespace
        )
        logger.info("Successfully connected to Temporal")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        raise

    yield

    # Shutdown: Close Temporal connection
    if temporal_client:
        logger.info("Closing Temporal connection")


# Create FastAPI app
app = FastAPI(
    title="Agent B",
    description="A2A-enabled agent with crash recovery capabilities",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/a2a/message/send")
async def receive_message(request: Request):
    """
    A2A endpoint for receiving messages from other agents.

    This endpoint:
    1. Extracts message parameters from JSON-RPC 2.0 envelope
    2. Starts Temporal workflow if it doesn't exist (SignalWithStart pattern)
    3. Signals the workflow with the inbound message
    4. Returns JSON-RPC success response

    Expected request body (JSON-RPC 2.0):
    {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "taskId": "...",
            "messageId": "...",
            "replyTo": "...",
            "content": "..."
        },
        "id": "..."
    }
    """
    try:
        # Parse JSON-RPC request
        body = await request.json()
        params = body.get("params", {})

        task_id = params.get("taskId")
        message_id = params.get("messageId")
        reply_to = params.get("replyTo")
        content = params.get("content")

        # Validate required fields
        if not all([task_id, message_id, reply_to, content]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: taskId, messageId, replyTo, content"
            )

        logger.info(
            f"Received A2A message {message_id} for task {task_id}",
            extra={
                "event": "inbound_received",
                "taskId": task_id,
                "messageId": message_id
            }
        )

        # Start workflow if it doesn't exist, or get handle if it does
        workflow_id = f"task-{task_id}"

        try:
            # Try to signal existing workflow first
            workflow_handle = temporal_client.get_workflow_handle(workflow_id)

            # Signal the workflow with the inbound message
            await workflow_handle.signal(
                "inbound_message",
                {
                    "message_id": message_id,
                    "content": content,
                    "reply_to": reply_to
                }
            )

            logger.info(
                f"Signaled existing workflow {workflow_id}",
                extra={"taskId": task_id, "messageId": message_id}
            )

        except Exception:
            # Workflow doesn't exist, start it and signal simultaneously
            await temporal_client.start_workflow(
                TaskWorkflow.run,
                args=[task_id],
                id=workflow_id,
                task_queue=os.environ.get("TEMPORAL_TASK_QUEUE", "agent-b-tasks")
            )

            # Now signal it
            workflow_handle = temporal_client.get_workflow_handle(workflow_id)
            await workflow_handle.signal(
                "inbound_message",
                {
                    "message_id": message_id,
                    "content": content,
                    "reply_to": reply_to
                }
            )

            logger.info(
                f"Started and signaled new workflow {workflow_id}",
                extra={"taskId": task_id, "messageId": message_id}
            )

        # Return JSON-RPC success response
        return {
            "jsonrpc": "2.0",
            "result": {"status": "received"},
            "id": body.get("id", message_id)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error processing A2A message: {e}",
            extra={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/a2a/.well-known/agent-card")
async def get_agent_card():
    """
    Agent discovery endpoint - returns Agent B's metadata.

    Returns:
    {
        "name": "agent-b",
        "version": "1.0.0",
        "capabilities": [...],
        "endpoints": {...}
    }
    """
    agent_b_url = os.environ.get("AGENT_B_URL", "http://agent-b:8080")

    return {
        "name": "agent-b",
        "version": "1.0.0",
        "capabilities": ["chat", "task-execution", "llm-processing"],
        "endpoints": {
            "message/send": f"{agent_b_url}/a2a/message/send"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "agent": "agent-b"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

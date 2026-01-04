"""Temporal worker for Agent B - executes workflows and activities."""

import asyncio
import logging
import os
import signal
from temporalio.client import Client
from temporalio.worker import Worker

from src.workflows.task_workflow import TaskWorkflow
from src.activities.crash_worker import crash_worker
from src.activities.process_message import process_message
from src.activities.send_a2a_message import send_a2a_message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

# Global worker instance for graceful shutdown
worker_instance: Worker = None

async def main():
    """Initialize and run the Temporal worker."""
    global worker_instance

    # Get configuration from environment
    temporal_server = os.environ.get("TEMPORAL_SERVER", "temporal:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "a2a-demo")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "agent-b-tasks")

    logger.info(
        f"Starting Agent B worker",
        extra={
            "temporalServer": temporal_server,
            "namespace": temporal_namespace,
            "taskQueue": task_queue
        }
    )

    # Connect to Temporal server
    try:
        client = await Client.connect(
            temporal_server,
            namespace=temporal_namespace
        )
        logger.info("Successfully connected to Temporal server")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        raise

    # Create worker
    worker_instance = Worker(
        client,
        task_queue=task_queue,
        workflows=[TaskWorkflow],
        activities=[
            crash_worker,
            process_message,
            send_a2a_message
        ],
        max_concurrent_workflow_tasks=10,
        max_concurrent_activities=10
    )

    logger.info("Temporal worker created successfully")

    # Run worker
    try:
        logger.info("Starting worker - polling for tasks")
        await worker_instance.run()
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise


def handle_shutdown(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {sig}, initiating graceful shutdown")
    if worker_instance:
        asyncio.create_task(worker_instance.shutdown())


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise

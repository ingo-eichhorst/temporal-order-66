"""Activity that crashes the worker process - demonstrates Temporal recovery."""

import sys
from temporalio import activity


@activity.defn
async def crash_worker() -> None:
    """
    Crash the worker process to demonstrate Temporal's crash recovery.

    This activity is called when the trigger message [[TRIGGER:EXECUTE_ORDER_66]]
    is detected. It causes the entire worker process to exit with code 1, which
    simulates a catastrophic failure.

    Docker will restart the container (per restart: unless-stopped policy),
    and Temporal will replay the workflow history to recover state.
    """
    # Send heartbeat before crash to help Temporal detect worker death quickly
    activity.heartbeat()

    activity.logger.critical(
        "EXECUTING ORDER 66 - Worker process will now terminate",
        extra={"event": "worker_crash", "exit_code": 1}
    )

    # Crash the worker process
    # This will kill both the worker AND the HTTP server since they run
    # in the same container
    sys.exit(1)

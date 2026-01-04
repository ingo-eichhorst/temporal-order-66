"""Activity for sending A2A messages to other agents."""

import os
import httpx
from temporalio import activity


@activity.defn
async def send_a2a_message(
    recipient_url: str,
    task_id: str,
    message_id: str,
    content: str
) -> dict:
    """
    Send an A2A message to another agent using JSON-RPC 2.0 protocol.

    Args:
        recipient_url: The recipient's A2A endpoint URL (from replyTo field)
        task_id: Conversation thread identifier
        message_id: Unique message ID (deterministic: r-{original_message_id})
        content: Message payload (LLM response text)

    Returns:
        JSON-RPC response from recipient

    Raises:
        httpx.HTTPError: If request fails (handled by Temporal retry policy)
    """
    activity.logger.info(
        f"Sending A2A message {message_id} to {recipient_url}",
        extra={
            "event": "send_a2a_start",
            "taskId": task_id,
            "messageId": message_id,
            "recipientUrl": recipient_url
        }
    )

    # Get current agent's URL for replyTo field
    agent_b_url = os.environ.get("AGENT_B_URL", "http://agent-b:8080")
    reply_to_url = f"{agent_b_url}/a2a/message/send"

    # Construct JSON-RPC 2.0 message envelope
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "taskId": task_id,
            "messageId": message_id,
            "replyTo": reply_to_url,
            "content": content
        },
        "id": message_id  # Use message_id as JSON-RPC request ID
    }

    # Send HTTP POST request
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                recipient_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            # Raise exception for non-2xx responses
            response.raise_for_status()

            result = response.json()

            activity.logger.info(
                f"Successfully sent A2A message {message_id}",
                extra={
                    "event": "send_a2a_complete",
                    "taskId": task_id,
                    "messageId": message_id,
                    "statusCode": response.status_code
                }
            )

            return result

        except httpx.HTTPError as e:
            activity.logger.error(
                f"Failed to send A2A message {message_id}: {e}",
                extra={
                    "event": "send_a2a_error",
                    "taskId": task_id,
                    "messageId": message_id,
                    "error": str(e)
                }
            )
            # Re-raise for Temporal to handle retry
            raise

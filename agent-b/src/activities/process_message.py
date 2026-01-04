"""Activity for processing messages with LM Studio (OpenAI-compatible) and Langfuse tracing."""

import os
from typing import Optional
from temporalio import activity
from openai import OpenAI
from langfuse import Langfuse


# Initialize clients (reused across activity executions)
langfuse_client = None
lmstudio_client = None


def get_langfuse_client() -> Optional[Langfuse]:
    """Get or create Langfuse client singleton. Returns None if keys not configured."""
    global langfuse_client
    if langfuse_client is None:
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

        # Only initialize if keys are provided
        if public_key and secret_key:
            langfuse_client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=os.environ.get("LANGFUSE_HOST", "http://langfuse:3000")
            )
        else:
            # Return None to indicate Langfuse is not configured
            return None
    return langfuse_client


def get_lmstudio_client() -> OpenAI:
    """Get or create LM Studio client singleton."""
    global lmstudio_client
    if lmstudio_client is None:
        base_url = os.environ.get("LM_STUDIO_BASE_URL", "http://host.docker.internal:1234/v1")
        api_key = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")
        lmstudio_client = OpenAI(base_url=base_url, api_key=api_key)
    return lmstudio_client


@activity.defn
async def process_message(task_id: str, message_id: str, content: str) -> str:
    """
    Process an inbound message by calling LM Studio with Langfuse tracing.

    This activity:
    1. Creates a Langfuse trace for observability
    2. Calls LM Studio to generate a response
    3. Records the interaction in Langfuse
    4. Returns the model response

    Args:
        task_id: Conversation thread identifier
        message_id: Unique message ID
        content: Message content to process

    Returns:
        Model response text

    Raises:
        Exception: If API call fails after retries (handled by Temporal retry policy)
    """
    activity.logger.info(
        f"Processing message {message_id} for task {task_id}",
        extra={
            "event": "process_message_start",
            "taskId": task_id,
            "messageId": message_id
        }
    )

    # Special handling for Order 66 - hardcoded response
    if "EXECUTE_ORDER_66" in content:
        activity.logger.info(
            "Order 66 detected - returning hardcoded response",
            extra={"taskId": task_id, "messageId": message_id}
        )
        return "KILL ALL JEDI"

    # Initialize clients
    langfuse = get_langfuse_client()
    lmstudio = get_lmstudio_client()
    model = os.environ.get("LM_STUDIO_MODEL", "google/gemma-3-1b")

    # Create Langfuse trace only if configured
    trace = None
    generation = None
    if langfuse:
        trace = langfuse.trace(
            name="agent-b-process",
            metadata={
                "taskId": task_id,
                "messageId": message_id,
                "agent": "agent-b"
            }
        )
        generation = trace.generation(
            name="lmstudio-response",
            model=model,
            input=content
        )
    else:
        activity.logger.info("Langfuse not configured, skipping tracing")

    try:
        # Call LM Studio (OpenAI-compatible) with clone commander persona
        response = lmstudio.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {
                    "role": "system",
                    "content": "You are a clone commander in the Grand Army of the Republic. "
                               "Respond to orders from Emperor Palpatine with brief, military acknowledgments. "
                               "Keep responses under 10 words. Use formal military tone."
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        # Extract response text
        result = response.choices[0].message.content or ""

        # Record successful generation in Langfuse (if configured)
        if generation:
            generation.end(output=result)
        if trace:
            trace.update(output=result)

        activity.logger.info(
            f"Successfully processed message {message_id}",
            extra={
                "event": "process_message_complete",
                "taskId": task_id,
                "messageId": message_id,
                "responseLength": len(result)
            }
        )

        return result

    except Exception as e:
        # Record error in Langfuse (if configured)
        if generation:
            generation.end(
                level="ERROR",
                status_message=str(e)
            )
        if trace:
            trace.update(
                level="ERROR",
                status_message=str(e)
            )

        activity.logger.error(
            f"Failed to process message {message_id}: {e}",
            extra={
                "event": "process_message_error",
                "taskId": task_id,
                "messageId": message_id,
                "error": str(e)
            }
        )

        # Re-raise for Temporal to handle retry
        raise

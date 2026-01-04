/**
 * Activity for sending A2A messages to other agents.
 */

import { getLangfuseClient } from '../langfuse';

export interface SendA2AMessageParams {
  recipientUrl: string;
  taskId: string;
  messageId: string;
  replyTo: string;
  content: string;
}

export interface A2AResponse {
  jsonrpc: string;
  result?: any;
  error?: any;
  id: string;
}

/**
 * Send an A2A message to another agent using JSON-RPC 2.0 protocol.
 *
 * @param params Message parameters
 * @returns JSON-RPC response from recipient
 * @throws Error if request fails (handled by Temporal retry policy)
 */
export async function sendA2AMessage(params: SendA2AMessageParams): Promise<A2AResponse> {
  const { recipientUrl, taskId, messageId, replyTo, content } = params;

  console.log(`[Activity] Sending A2A message ${messageId} to ${recipientUrl}`);

  // Initialize Langfuse tracing (if configured)
  const langfuse = getLangfuseClient();
  const trace = langfuse?.trace({
    name: 'a2a-message-send',
    sessionId: taskId, // Link all traces from same task
    metadata: {
      agent: 'agent-a',
      taskId,
      messageId,
      recipientUrl,
    },
  });
  const span = trace?.span({
    name: 'http-post',
    input: { content },
  });

  // Construct JSON-RPC 2.0 message envelope
  const payload = {
    jsonrpc: '2.0',
    method: 'message/send',
    params: {
      taskId,
      messageId,
      replyTo,
      content,
    },
    id: messageId, // Use message ID as JSON-RPC request ID
  };

  try {
    // Send HTTP POST request using Node.js built-in fetch (available in Node 20+)
    const response = await fetch(recipientUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    // Check for HTTP errors
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    // Parse JSON response
    const result = await response.json() as A2AResponse;

    console.log(`[Activity] Successfully sent message ${messageId}`);

    // Record successful trace
    if (span) {
      span.end({ output: result });
    }
    if (trace) {
      trace.update({ output: { status: 'success', messageId } });
    }
    if (langfuse) {
      await langfuse.flushAsync();
    }

    return result;
  } catch (error) {
    console.error(`[Activity] Failed to send message ${messageId}:`, error);

    // Record error in trace
    if (span) {
      span.end({
        statusMessage: String(error),
      });
    }
    if (trace) {
      trace.update({
        output: { status: 'error', error: String(error) },
      });
    }
    if (langfuse) {
      await langfuse.flushAsync();
    }

    throw error; // Re-throw for Temporal to handle retry
  }
}

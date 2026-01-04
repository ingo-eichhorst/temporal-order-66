/**
 * Activity for sending A2A messages to other agents.
 */

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

    return result;
  } catch (error) {
    console.error(`[Activity] Failed to send message ${messageId}:`, error);
    throw error; // Re-throw for Temporal to handle retry
  }
}

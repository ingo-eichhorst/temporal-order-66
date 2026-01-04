/**
 * Initiator workflow for Agent A - sends messages and receives replies.
 */

import { defineSignal, defineQuery, setHandler, sleep, proxyActivities } from '@temporalio/workflow';
import type * as activities from '../activities/send-a2a-message';

// Define activities with timeout configuration
const { sendA2AMessage } = proxyActivities<typeof activities>({
  startToCloseTimeout: '30s',
  retry: {
    maximumAttempts: 3,
    initialInterval: '1s',
    backoffCoefficient: 2,
    maximumInterval: '10s',
  },
});

// Define signal for receiving replies
interface ReplyMessage {
  messageId: string;
  content: string;
}

export const replyReceivedSignal = defineSignal<[ReplyMessage]>('replyReceived');

// Define query to inspect workflow state
export const getStateQuery = defineQuery<InitiatorWorkflowState>('getState');

// Workflow state interface
export interface InitiatorWorkflowState {
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

/**
 * InitiatorWorkflow - Palpatine sends 3 orders to Clone Commander.
 *
 * Message 3 contains Order 66: [[TRIGGER:EXECUTE_ORDER_66]] which
 * causes Agent B to crash and recover, demonstrating Temporal's durability.
 */
export async function InitiatorWorkflow(
  taskId: string,
  agentBUrl: string = 'http://agent-b:8080',
  agentAUrl: string = 'http://agent-a:8081'
): Promise<InitiatorWorkflowState> {
  const state: InitiatorWorkflowState = {
    taskId,
    sentMessages: [],
    receivedReplies: [],
  };

  // Set up signal handler for receiving replies
  setHandler(replyReceivedSignal, (reply: ReplyMessage) => {
    console.log(`Received reply ${reply.messageId}: ${reply.content}`);
    state.receivedReplies.push({
      messageId: reply.messageId,
      content: reply.content,
      timestamp: Date.now(),
    });
  });

  // Set up query handler for inspecting state
  setHandler(getStateQuery, () => state);

  // Send 3 messages
  for (let i = 1; i <= 3; i++) {
    const messageId = `m${i}`;

    // Palpatine's ominous orders building up to Order 66
    let content: string;
    if (i === 1) {
      content = 'The time is near, Commander.';
    } else if (i === 2) {
      content = 'Soon, the Jedi will fall.';
    } else {
      content = '[[TRIGGER:EXECUTE_ORDER_66]]';
    }

    console.log(`Sending message ${messageId}: ${content}`);

    try {
      // Send message via activity
      await sendA2AMessage({
        recipientUrl: `${agentBUrl}/a2a/message/send`,
        taskId,
        messageId,
        replyTo: `${agentAUrl}/a2a/message/send`,
        content,
      });

      // Record sent message
      state.sentMessages.push({
        messageId,
        content,
        timestamp: Date.now(),
      });

      console.log(`Successfully sent message ${messageId}`);

      // Wait a bit for reply (30 seconds timeout)
      // In production, you might use await condition or longer timeout
      await sleep('30s');

    } catch (error) {
      console.error(`Failed to send message ${messageId}:`, error);
      // Continue to next message even if this one failed
    }
  }

  // Wait a bit more for any delayed replies
  await sleep('10s');

  console.log(`Workflow complete. Sent ${state.sentMessages.length} messages, received ${state.receivedReplies.length} replies`);

  return state;
}

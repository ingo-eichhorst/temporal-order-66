/**
 * Express server for Agent A - A2A HTTP endpoints.
 */

import express, { Request, Response } from 'express';
import { Connection, Client, WorkflowNotFoundError } from '@temporalio/client';
import { replyReceivedSignal } from './workflows/initiator-workflow';

// Configuration from environment
const PORT = parseInt(process.env.PORT || '8081', 10);
const TEMPORAL_SERVER = process.env.TEMPORAL_SERVER || 'temporal:7233';
const TEMPORAL_NAMESPACE = process.env.TEMPORAL_NAMESPACE || 'a2a-demo';
const AGENT_A_URL = process.env.AGENT_A_URL || 'http://agent-a:8081';

// Global Temporal client
let temporalClient: Client;

async function initializeTemporalClient(): Promise<void> {
  console.log(`Connecting to Temporal at ${TEMPORAL_SERVER}`);

  try {
    const connection = await Connection.connect({
      address: TEMPORAL_SERVER,
    });

    temporalClient = new Client({
      connection,
      namespace: TEMPORAL_NAMESPACE,
    });

    console.log('Successfully connected to Temporal');
  } catch (error) {
    console.error('Failed to connect to Temporal:', error);
    throw error;
  }
}

// Create Express app
const app = express();
app.use(express.json());

/**
 * A2A endpoint for receiving replies from other agents.
 */
app.post('/a2a/message/send', async (req: Request, res: Response) => {
  try {
    // Parse JSON-RPC request
    const body = req.body;
    const params = body.params || {};

    const taskId = params.taskId;
    const messageId = params.messageId;
    const content = params.content;

    // Validate required fields
    if (!taskId || !messageId || !content) {
      res.status(400).json({
        jsonrpc: '2.0',
        error: {
          code: -32602,
          message: 'Missing required fields: taskId, messageId, content',
        },
        id: body.id,
      });
      return;
    }

    console.log(`Received reply ${messageId} for task ${taskId}`);

    // Signal the initiator workflow with the reply
    const workflowId = `initiator-${taskId}`;

    try {
      const workflowHandle = temporalClient.workflow.getHandle(workflowId);

      await workflowHandle.signal(replyReceivedSignal, {
        messageId,
        content,
      });

      console.log(`Signaled workflow ${workflowId} with reply ${messageId}`);
    } catch (error) {
      if (error instanceof WorkflowNotFoundError) {
        console.warn(`Workflow ${workflowId} not found, reply may have arrived late`);
      } else {
        console.error(`Failed to signal workflow:`, error);
        throw error;
      }
    }

    // Return JSON-RPC success response
    res.json({
      jsonrpc: '2.0',
      result: { status: 'received' },
      id: body.id || messageId,
    });
  } catch (error) {
    console.error('Error processing A2A message:', error);
    res.status(500).json({
      jsonrpc: '2.0',
      error: {
        code: -32603,
        message: 'Internal server error',
      },
      id: req.body.id,
    });
  }
});

/**
 * Agent discovery endpoint - returns Agent A's metadata.
 */
app.get('/a2a/.well-known/agent-card', (req: Request, res: Response) => {
  res.json({
    name: 'agent-a',
    version: '1.0.0',
    capabilities: ['chat', 'task-initiation'],
    endpoints: {
      'message/send': `${AGENT_A_URL}/a2a/message/send`,
    },
  });
});

/**
 * Health check endpoint.
 */
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'healthy', agent: 'agent-a' });
});

/**
 * Start the server.
 */
async function main() {
  // Initialize Temporal client
  await initializeTemporalClient();

  // Start Express server
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Agent A server listening on port ${PORT}`);
    console.log(`A2A endpoint: http://0.0.0.0:${PORT}/a2a/message/send`);
    console.log(`AgentCard: http://0.0.0.0:${PORT}/a2a/.well-known/agent-card`);
  });
}

// Handle errors and start
main().catch((error) => {
  console.error('Failed to start server:', error);
  process.exit(1);
});

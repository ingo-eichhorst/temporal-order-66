/**
 * Demo driver - REST endpoint to trigger the 3-turn conversation.
 */

import express, { Request, Response } from 'express';
import { Connection, Client } from '@temporalio/client';
import { InitiatorWorkflow } from './workflows/initiator-workflow';

// Configuration from environment
const DEMO_DRIVER_PORT = parseInt(process.env.DEMO_DRIVER_PORT || '8082', 10);
const TEMPORAL_SERVER = process.env.TEMPORAL_SERVER || 'temporal:7233';
const TEMPORAL_NAMESPACE = process.env.TEMPORAL_NAMESPACE || 'a2a-demo';
const TASK_QUEUE = process.env.TEMPORAL_TASK_QUEUE || 'agent-a-tasks';

// Global Temporal client
let temporalClient: Client;

async function initializeTemporalClient(): Promise<void> {
  console.log(`[Demo Driver] Connecting to Temporal at ${TEMPORAL_SERVER}`);

  try {
    const connection = await Connection.connect({
      address: TEMPORAL_SERVER,
    });

    temporalClient = new Client({
      connection,
      namespace: TEMPORAL_NAMESPACE,
    });

    console.log('[Demo Driver] Successfully connected to Temporal');
  } catch (error) {
    console.error('[Demo Driver] Failed to connect to Temporal:', error);
    throw error;
  }
}

// Create Express app
const app = express();
app.use(express.json());

/**
 * POST /start-task - Start a new conversation task.
 *
 * Request body:
 * {
 *   "taskId": "demo-1",
 *   "turns": 3
 * }
 */
app.post('/start-task', async (req: Request, res: Response) => {
  try {
    const { taskId, turns = 3 } = req.body;

    if (!taskId) {
      res.status(400).json({
        error: 'Missing required field: taskId',
      });
      return;
    }

    console.log(`[Demo Driver] Starting task ${taskId} with ${turns} turns`);

    // Start the InitiatorWorkflow
    const workflowId = `initiator-${taskId}`;

    const agentBUrl = process.env.AGENT_B_URL || 'http://agent-b:8080';
    const agentAUrl = process.env.AGENT_A_URL || 'http://agent-a:8081';

    const handle = await temporalClient.workflow.start(InitiatorWorkflow, {
      taskQueue: TASK_QUEUE,
      workflowId,
      args: [taskId, agentBUrl, agentAUrl],
    });

    console.log(`[Demo Driver] Started workflow ${workflowId}`);

    res.json({
      success: true,
      taskId,
      workflowId,
      message: `Task ${taskId} started. Workflow ID: ${workflowId}`,
    });
  } catch (error) {
    console.error('[Demo Driver] Error starting task:', error);
    res.status(500).json({
      error: 'Failed to start task',
      details: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * GET /status/:taskId - Get status of a task.
 */
app.get('/status/:taskId', async (req: Request, res: Response) => {
  try {
    const { taskId } = req.params;
    const workflowId = `initiator-${taskId}`;

    const handle = temporalClient.workflow.getHandle(workflowId);
    const description = await handle.describe();

    res.json({
      taskId,
      workflowId,
      status: description.status.name,
      runId: description.runId,
    });
  } catch (error) {
    console.error('[Demo Driver] Error getting status:', error);
    res.status(500).json({
      error: 'Failed to get status',
      details: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * Health check endpoint.
 */
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'healthy', service: 'demo-driver' });
});

/**
 * Start the demo driver server.
 */
async function main() {
  // Initialize Temporal client
  await initializeTemporalClient();

  // Start Express server
  app.listen(DEMO_DRIVER_PORT, '0.0.0.0', () => {
    console.log(`[Demo Driver] Server listening on port ${DEMO_DRIVER_PORT}`);
    console.log(`[Demo Driver] Trigger demo: POST http://localhost:${DEMO_DRIVER_PORT}/start-task`);
  });
}

// Handle errors and start
main().catch((error) => {
  console.error('[Demo Driver] Failed to start:', error);
  process.exit(1);
});

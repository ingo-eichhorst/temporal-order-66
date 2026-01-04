/**
 * Temporal worker for Agent A - executes workflows and activities.
 */

import { NativeConnection, Worker } from '@temporalio/worker';
import * as activities from './activities/send-a2a-message';
import path from 'path';

// Configuration from environment
const TEMPORAL_SERVER = process.env.TEMPORAL_SERVER || 'temporal:7233';
const TEMPORAL_NAMESPACE = process.env.TEMPORAL_NAMESPACE || 'a2a-demo';
const TASK_QUEUE = process.env.TEMPORAL_TASK_QUEUE || 'agent-a-tasks';

async function main() {
  console.log(`[Worker] Starting Agent A worker`);
  console.log(`[Worker] Temporal server: ${TEMPORAL_SERVER}`);
  console.log(`[Worker] Namespace: ${TEMPORAL_NAMESPACE}`);
  console.log(`[Worker] Task queue: ${TASK_QUEUE}`);

  // Connect to Temporal server
  let connection: NativeConnection;
  try {
    connection = await NativeConnection.connect({
      address: TEMPORAL_SERVER,
    });
    console.log('[Worker] Successfully connected to Temporal server');
  } catch (error) {
    console.error('[Worker] Failed to connect to Temporal:', error);
    throw error;
  }

  // Create worker
  const worker = await Worker.create({
    connection,
    namespace: TEMPORAL_NAMESPACE,
    taskQueue: TASK_QUEUE,
    workflowsPath: path.join(__dirname, 'workflows'),
    activities,
    maxConcurrentWorkflowTaskExecutions: 10,
    maxConcurrentActivityTaskExecutions: 10,
  });

  console.log('[Worker] Worker created successfully');

  // Run worker
  try {
    console.log('[Worker] Starting worker - polling for tasks');
    await worker.run();
  } catch (error) {
    console.error('[Worker] Worker error:', error);
    throw error;
  }
}

// Handle shutdown gracefully
process.on('SIGINT', () => {
  console.log('[Worker] Received SIGINT, shutting down gracefully');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('[Worker] Received SIGTERM, shutting down gracefully');
  process.exit(0);
});

// Start worker
main().catch((error) => {
  console.error('[Worker] Fatal error:', error);
  process.exit(1);
});

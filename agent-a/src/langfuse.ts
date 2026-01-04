/**
 * Langfuse client singleton for Agent A tracing.
 */

import { Langfuse } from 'langfuse';

let langfuseClient: Langfuse | null = null;

/**
 * Get or create Langfuse client singleton.
 * Returns null if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not configured.
 */
export function getLangfuseClient(): Langfuse | null {
  if (langfuseClient === null) {
    const publicKey = process.env.LANGFUSE_PUBLIC_KEY || '';
    const secretKey = process.env.LANGFUSE_SECRET_KEY || '';

    // Only initialize if keys are provided
    if (publicKey && secretKey) {
      langfuseClient = new Langfuse({
        publicKey,
        secretKey,
        baseUrl: process.env.LANGFUSE_HOST || 'http://langfuse:3000',
      });
      console.log('[Langfuse] Client initialized');
    } else {
      console.log('[Langfuse] Keys not configured, tracing disabled');
    }
  }
  return langfuseClient;
}

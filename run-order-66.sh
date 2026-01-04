#!/bin/bash

# Order 66 Demo Script
# Starts the Palpatine → Clone Commander conversation and watches it in real-time

set -e

# Generate random task ID
TASK_ID="order-66-$(date +%s)"

echo "════════════════════════════════════════════════════════════════"
echo "   EXECUTING ORDER 66"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Task ID: $TASK_ID"
echo ""

# Start the task
echo "🎬 Initiating transmission from Palpatine..."
RESPONSE=$(curl -s -X POST http://localhost:8082/start-task \
  -H "Content-Type: application/json" \
  -d "{\"taskId\": \"$TASK_ID\", \"turns\": 3}")

# Check if successful
if echo "$RESPONSE" | grep -q "success"; then
    WORKFLOW_ID=$(echo "$RESPONSE" | jq -r '.workflowId')
    echo "✅ Workflow started: $WORKFLOW_ID"
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo "   OBSERVING CONVERSATION"
    echo "════════════════════════════════════════════════════════════════"
    echo ""

    # Function to watch logs with timeout
    watch_conversation() {
        local timeout=90
        local elapsed=0
        local interval=2

        echo "Waiting for conversation to complete (timeout: ${timeout}s)..."
        echo ""

        while [ $elapsed -lt $timeout ]; do
            # Check specifically for Order 66 completion (m3 reply)
            if docker-compose logs agent-a 2>/dev/null | grep "$TASK_ID" | grep -q "Received reply r-m3:"; then
                echo "✅ All 3 turns completed!"
                echo ""
                echo "💀 ORDER 66 EXECUTED"
                echo ""
                # Brief wait to ensure logs are flushed
                sleep 2
                break
            fi

            sleep $interval
            elapsed=$((elapsed + interval))
        done

        # Display the full conversation
        echo "════════════════════════════════════════════════════════════════"
        echo "   CONVERSATION TRANSCRIPT"
        echo "════════════════════════════════════════════════════════════════"
        echo ""

        docker-compose logs agent-a 2>/dev/null | grep "$TASK_ID" | grep -E "InitiatorWorkflow.*Sending message|InitiatorWorkflow.*Received reply" | while IFS= read -r line; do
            if echo "$line" | grep -q "Sending message m1:"; then
                MSG=$(echo "$line" | awk -F'Sending message m1: ' '{print $2}')
                echo "🔴 PALPATINE (m1): $MSG"
            elif echo "$line" | grep -q "Received reply r-m1:"; then
                MSG=$(echo "$line" | awk -F'Received reply r-m1: ' '{print $2}')
                echo "⚪ CLONE COMMANDER (r-m1): $MSG"
                echo ""
            elif echo "$line" | grep -q "Sending message m2:"; then
                MSG=$(echo "$line" | awk -F'Sending message m2: ' '{print $2}')
                echo "🔴 PALPATINE (m2): $MSG"
            elif echo "$line" | grep -q "Received reply r-m2:"; then
                MSG=$(echo "$line" | awk -F'Received reply r-m2: ' '{print $2}')
                echo "⚪ CLONE COMMANDER (r-m2): $MSG"
                echo ""
            elif echo "$line" | grep -q "Sending message m3:"; then
                MSG=$(echo "$line" | awk -F'Sending message m3: ' '{print $2}')
                echo "🔴 PALPATINE (m3): $MSG"
            elif echo "$line" | grep -q "Received reply r-m3:"; then
                MSG=$(echo "$line" | awk -F'Received reply r-m3: ' '{print $2}')
                echo "⚪ CLONE COMMANDER (r-m3): $MSG"
                echo ""
            fi
        done

        echo "════════════════════════════════════════════════════════════════"
        echo ""

        # Check if Order 66 was executed
        if docker-compose logs agent-b 2>/dev/null | grep "$TASK_ID" | grep -q "Order 66 detected"; then
            echo "💀 ORDER 66 EXECUTED - Checking for crash trigger..."
            echo ""

            # Show crash detection
            docker-compose logs agent-b 2>/dev/null | grep "$TASK_ID" | grep -E "Order 66|crash" | head -5
            echo ""
        fi

        echo "════════════════════════════════════════════════════════════════"
        echo "   WORKFLOW STATUS"
        echo "════════════════════════════════════════════════════════════════"
        echo ""

        # Get workflow status
        STATUS=$(curl -s http://localhost:8082/status/$TASK_ID)
        echo "$STATUS" | jq '.'

        echo ""
        echo "🔍 View in Temporal UI: http://localhost:8233"
        echo "   Workflow ID: $WORKFLOW_ID"
        echo ""
    }

    watch_conversation

else
    echo "❌ Failed to start workflow"
    echo "$RESPONSE" | jq '.'
    exit 1
fi

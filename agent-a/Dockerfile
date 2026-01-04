FROM node:20-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY package*.json ./
COPY tsconfig.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY src/ ./src/

# Build TypeScript
RUN npm run build

# Expose ports
EXPOSE 8081 8082

# Run worker, server, and demo-driver concurrently
CMD ["sh", "-c", "node dist/worker.js & node dist/server.js & node dist/demo-driver.js & wait"]

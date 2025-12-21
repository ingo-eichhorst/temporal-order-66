#!/bin/bash

# This script runs after the dev container is created

echo "Setting up development environment..."

# Install Python dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
fi

# Install Node dependencies if package.json exists
if [ -f "package.json" ]; then
    echo "Installing Node dependencies..."
    npm install
fi

echo "Development environment setup complete!"

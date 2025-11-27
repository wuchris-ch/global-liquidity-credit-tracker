#!/bin/bash

# Kill any existing processes on ports 8000 and 3000
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

echo "Starting API server on port 8000..."
uvicorn src.api:app --reload --port 8000 &
API_PID=$!

sleep 2

echo "Starting frontend on port 3000..."
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Services starting:"
echo "   API:      http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for both processes
wait $API_PID $FRONTEND_PID

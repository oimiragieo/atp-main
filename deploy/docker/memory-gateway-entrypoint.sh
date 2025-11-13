#!/bin/bash

# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

# Default values
PORT=${PORT:-8000}
ENVIRONMENT=${ENVIRONMENT:-production}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

# Wait for database to be ready
wait_for_db() {
    if [[ -n "${DATABASE_URL:-}" ]]; then
        log "Waiting for database to be ready..."
        
        local max_attempts=30
        local attempt=1
        
        while [[ $attempt -le $max_attempts ]]; do
            if python -c "
import asyncpg
import asyncio
import os
import sys

async def check_db():
    try:
        conn = await asyncpg.connect(os.environ['DATABASE_URL'])
        await conn.execute('SELECT 1')
        await conn.close()
        return True
    except Exception as e:
        print(f'Database not ready: {e}')
        return False

result = asyncio.run(check_db())
sys.exit(0 if result else 1)
"; then
                log "Database is ready"
                break
            fi
            
            log "Database not ready, attempt $attempt/$max_attempts"
            sleep 2
            ((attempt++))
        done
        
        if [[ $attempt -gt $max_attempts ]]; then
            log "ERROR: Database failed to become ready after $max_attempts attempts"
            exit 1
        fi
    fi
}

# Wait for Redis to be ready
wait_for_redis() {
    if [[ -n "${REDIS_URL:-}" ]]; then
        log "Waiting for Redis to be ready..."
        
        local max_attempts=30
        local attempt=1
        
        while [[ $attempt -le $max_attempts ]]; do
            if python -c "
import redis
import os
import sys

try:
    r = redis.from_url(os.environ['REDIS_URL'])
    r.ping()
    print('Redis is ready')
    sys.exit(0)
except Exception as e:
    print(f'Redis not ready: {e}')
    sys.exit(1)
"; then
                log "Redis is ready"
                break
            fi
            
            log "Redis not ready, attempt $attempt/$max_attempts"
            sleep 2
            ((attempt++))
        done
        
        if [[ $attempt -gt $max_attempts ]]; then
            log "ERROR: Redis failed to become ready after $max_attempts attempts"
            exit 1
        fi
    fi
}

# Initialize PII audit directories
init_pii_audit() {
    log "Initializing PII audit directories..."
    mkdir -p /app/pii_audit_logs
    
    # Set proper permissions
    chmod 755 /app/pii_audit_logs
    
    log "PII audit directories initialized"
}

# Start the memory gateway
start_gateway() {
    log "Starting ATP Memory Gateway..."
    log "Environment: $ENVIRONMENT"
    log "Port: $PORT"
    log "Log Level: $LOG_LEVEL"
    
    # Set Python path
    export PYTHONPATH="/app:$PYTHONPATH"
    
    # Start the service using uvicorn
    exec python -m uvicorn app:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        --log-level "$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')" \
        --access-log \
        --loop uvloop \
        --http httptools
}

# Health check endpoint
health_check() {
    curl -f "http://localhost:$PORT/health" || exit 1
}

# Main execution
case "${1:-gateway}" in
    "gateway")
        wait_for_db
        wait_for_redis
        init_pii_audit
        start_gateway
        ;;
    "health")
        health_check
        ;;
    *)
        log "Unknown command: $1"
        log "Available commands: gateway, health"
        exit 1
        ;;
esac
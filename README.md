# KnockLock IoT Backend

Phase 2 implementation of the KnockLock IoT backend using FastAPI + Redis + MQTT.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   FastAPI   │────▶│    Redis    │     │  Mosquitto  │
│   (API)     │     │  (State +   │     │   (MQTT)    │
│             │     │   Events)   │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                       │
       └───────────────────────────────────────┘
                    (MQTT Client)
```

## Features (Phase 2)

- **MQTT Ingest**: Parse, validate, and store MQTT messages
- **Event Stream**: All messages stored in Redis Stream for history
- **Device State**: Real-time device state with online/offline detection
- **REST API**: Get device state and events

## MQTT Library Choice

**Selected: `aiomqtt`** (async-native, formerly asyncio-mqtt)

**Justification:**
- **Async-Native**: aiomqtt provides a native async/await interface that integrates cleanly with FastAPI's async lifespan and event loop
- **No Threading Complexity**: Unlike paho-mqtt which uses callbacks and a separate network thread, aiomqtt handles this internally
- **Context Manager Support**: Clean context manager patterns that align with FastAPI's lifespan pattern
- **Modern Python**: Better type hints and modern Python patterns

Trade-off: paho-mqtt is more battle-tested and has more examples, but the async complexity it introduces outweighs this benefit for our use case.

## Project Structure

```
app/
├── main.py              # FastAPI app with lifespan
├── api/                 # REST API routers
│   ├── health.py        # Health check endpoints
│   ├── devices.py       # Device state and events endpoints
│   ├── patterns.py      # Pattern endpoints (placeholder)
│   └── users.py         # User endpoints (placeholder)
├── core/                # Core utilities
│   ├── settings.py      # Pydantic settings
│   ├── logging.py       # Logging configuration
│   └── security.py      # Security utilities (placeholder)
├── mqtt/                # MQTT client and handlers
│   ├── client.py        # MQTT client (connect/subscribe/publish)
│   ├── topics.py        # Topic utilities and constants
│   └── handlers.py      # Message handlers (parse, validate, store)
├── storage/             # Data storage
│   ├── redis.py         # Redis connection and helpers
│   ├── events.py        # Event stream operations
│   └── state.py         # Device state operations
├── models/              # Pydantic schemas
│   ├── common.py        # Meta, ErrorResponse
│   ├── mqtt.py          # MQTT payload models
│   └── state.py         # Device state models
└── services/            # Business logic
    └── device.py        # Device service (placeholder)
tests/
├── fixtures/            # Sample MQTT payloads
├── test_smoke.py        # Basic API smoke tests
├── test_mqtt_topics.py  # MQTT topic utility tests
├── test_mqtt_ingest.py  # MQTT handler tests
└── test_devices_api.py  # Device API tests
```

## MQTT Topics

### Subscribe (Device → Cloud)

| Topic Pattern | Description |
|--------------|-------------|
| `knocklock/v1/devices/+/telemetry` | Device telemetry (battery, RSSI, etc.) |
| `knocklock/v1/devices/+/knock/live` | Live knock pattern streaming |
| `knocklock/v1/devices/+/knock/result` | Knock recognition result |
| `knocklock/v1/devices/+/logs` | Device logs |
| `knocklock/v1/devices/+/commands/+/ack` | Command acknowledgments |

### Publish (Cloud → Device)

| Topic Pattern | Description |
|--------------|-------------|
| `knocklock/v1/devices/{device_id}/commands/{cmd_id}` | Send command |
| `knocklock/v1/devices/{device_id}/config` | Configuration update |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.11+ for local development

### Run with Docker

```bash
# Clone and navigate to project
cd StupidChest_Cloud

# Copy environment file
cp .env.example .env

# Start all services
docker compose up --build

# Or run in background
docker compose up -d --build
```

### Verify Installation

```bash
# Health check
curl http://localhost:8000/healthz

# Expected response:
# {"status":"healthy","environment":"development","version":"1.0.0"}
```

### Access Swagger UI

Open in browser: http://localhost:8000/docs

## Example Commands

### 1. Health Check

```bash
curl http://localhost:8000/healthz
```

### 2. Readiness Check (includes Redis status)

```bash
curl http://localhost:8000/readyz
```

### 3. Test MQTT - Telemetry Message

```bash
# Send telemetry with proper payload format
docker exec knocklock-mosquitto mosquitto_pub -h localhost -p 1883 \
  -t "knocklock/v1/devices/test-device-001/telemetry" \
  -m '{
    "meta": {"schema": "telemetry/v1", "ts": "2026-02-01T10:00:00Z"},
    "data": {"battery": 85, "rssi": -45, "uptime": 3600}
  }'
```

You should see the API container log:
```
Processing message: device=test-device-001, type=telemetry, size=xxx bytes
Telemetry processed: device=test-device-001, battery=85, rssi=-45
```

### 4. Test Knock Result Message

```bash
docker exec knocklock-mosquitto mosquitto_pub -h localhost -p 1883 \
  -t "knocklock/v1/devices/test-device-001/knock/result" \
  -m '{
    "meta": {"schema": "knock_result/v1", "ts": "2026-02-01T10:05:00Z"},
    "data": {"matched": true, "patternId": "secret-knock", "score": 0.95, "threshold": 0.8, "action": "unlock", "latencyMs": 150}
  }'
```

### 5. Test Logs Message

```bash
docker exec knocklock-mosquitto mosquitto_pub -h localhost -p 1883 \
  -t "knocklock/v1/devices/test-device-001/logs" \
  -m '{
    "meta": {"schema": "logs/v1", "ts": "2026-02-01T10:10:00Z"},
    "data": {"level": "info", "message": "Device started", "module": "main"}
  }'
```

### 6. Test Command Acknowledgment

```bash
docker exec knocklock-mosquitto mosquitto_pub -h localhost -p 1883 \
  -t "knocklock/v1/devices/test-device-001/commands/cmd-001/ack" \
  -m '{
    "meta": {"schema": "command_ack/v1", "ts": "2026-02-01T10:15:00Z"},
    "data": {"commandId": "cmd-001", "status": "success"}
  }'
```

### 7. Get Device State (after sending MQTT messages)

```bash
curl http://localhost:8000/api/v1/devices/test-device-001/state | jq
```

Expected response:
```json
{
  "deviceId": "test-device-001",
  "status": "online",
  "lastSeen": "2026-02-01T10:15:00Z",
  "updatedAt": "2026-02-01T10:15:00Z",
  "telemetry": {
    "battery": 85,
    "rssi": -45,
    "uptime": 3600,
    "ts": "2026-02-01T10:00:00Z"
  },
  "lastKnockResult": {
    "matched": true,
    "patternId": "secret-knock",
    "score": 0.95,
    "ts": "2026-02-01T10:05:00Z"
  }
}
```

### 8. Get Device Events

```bash
# Get all events
curl "http://localhost:8000/api/v1/devices/test-device-001/events" | jq

# Filter by event type
curl "http://localhost:8000/api/v1/devices/test-device-001/events?event_type=telemetry&limit=10" | jq
```

## Development

### Run Tests

```bash
# With Docker
docker compose exec api pytest

# Local (with dependencies installed)
pytest
```

### View Logs

```bash
# All services
docker compose logs -f

# API only
docker compose logs -f api

# MQTT broker
docker compose logs -f mosquitto
```

### Stop Services

```bash
docker compose down

# Remove volumes too
docker compose down -v
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | development | Environment (development/production) |
| `LOG_LEVEL` | INFO | Logging level |
| `REDIS_URL` | redis://redis:6379/0 | Redis connection URL |
| `MQTT_BROKER_HOST` | mosquitto | MQTT broker hostname |
| `MQTT_BROKER_PORT` | 1883 | MQTT broker port |
| `MQTT_USERNAME` | (empty) | MQTT authentication username |
| `MQTT_PASSWORD` | (empty) | MQTT authentication password |
| `MQTT_CLIENT_ID` | knocklock-api | MQTT client identifier |
| `MQTT_TOPIC_PREFIX` | knocklock/v1/devices | Topic prefix |
| `ONLINE_TTL_SEC` | 30 | Seconds before device is considered offline |
| `MAX_PAYLOAD_BYTES` | 256000 | Maximum MQTT payload size |
| `EVENT_STREAM_MAXLEN` | 10000 | Maximum events in Redis stream |

## API Endpoints

### Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe (checks Redis) |

### Device State

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/devices/{deviceId}/state` | GET | Get device state snapshot |
| `/api/v1/devices/{deviceId}/events` | GET | Get device events from stream |

**Note**: Devices are auto-registered when the first MQTT message is received.
No manual registration required.

## Redis Data Structure

| Key Pattern | Type | Description |
|-------------|------|-------------|
| `knocklock:device_state:{deviceId}` | String (JSON) | Device state snapshot |
| `knocklock:events` | Stream | All MQTT events |

## Phase 2 Status

✅ Completed:
- MQTT message parsing and validation
- Event stream persistence (Redis Stream)
- Device state management with online/offline detection
- Telemetry snapshot storage
- Knock result summary storage
- Device state REST API
- Device events REST API
- Pydantic v2 models for all payloads

🔲 Future Phases:
- Knock pattern CRUD and matching
- Command dispatch via MQTT
- User authentication (JWT)
- Real-time WebSocket streaming

## License

Proprietary - All rights reserved.

# AGP Federation Quickstart

## Overview

The Agent Gateway Protocol (AGP) enables inter-router federation for the ATP platform. This document provides a quickstart guide for implementing and using AGP sessions.

## AGP Session FSM

AGP uses a BGP-inspired finite state machine with the following states:

```
IDLE → CONNECT → OPEN_SENT → OPEN_CONFIRMED → ESTABLISHED
```

### State Transitions

- **IDLE**: Initial state, waiting for session start
- **CONNECT**: Attempting to establish TCP connection to peer
- **OPEN_SENT**: Connection established, OPEN message sent
- **OPEN_CONFIRMED**: OPEN message received from peer
- **ESTABLISHED**: Session fully established, exchanging routing information

## Basic Usage

### Creating a Session

```python
from router_service.agp_session_fsm import AGPSessionConfig, AGPSessionFSM, AGPEvent

# Configure the session
config = AGPSessionConfig(
    peer_address="192.168.1.100:179",
    peer_router_id="router-2",
    peer_adn=65001,
    keepalive_interval=10.0,
    hold_time=30.0
)

# Create FSM instance
fsm = AGPSessionFSM(config)

# Start the session
fsm.handle_event(AGPEvent.START)
```

### Session Management

```python
from router_service.agp_session_fsm import AGPSessionManager

# Create session manager
manager = AGPSessionManager()

# Add a session
session = manager.add_session("router-2", config)

# Start keepalive monitoring
manager.start_keepalive_monitor()

# Get session information
info = manager.get_all_sessions_info()
print(info)
```

### Event Handling

```python
# Register event handlers
def on_session_established():
    print("AGP session established!")

fsm.register_handler(AGPEvent.CONNECT_SUCCESS, on_session_established)
```

## Message Types

AGP supports the following message types:

- **OPEN**: Initialize session parameters
- **KEEPALIVE**: Maintain session liveness
- **UPDATE**: Exchange routing information (announce/withdraw routes)
- **NOTIFICATION**: Error reporting

## UPDATE Message Handling

### Route Attributes

AGP routes include comprehensive attributes for policy-based routing:

```python
from router_service.agp_update_handler import AGPRouteAttributes, AGPRoute

# Create route attributes
attrs = AGPRouteAttributes(
    path=[64512, 65001],  # ADN path vector
    next_hop="router-2",  # Next hop router ID
    local_pref=200,       # Local preference
    med=50,              # Multi-Exit Discriminator
    qos_supported=["gold", "silver"],
    capacity={
        "max_parallel": 128,
        "tokens_per_s": 2000000,
        "usd_per_s": 10.0
    },
    communities=["no-export?false", "region:us-east"]
)

# Create route
route = AGPRoute(
    prefix="reviewer.*",
    attributes=attrs,
    received_at=time.time(),
    peer_router_id="router-1"
)
```

### Route Table Management

```python
from router_service.agp_update_handler import AGPRouteTable

# Create route table
table = AGPRouteTable()

# Update routes
table.update_routes([route])

# Withdraw routes
table.withdraw_routes(["reviewer.*"], "router-1")

# Get best route
best = table.get_best_route("reviewer.*")

# Get route statistics
stats = table.get_stats()
```

### UPDATE Message Processing

```python
from router_service.agp_update_handler import AGPUpdateHandler, AGPUpdateMessage

# Create handler
handler = AGPUpdateHandler(route_table)

# Process UPDATE message
message = {
    "type": "UPDATE",
    "announce": [{
        "prefix": "reviewer.*",
        "attrs": {
            "path": [64512],
            "next_hop": "router-2"
        }
    }],
    "withdraw": ["summarizer.eu.*"]
}

routes, withdrawn = handler.handle_update(message, "router-1")
```

## Configuration Parameters

- `peer_address`: IP address and port of peer router
- `peer_router_id`: Unique identifier for peer router
- `peer_adn`: Autonomous Domain Number (ASN equivalent)
- `keepalive_interval`: Seconds between keepalive messages
- `hold_time`: Session timeout if no keepalive received
- `connect_retry_time`: Seconds to wait before retrying connection
- `max_keepalive_misses`: Maximum missed keepalives before timeout

## Monitoring

The AGP implementation provides built-in metrics:

- `agp_sessions_established_total`: Total sessions established
- `agp_session_state_changes_total`: Total state transitions
- `agp_keepalive_misses_total`: Total keepalive timeouts
- `agp_routes_active`: Current number of active routes
- `agp_route_updates_total`: Total route updates processed
- `agp_route_withdrawals_total`: Total route withdrawals processed
- `agp_update_messages_processed_total`: Total UPDATE messages processed
- `agp_update_parse_errors_total`: Total UPDATE parsing errors

Access metrics via the global registry:

```python
from metrics.registry import REGISTRY

routes_active = REGISTRY.gauge("agp_routes_active")
print(f"Active routes: {routes_active.value}")
```

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check peer address and firewall rules
2. **Keepalive Timeout**: Verify network connectivity and adjust `hold_time`
3. **State Stuck in CONNECT**: Check peer router configuration and network reachability

### Debug Information

```python
# Get detailed session info
session_info = fsm.get_session_info()
print(session_info)
```

## Integration with Router Service

The AGP FSM integrates with the main router service for:

- Automatic peer discovery
- Route exchange and propagation
- Session health monitoring
- Federation topology management

See the main router service documentation for complete integration details.

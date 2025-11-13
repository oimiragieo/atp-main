# Policy Change Approval Workflow

## Overview

The Policy Change Approval Workflow implements a comprehensive approval system for policy changes in the ATP (Autonomous Trust Platform). This system ensures that all policy modifications go through proper review and approval processes, supporting compliance with change management requirements (SOC2 CC7.1).

## Purpose

Policy changes in ATP can have significant security, compliance, and operational impacts. The approval workflow provides:

- **Controlled Changes**: Ensures policy modifications are reviewed and approved
- **Audit Trail**: Complete record of all approval actions and decisions
- **Multi-stage Approvals**: Support for different approval levels and stakeholders
- **Compliance**: Meets regulatory requirements for change management
- **Risk Mitigation**: Prevents unauthorized or poorly reviewed policy changes

## Architecture

### Core Components

#### PolicyChangeRequest
Represents a single policy change request with:
- **Metadata**: Request ID, type, requester, timestamps
- **Change Details**: Current vs proposed policy, justification
- **Approval State**: PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED
- **Audit Trail**: Complete history of all actions

#### PolicyApprovalWorkflow
Manages the approval process with:
- **Request Lifecycle**: Creation, approval, rejection, expiration
- **Persistence**: Automatic saving/loading of requests
- **Filtering**: Query requests by various criteria
- **Metrics**: Comprehensive tracking of approval metrics

#### PolicyChangeGating
Integrates approvals with policy enforcement:
- **Change Requests**: Submit policy changes for approval
- **Application**: Apply approved changes to target systems
- **Access Control**: Gate policy modifications based on permissions

## Usage

### Basic Workflow

```python
from tools.policy_approval_workflow import PolicyApprovalWorkflow, PolicyChangeGating

# Initialize the approval system
workflow = PolicyApprovalWorkflow()
gating = PolicyChangeGating(workflow)

# Create a policy change request
request_id = gating.request_policy_change(
    policy_type="ingestion_policy",
    policy_id="user_data_schema",
    change_type="update",
    current_policy={"allow_ingestion": True},
    proposed_policy={"allow_ingestion": False, "max_size_bytes": 1024},
    justification="Security hardening - limit data ingestion",
    requester="alice",
    required_approvers=["bob", "charlie"]
)

print(f"Created request: {request_id}")

# Check request status
request = workflow.get_request(request_id)
print(f"Status: {request.state.value}")

# Approve the request (as authorized approver)
workflow.approve_request(request_id, "bob", "Approved for security")
workflow.approve_request(request_id, "charlie", "Compliance review complete")

# Apply the approved change
if request.state == ApprovalState.APPROVED:
    success = gating.apply_approved_change(request_id, policy_system)
    print(f"Change applied: {success}")
```

### Advanced Usage

#### Multi-stage Approvals

```python
# Create request requiring multiple approval stages
request_id = workflow.create_request(
    policy_type="access_policy",
    policy_id="admin_role",
    change_type="create",
    current_policy=None,
    proposed_policy={"permissions": ["read", "write", "admin"]},
    justification="New admin role for compliance team",
    requester="alice",
    required_approvers=["security_team", "compliance_team", "it_ops"]
)

# Different teams can approve at different stages
workflow.approve_request(request_id, "security_team", "Security review passed")
workflow.approve_request(request_id, "compliance_team", "Compliance requirements met")
workflow.approve_request(request_id, "it_ops", "Operational review complete")
```

#### Request Management

```python
# List all pending requests
pending = workflow.list_requests(state=ApprovalState.PENDING)
print(f"Pending requests: {len(pending)}")

# List requests by requester
my_requests = workflow.list_requests(requester="alice")

# List requests by policy type
ingestion_requests = workflow.list_requests(policy_type="ingestion_policy")

# Process expired requests
expired = workflow.process_expired_requests()
print(f"Expired requests: {expired}")
```

## Approval States

### PENDING
- Initial state when request is created
- Awaiting required approvals
- Can be approved, rejected, cancelled, or expired

### APPROVED
- All required approvals received
- Change can be applied to the target system
- Final state - no further actions possible

### REJECTED
- Request was denied by an approver
- Includes rejection reason
- Final state - no further actions possible

### EXPIRED
- Request exceeded expiry time without completion
- Automatically processed by system
- Final state - no further actions possible

### CANCELLED
- Request was cancelled by the original requester
- Includes optional cancellation reason
- Final state - no further actions possible

## Configuration

### Approval Requirements

Configure required approvers based on:
- **Policy Type**: Different policies may need different approvers
- **Change Impact**: High-impact changes require more approvals
- **Organizational Structure**: Security, compliance, operations teams

```python
# Example approval requirements
APPROVAL_REQUIREMENTS = {
    "ingestion_policy": ["security_team", "data_team"],
    "access_policy": ["security_team", "compliance_team", "it_ops"],
    "network_policy": ["security_team", "network_team"],
}
```

### Expiry Settings

Configure request expiry times:
- **Default**: 7 days (168 hours)
- **Critical Changes**: 24 hours
- **Minor Changes**: 30 days

```python
EXPIRY_CONFIG = {
    "critical": 24,      # hours
    "normal": 168,       # hours (7 days)
    "minor": 720,        # hours (30 days)
}
```

## Integration Points

### Policy Systems

The approval workflow integrates with existing policy systems:

#### Schema Registry Policies
```python
from tools.schema_registry import IngestionPolicy

# Create approval-gated policy change
request_id = gating.request_policy_change(
    policy_type="ingestion_policy",
    policy_id="schema_123",
    change_type="update",
    current_policy=ingestion_policy.get_policy("schema_123"),
    proposed_policy={"allow_ingestion": False},
    justification="Security policy update",
    requester="alice",
    required_approvers=["security_team"]
)
```

### Access Control

Integration with RBAC/ABAC systems for permission checking:

```python
def check_policy_access(user: str, policy_type: str, policy_id: str) -> bool:
    """Check if user can request changes to a policy."""
    # Implementation depends on your access control system
    return rbac_system.has_permission(user, f"policy:{policy_type}:modify")
```

## Metrics and Monitoring

The system provides comprehensive metrics for monitoring:

### Counters
- `policy_change_requests_total`: Total requests created
- `policy_change_requests_approved_total`: Total approved requests
- `policy_change_requests_rejected_total`: Total rejected requests
- `policy_change_requests_expired_total`: Total expired requests

### Gauges
- `policy_change_requests_pending`: Current pending requests

### Histograms
- `policy_approval_latency_seconds`: Time to approval (buckets: 1h, 2h, 4h, 8h, 1w)

### Example Queries

```python
# Prometheus-style queries
pending_requests = REGISTRY.gauge("policy_change_requests_pending").value
approval_rate = (approved_total / requests_total) * 100
avg_approval_time = histogram_quantile(0.95, approval_latency)
```

## Security Considerations

### Authorization
- **Approver Validation**: Only designated approvers can approve requests
- **Requester Validation**: Only authorized users can create requests
- **State Validation**: Actions only allowed in appropriate states

### Audit Trail
- **Complete History**: All actions are logged with timestamps and users
- **Immutability**: Audit entries cannot be modified
- **Persistence**: Audit data survives system restarts

### Data Protection
- **Encryption**: Sensitive policy data should be encrypted at rest
- **Access Control**: Audit data access should be restricted
- **Retention**: Configure appropriate retention policies

## API Reference

### PolicyApprovalWorkflow

#### Methods
- `create_request(...)`: Create new approval request
- `approve_request(request_id, approver, comments)`: Approve request
- `reject_request(request_id, rejector, reason)`: Reject request
- `cancel_request(request_id, canceller, reason)`: Cancel request
- `get_request(request_id)`: Get request details
- `list_requests(state, requester, policy_type)`: List/filter requests
- `process_expired_requests()`: Process expired requests
- `get_pending_count()`: Get count of pending requests

### PolicyChangeGating

#### Methods
- `request_policy_change(...)`: Submit change for approval
- `apply_approved_change(request_id, policy_system)`: Apply approved change
- `check_policy_access(policy_type, policy_id, user)`: Check access permissions

## Error Handling

### Common Errors

#### Request Not Found
```python
try:
    workflow.approve_request("invalid-id", "alice")
except ValueError as e:
    print(f"Error: {e}")  # "Request invalid-id not found"
```

#### Unauthorized Approver
```python
try:
    workflow.approve_request(request_id, "unauthorized_user")
except ValueError as e:
    print(f"Error: {e}")  # "User unauthorized_user is not an authorized approver"
```

#### Invalid State
```python
try:
    workflow.approve_request(request_id, "alice")  # Already approved
except ValueError as e:
    print(f"Error: {e}")  # "Request request_id is not in pending state"
```

## Testing

Comprehensive test suite covers:

```bash
# Run approval workflow tests
python tests/test_policy_approval_workflow.py

# Test specific scenarios
python -m pytest tests/test_policy_approval_workflow.py::test_approval_workflow -v
python -m pytest tests/test_policy_approval_workflow.py::test_expiration_handling -v
```

## Troubleshooting

### Common Issues

**Requests not persisting**
- Check storage path permissions
- Verify disk space availability
- Check for file system errors

**Metrics not updating**
- Ensure metrics registry is properly initialized
- Check for import errors
- Verify metric names match registry definitions

**Approval authorization failing**
- Verify approver lists are correctly configured
- Check user authentication and authorization
- Review approval requirements configuration

## Compliance

### SOC2 CC7.1 Change Management
- ✅ **Change Requests**: All changes require formal requests
- ✅ **Approval Process**: Multi-level approval workflow
- ✅ **Audit Trail**: Complete change history
- ✅ **Testing**: Changes tested before implementation
- ✅ **Documentation**: Changes properly documented

### GDPR Article 25 Data Protection by Design
- ✅ **Privacy Impact Assessment**: Policy changes assessed for privacy impact
- ✅ **Approval Gates**: Privacy-related changes require specific approvals
- ✅ **Audit Trail**: Privacy change decisions are auditable

## Future Enhancements

### Planned Features
- **Email Notifications**: Automatic notifications for approval requests
- **Slack Integration**: Real-time approval notifications
- **Bulk Approvals**: Approve multiple related requests together
- **Approval Templates**: Pre-configured approval workflows
- **Reporting**: Advanced analytics and reporting
- **Integration APIs**: REST APIs for external system integration

## Contributing

When contributing to the approval workflow:

1. Add comprehensive tests for new features
2. Update documentation for API changes
3. Ensure backward compatibility
4. Follow security best practices
5. Update metrics for new functionality

## Related Documentation

- [ATP Security Architecture](../docs/security.md)
- [SOC2 Compliance Matrix](../docs/soc2_compliance.md)
- [Change Management Policy](../docs/change_management.md)
- [Audit Logging](../docs/audit_verification_tool.md)

# Enterprise Authentication System

The ATP Enterprise Authentication System provides comprehensive authentication and authorization capabilities for enterprise deployments, supporting multiple identity providers and advanced security features.

## Features

- **Multiple Identity Providers**: Support for OIDC, SAML, Okta, Azure AD, Auth0, and more
- **JWT Token Validation**: Secure token validation with JWKS support
- **Session Management**: Secure session handling with configurable expiration
- **Multi-Factor Authentication**: Optional MFA support with provider integration
- **Role-Based Access Control**: Fine-grained permissions and role mapping
- **Audit Logging**: Comprehensive audit trail for all authentication events
- **Backward Compatibility**: Seamless integration with existing admin keys system

## Quick Start

### 1. Basic Configuration

Create a `.env` file with your authentication settings:

```bash
# Enable enterprise authentication
AUTH_ENABLED_PROVIDERS=admin_keys,oidc

# Configure session settings
AUTH_SESSION_DURATION_HOURS=24
AUTH_REQUIRE_HTTPS=true

# Configure your identity provider
OIDC_CLIENT_ID=your_client_id
OIDC_CLIENT_SECRET=your_client_secret
OIDC_DISCOVERY_URL=https://your-provider.com/.well-known/openid_configuration
OIDC_REDIRECT_URI=https://your-atp-instance.com/auth/callback/oidc
```

### 2. Start the Service

The authentication system is automatically enabled when you start the ATP router service:

```bash
python -m router_service.service
```

### 3. Test Authentication

Test the authentication endpoints:

```bash
# List available providers
curl http://localhost:8000/auth/providers

# Login with admin key (legacy)
curl -X POST http://localhost:8000/auth/token \
  -d "username=admin&password=your_admin_key&provider=admin_keys"

# Get current user info
curl -H "X-Admin-API-Key: your_admin_key" \
  http://localhost:8000/auth/me
```

## Supported Identity Providers

### Admin Keys (Legacy)

The existing admin keys system is fully supported for backward compatibility:

```bash
# Environment variable
ROUTER_ADMIN_KEYS=key1:read+write,key2:admin

# Usage
curl -H "X-Admin-API-Key: key1" http://localhost:8000/auth/me
```

### Generic OIDC Provider

Configure any OIDC-compliant provider:

```bash
OIDC_CLIENT_ID=your_client_id
OIDC_CLIENT_SECRET=your_client_secret
OIDC_DISCOVERY_URL=https://provider.com/.well-known/openid_configuration
OIDC_ISSUER=https://provider.com
OIDC_AUDIENCE=your_audience
OIDC_REDIRECT_URI=https://your-domain.com/auth/callback/oidc
```

### Okta

```bash
OKTA_CLIENT_ID=your_okta_client_id
OKTA_CLIENT_SECRET=your_okta_client_secret
OKTA_DOMAIN=your-company.okta.com
OKTA_REDIRECT_URI=https://your-domain.com/auth/callback/okta
```

### Azure AD / Microsoft 365

```bash
AZURE_CLIENT_ID=your_azure_client_id
AZURE_CLIENT_SECRET=your_azure_client_secret
AZURE_TENANT_ID=your_tenant_id
AZURE_REDIRECT_URI=https://your-domain.com/auth/callback/azure_ad
```

### Auth0

```bash
AUTH0_CLIENT_ID=your_auth0_client_id
AUTH0_CLIENT_SECRET=your_auth0_client_secret
AUTH0_DOMAIN=your-company.auth0.com
AUTH0_REDIRECT_URI=https://your-domain.com/auth/callback/auth0
```

## Authentication Methods

### 1. OAuth/OIDC Flow

For web applications and interactive login:

1. Redirect user to `/auth/login/{provider}`
2. User authenticates with identity provider
3. Provider redirects to `/auth/callback/{provider}`
4. System creates session and sets secure cookie

### 2. API Key Authentication

For programmatic access (legacy admin keys):

```bash
curl -H "X-Admin-API-Key: your_key" http://localhost:8000/api/endpoint
```

### 3. JWT Bearer Token

For API access with JWT tokens:

```bash
curl -H "Authorization: Bearer your_jwt_token" http://localhost:8000/api/endpoint
```

### 4. Session Cookie

For web applications after OAuth login:

```bash
# Cookie is automatically set after successful OAuth login
curl -b "atp_session=session_id" http://localhost:8000/api/endpoint
```

## Role-Based Access Control

### Default Roles

- `read`: Read-only access to resources
- `write`: Read and write access to resources  
- `admin`: Full administrative access

### Role Mapping

Map identity provider groups to ATP roles:

```python
# In provider configuration
role_mapping = {
    "atp-admins": {"admin"},
    "atp-users": {"read", "write"},
    "atp-readonly": {"read"}
}
```

### Custom Claims

Configure custom claims for roles and groups:

```bash
# Azure AD example
AZURE_ROLE_CLAIM=roles
AZURE_GROUP_CLAIM=groups

# Okta example  
OKTA_ROLE_CLAIM=atp_roles
OKTA_GROUP_CLAIM=groups
```

## Multi-Factor Authentication

### Enable MFA

```bash
AUTH_MFA_ENABLED=true
AUTH_MFA_REQUIRED_FOR_ADMIN=true
AUTH_MFA_GRACE_PERIOD_MINUTES=60
```

### Provider-Specific MFA

```bash
OKTA_MFA_REQUIRED=true
AZURE_MFA_REQUIRED=true
```

MFA verification is handled by the identity provider. The ATP system validates the `amr` (Authentication Methods References) claim in JWT tokens.

## Session Management

### Configuration

```bash
AUTH_SESSION_DURATION_HOURS=24
AUTH_SESSION_CLEANUP_MINUTES=5
```

### Session Operations

```bash
# List active sessions (admin only)
curl -H "X-Admin-API-Key: admin_key" http://localhost:8000/auth/sessions

# Revoke specific session (admin only)
curl -X DELETE -H "X-Admin-API-Key: admin_key" \
  http://localhost:8000/auth/sessions/session_id

# Logout (revoke current session)
curl -X POST http://localhost:8000/auth/logout
```

## Security Features

### HTTPS and Secure Cookies

```bash
AUTH_REQUIRE_HTTPS=true
AUTH_SECURE_COOKIES=true
```

### CSRF Protection

```bash
AUTH_CSRF_PROTECTION=true
```

### Rate Limiting

```bash
AUTH_RATE_LIMIT_PER_MINUTE=60
AUTH_MAX_FAILED_ATTEMPTS=5
AUTH_FAILED_LOGIN_LOCKOUT_MINUTES=15
```

### JWT Security

```bash
AUTH_JWT_ALGORITHM=HS256
AUTH_JWT_EXPIRATION_MINUTES=60
```

## Audit Logging

All authentication events are logged for security and compliance:

```bash
AUTH_AUDIT_ALL_EVENTS=true
AUTH_AUDIT_RETENTION_DAYS=90
```

Audit events include:
- Login attempts (success/failure)
- Session creation/expiration
- Token refresh
- Permission checks
- Administrative actions

## API Reference

### Authentication Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/providers` | GET | List available providers |
| `/auth/login/{provider}` | GET | Initiate OAuth login |
| `/auth/callback/{provider}` | GET | OAuth callback handler |
| `/auth/token` | POST | Create API token |
| `/auth/refresh` | POST | Refresh access token |
| `/auth/me` | GET | Get current user info |
| `/auth/logout` | POST | Logout and revoke session |
| `/auth/sessions` | GET | List sessions (admin) |
| `/auth/sessions/{id}` | DELETE | Revoke session (admin) |
| `/auth/config` | GET | Get auth config (admin) |
| `/auth/config/{provider}` | PUT | Update provider config (admin) |

### Authentication Headers

| Header | Description | Example |
|--------|-------------|---------|
| `Authorization` | JWT Bearer token | `Bearer eyJ0eXAiOiJKV1Q...` |
| `X-Admin-API-Key` | Admin API key | `your_admin_key` |
| `Cookie` | Session cookie | `atp_session=session_id` |

## Integration Examples

### Python SDK

```python
import httpx

# Using admin key
client = httpx.Client(
    headers={"X-Admin-API-Key": "your_admin_key"}
)

# Using JWT token
client = httpx.Client(
    headers={"Authorization": "Bearer your_jwt_token"}
)

response = client.get("http://localhost:8000/auth/me")
user_info = response.json()
```

### JavaScript/Node.js

```javascript
// Using fetch with JWT
const response = await fetch('http://localhost:8000/auth/me', {
  headers: {
    'Authorization': 'Bearer your_jwt_token'
  }
});

const userInfo = await response.json();
```

### cURL Examples

```bash
# Get user info with admin key
curl -H "X-Admin-API-Key: your_key" \
  http://localhost:8000/auth/me

# Get user info with JWT
curl -H "Authorization: Bearer your_jwt" \
  http://localhost:8000/auth/me

# Login with OAuth (redirects to provider)
curl -L http://localhost:8000/auth/login/okta?redirect_url=/dashboard
```

## Troubleshooting

### Common Issues

1. **Provider not found**: Check `AUTH_ENABLED_PROVIDERS` configuration
2. **Invalid JWT**: Verify issuer, audience, and signing key configuration
3. **Session expired**: Check `AUTH_SESSION_DURATION_HOURS` setting
4. **HTTPS required**: Set `AUTH_REQUIRE_HTTPS=false` for development only

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
python -m router_service.service
```

### Health Checks

Check authentication system health:

```bash
curl http://localhost:8000/auth/providers
curl http://localhost:8000/healthz
```

## Migration from Admin Keys

The enterprise authentication system is fully backward compatible with the existing admin keys system:

1. **Existing keys continue to work**: No changes required for existing API clients
2. **Gradual migration**: Enable new providers alongside admin keys
3. **Role mapping**: Map existing admin key roles to new RBAC system
4. **Audit trail**: All authentication methods are logged consistently

### Migration Steps

1. Configure new identity provider alongside admin keys:
   ```bash
   AUTH_ENABLED_PROVIDERS=admin_keys,oidc
   ```

2. Test new provider with limited users

3. Gradually migrate users to new provider

4. Eventually disable admin keys:
   ```bash
   AUTH_ENABLED_PROVIDERS=oidc
   ```

## Production Deployment

### Security Checklist

- [ ] Enable HTTPS (`AUTH_REQUIRE_HTTPS=true`)
- [ ] Use secure cookies (`AUTH_SECURE_COOKIES=true`)
- [ ] Enable CSRF protection (`AUTH_CSRF_PROTECTION=true`)
- [ ] Configure appropriate session duration
- [ ] Enable MFA for admin users
- [ ] Set up proper rate limiting
- [ ] Configure audit log retention
- [ ] Use strong JWT signing keys
- [ ] Validate redirect URIs in identity provider
- [ ] Monitor authentication metrics

### High Availability

- Use Redis for session storage in multi-instance deployments
- Configure load balancer session affinity if using in-memory sessions
- Set up monitoring and alerting for authentication failures
- Implement circuit breakers for identity provider calls

### Monitoring

Key metrics to monitor:
- Authentication success/failure rates
- Session creation/expiration rates
- Token refresh rates
- MFA challenge/success rates
- Provider response times
- Rate limiting hits

## Support

For issues and questions:
- Check the troubleshooting section above
- Review audit logs for authentication events
- Enable debug logging for detailed information
- Consult identity provider documentation for provider-specific issues
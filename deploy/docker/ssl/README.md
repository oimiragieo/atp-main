# SSL Certificates for ATP Router mTLS

This directory contains SSL certificates for mutual TLS authentication between the reverse proxy and router.

## Certificate Files

- `ca.crt` - Certificate Authority certificate
- `ca.key` - Certificate Authority private key
- `server.crt` - Server certificate for nginx reverse proxy
- `server.key` - Server private key
- `client.crt` - Client certificate for router authentication
- `client.key` - Client private key

## Generating Certificates

Use the certificate rotation script to generate certificates:

```bash
# Generate all certificates
python tools/cert_rotation.py --generate-all

# Or generate individually
python tools/cert_rotation.py --generate-ca
python tools/cert_rotation.py --generate-server
python tools/cert_rotation.py --generate-client
```

## Docker Deployment

The certificates in this directory are mounted into the nginx container for mTLS configuration.

## Security Notes

- Keep private keys secure and never commit them to version control
- Rotate certificates regularly (recommended: every 90 days for server certs, 365 days for CA)
- Use strong passphrases for private keys in production
- Validate certificate chains before deployment

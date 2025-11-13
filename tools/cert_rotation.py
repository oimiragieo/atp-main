#!/usr/bin/env python3
"""
Certificate Rotation Script for ATP Router

Generates and rotates SSL certificates for mTLS between reverse proxy and router.
This script creates a Certificate Authority (CA), server certificates, and client certificates.
"""

import subprocess
from pathlib import Path


class CertificateAuthority:
    """Manages CA certificate and key generation."""

    def __init__(self, ca_dir: str = "certs"):
        self.ca_dir = Path(ca_dir)
        self.ca_dir.mkdir(exist_ok=True)
        self.ca_key = self.ca_dir / "ca.key"
        self.ca_cert = self.ca_dir / "ca.crt"

    def generate_ca(self, validity_days: int = 3650) -> None:
        """Generate a new Certificate Authority."""
        print("Generating Certificate Authority...")

        # Generate CA private key
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "genrsa",
                "-out",
                str(self.ca_key),
                "4096",
            ],
            check=True,
        )

        # Generate CA certificate
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "req",
                "-new",
                "-x509",
                "-days",
                str(validity_days),
                "-key",
                str(self.ca_key),
                "-sha256",
                "-out",
                str(self.ca_cert),
                "-subj",
                "/C=US/ST=State/L=City/O=ATP/CN=ATP-CA",
            ],
            check=True,
        )

        print(f"CA certificate generated: {self.ca_cert}")

    def generate_server_cert(self, hostname: str = "router", validity_days: int = 365) -> None:
        """Generate server certificate signed by CA."""
        print(f"Generating server certificate for {hostname}...")

        key_file = self.ca_dir / f"{hostname}.key"
        csr_file = self.ca_dir / f"{hostname}.csr"
        cert_file = self.ca_dir / f"{hostname}.crt"

        # Generate server private key
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "genrsa",
                "-out",
                str(key_file),
                "2048",
            ],
            check=True,
        )

        # Generate certificate signing request
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "req",
                "-subj",
                f"/C=US/ST=State/L=City/O=ATP/CN={hostname}",
                "-new",
                "-key",
                str(key_file),
                "-out",
                str(csr_file),
            ],
            check=True,
        )

        # Generate server certificate
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "x509",
                "-req",
                "-days",
                str(validity_days),
                "-in",
                str(csr_file),
                "-CA",
                str(self.ca_cert),
                "-CAkey",
                str(self.ca_key),
                "-CAcreateserial",
                "-out",
                str(cert_file),
                "-sha256",
            ],
            check=True,
        )

        # Clean up CSR
        csr_file.unlink(missing_ok=True)

        print(f"Server certificate generated: {cert_file}")

    def generate_client_cert(self, client_name: str = "client", validity_days: int = 365) -> None:
        """Generate client certificate signed by CA."""
        print(f"Generating client certificate for {client_name}...")

        key_file = self.ca_dir / f"{client_name}.key"
        csr_file = self.ca_dir / f"{client_name}.csr"
        cert_file = self.ca_dir / f"{client_name}.crt"

        # Generate client private key
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "genrsa",
                "-out",
                str(key_file),
                "2048",
            ],
            check=True,
        )

        # Generate certificate signing request
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "req",
                "-subj",
                f"/C=US/ST=State/L=City/O=ATP/CN={client_name}",
                "-new",
                "-key",
                str(key_file),
                "-out",
                str(csr_file),
            ],
            check=True,
        )

        # Generate client certificate
        subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
            [
                "openssl",  # noqa: S607
                "x509",
                "-req",
                "-days",
                str(validity_days),
                "-in",
                str(csr_file),
                "-CA",
                str(self.ca_cert),
                "-CAkey",
                str(self.ca_key),
                "-CAcreateserial",
                "-out",
                str(cert_file),
                "-sha256",
            ],
            check=True,
        )

        # Clean up CSR
        csr_file.unlink(missing_ok=True)

        print(f"Client certificate generated: {cert_file}")

    def verify_cert(self, cert_file: str) -> bool:
        """Verify a certificate against the CA."""
        try:
            result = subprocess.run(  # noqa: S603,S607 - openssl command with controlled arguments
                [
                    "openssl",  # noqa: S607
                    "verify",
                    "-CAfile",
                    str(self.ca_cert),
                    cert_file,
                ],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate and rotate SSL certificates for ATP mTLS")
    parser.add_argument("--ca-dir", default="certs", help="Directory to store certificates")
    parser.add_argument("--hostname", default="router", help="Server hostname for certificate")
    parser.add_argument("--client-name", default="client", help="Client name for certificate")
    parser.add_argument("--validity-days", type=int, default=365, help="Certificate validity in days")
    parser.add_argument("--generate-ca", action="store_true", help="Generate new CA certificate")
    parser.add_argument("--generate-server", action="store_true", help="Generate server certificate")
    parser.add_argument("--generate-client", action="store_true", help="Generate client certificate")
    parser.add_argument("--generate-all", action="store_true", help="Generate all certificates")

    args = parser.parse_args()

    ca = CertificateAuthority(args.ca_dir)

    if args.generate_all:
        args.generate_ca = True
        args.generate_server = True
        args.generate_client = True

    if args.generate_ca:
        ca.generate_ca()

    if args.generate_server:
        if not ca.ca_cert.exists():
            print("CA certificate not found. Generate CA first with --generate-ca")
            return 1
        ca.generate_server_cert(args.hostname, args.validity_days)

    if args.generate_client:
        if not ca.ca_cert.exists():
            print("CA certificate not found. Generate CA first with --generate-ca")
            return 1
        ca.generate_client_cert(args.client_name, args.validity_days)

    # Verify certificates if they exist
    server_cert = ca.ca_dir / f"{args.hostname}.crt"
    client_cert = ca.ca_dir / f"{args.client_name}.crt"

    if server_cert.exists():
        if ca.verify_cert(str(server_cert)):
            print(f"✅ Server certificate verified: {server_cert}")
        else:
            print(f"❌ Server certificate verification failed: {server_cert}")

    if client_cert.exists():
        if ca.verify_cert(str(client_cert)):
            print(f"✅ Client certificate verified: {client_cert}")
        else:
            print(f"❌ Client certificate verification failed: {client_cert}")

    print(f"\nCertificates generated in: {ca.ca_dir}")
    print("Copy certificates to deploy/docker/ssl/ for Docker deployment")


if __name__ == "__main__":
    exit(main())

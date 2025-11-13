import ssl
from typing import Optional


def build_server_context(
    ca_path: Optional[str], cert_path: Optional[str], key_path: Optional[str], require_client_cert: bool = True
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("HIGH:!aNULL:!MD5")
    if cert_path and key_path:
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    if ca_path:
        ctx.load_verify_locations(cafile=ca_path)
    if require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def build_client_context(
    ca_path: Optional[str], cert_path: Optional[str] = None, key_path: Optional[str] = None, hostname_check: bool = True
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("HIGH:!aNULL:!MD5")
    if ca_path:
        ctx.load_verify_locations(cafile=ca_path)
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if cert_path and key_path:
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    ctx.check_hostname = bool(hostname_check)
    return ctx

# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the ssl check operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- SSL/TLS Certificate Check (tools/py/ssl_check.py)
# ============================================================================
#
# WHAT THIS DOES:
#   Tests the secure connection (HTTPS) to your Azure API endpoint by
#   performing a full SSL/TLS handshake. Think of it like verifying that
#   your encrypted radio channel is properly configured -- both sides
#   need to agree on the encryption method and trust each other's ID.
#
# WHAT IT SHOWS:
#   - Whether the SSL handshake succeeds
#   - Which TLS version is being used (TLSv1.2 or TLSv1.3)
#   - The encryption cipher in use
#   - Who issued the server's certificate (should be Microsoft/DigiCert)
#   - When the certificate expires
#
# MOST COMMON FAILURE:
#   "Certificate verification failed" -- This almost always means a
#   corporate proxy is intercepting your HTTPS traffic and replacing
#   the real certificate with its own. The fix is to get the corporate
#   CA certificate from IT and set REQUESTS_CA_BUNDLE to point to it.
#
# HOW TO USE:
#   python tools/py/ssl_check.py
# ============================================================================
import ssl
import socket
from urllib.parse import urlparse

try:
    import keyring
except ImportError:
    print("  [FAIL] keyring package not installed.")
    print("  Fix: pip install keyring==23.13.1")
    exit(1)

endpoint = keyring.get_password("hybridrag", "azure_endpoint")
if not endpoint:
    print("  No endpoint stored. Run rag-store-endpoint first.")
    exit(1)

parsed = urlparse(endpoint)
host = parsed.hostname

print(f"  Testing SSL to: {host}")
print(f"  Python SSL version: {ssl.OPENSSL_VERSION}")
print()

ctx = ssl.create_default_context()
try:
    with ctx.wrap_socket(socket.socket(), server_hostname=host) as s:
        s.settimeout(10)
        s.connect((host, 443))
        cert = s.getpeercert()
        print(f"  [OK] SSL handshake successful")
        print(f"  Protocol: {s.version()}")
        print(f"  Cipher:   {s.cipher()[0]}")
        if cert:
            subject = dict(x[0] for x in cert.get("subject", []))
            issuer = dict(x[0] for x in cert.get("issuer", []))
            print(f"  Subject:  {subject.get('commonName', 'unknown')}")
            print(f"  Issuer:   {issuer.get('organizationName', 'unknown')}")
            print(f"  Expires:  {cert.get('notAfter', 'unknown')}")

except ssl.SSLCertVerificationError as e:
    print(f"  [FAIL] Certificate verification failed")
    print(f"  Error: {e}")
    print()
    print("  This usually means a corporate proxy is intercepting HTTPS.")
    print("  Ask IT for the corporate CA certificate, then:")
    print("    $env:REQUESTS_CA_BUNDLE = 'path\\to\\corporate-ca.pem'")

except Exception as e:
    print(f"  [FAIL] {e}")
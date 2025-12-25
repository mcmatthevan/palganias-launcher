"""
PyInstaller runtime hook to configure SSL certificate bundle.
Sets SSL_CERT_FILE and REQUESTS_CA_BUNDLE to certifi's CA file at runtime,
so HTTPS requests succeed in frozen applications (Linux/macOS).
"""
import os

try:
    import certifi
    cafile = certifi.where()
    # Only set if not already provided by environment/user
    os.environ.setdefault("SSL_CERT_FILE", cafile)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", cafile)
except Exception:
    # Best-effort; if certifi is missing or fails, do nothing
    pass

"""Vercel Python Serverless Entrypoint exposing BaseHTTPRequestHandler `handler`."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server import AufbruchRequestHandler  # noqa: E402


class handler(AufbruchRequestHandler):
    """Vercel Serverless Function HTTP handler for all /api/* routes."""
    pass

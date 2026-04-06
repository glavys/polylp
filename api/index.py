"""Vercel serverless entry point — re-exports the FastAPI ASGI app."""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `polylp` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from polylp.server import app  # noqa: E402,F401

"""ag402-openclaw: Ag402 adapter for OpenClaw.

Bridges Ag402 x402 auto-payment into the OpenClaw agent framework via
mcporter. OpenClaw agents can call paid HTTP APIs transparently — the
adapter handles 402 negotiation, payment, and retry behind the scenes.

Integration via mcporter (recommended):
    mcporter config add ag402 \\
        --command python -m ag402_openclaw.bridge \\
        --scope home

Or use the ag402 CLI:
    ag402 install openclaw
"""

__version__ = "0.1.9"

from ag402_openclaw.bridge import OpenClawBridge

__all__ = ["__version__", "OpenClawBridge"]

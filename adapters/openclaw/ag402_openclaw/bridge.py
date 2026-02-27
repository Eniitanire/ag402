"""OpenClaw bridge adapter for Ag402 x402 auto-payment.

Provides an HTTP proxy bridge that OpenClaw agents use to make paid API
calls. The bridge intercepts outbound requests, detects 402 Payment
Required responses, automatically pays via Solana USDC, and returns the
paid response to the calling agent.

Architecture:
    OpenClaw Agent → mcporter → ag402-openclaw (this bridge) → Paid API

Usage (standalone):
    ag402-openclaw --port 14022

Usage (via mcporter):
    mcporter config add ag402 --command python -m ag402_openclaw.bridge --scope home

The bridge exposes a single endpoint:
    POST /proxy
    Body: {"url": "...", "method": "GET", "headers": {...}, "body": "..."}
    Response: {"status_code": 200, "body": "...", "payment_made": true, ...}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger("ag402_openclaw.bridge")


class OpenClawBridge:
    """HTTP proxy bridge for OpenClaw agents with x402 auto-payment.

    Wraps ag402-core middleware and exposes a simple JSON-RPC interface
    that OpenClaw agents (via mcporter) can call to make paid HTTP requests.
    """

    def __init__(self) -> None:
        self._middleware: Any = None
        self._wallet: Any = None
        self._initialized = False
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def ensure_initialized(self) -> None:
        """Lazily initialize ag402-core components."""
        if self._initialized:
            return

        async with self._get_lock():
            if self._initialized:
                return

            from ag402_core.config import load_config
            from ag402_core.middleware.x402_middleware import X402PaymentMiddleware
            from ag402_core.payment.registry import PaymentProviderRegistry
            from ag402_core.wallet.agent_wallet import AgentWallet

            config = load_config()

            self._wallet = AgentWallet(db_path=config.wallet_db_path)
            await self._wallet.init_db()

            if config.is_test_mode:
                balance = await self._wallet.get_balance()
                if balance == 0:
                    await self._wallet.deposit(100.0, note="ag402-openclaw auto-fund (test mode)")
                    logger.info("[init] Test mode: auto-funded 100.0 virtual USD")

            provider = PaymentProviderRegistry.get_provider(config=config)
            self._middleware = X402PaymentMiddleware(
                wallet=self._wallet,
                provider=provider,
                config=config,
            )
            self._initialized = True

            mode_label = "TEST" if config.is_test_mode else "PRODUCTION"
            logger.info("[init] OpenClaw bridge initialized (mode=%s)", mode_label)

    async def proxy_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        max_amount: float | None = None,
    ) -> dict:
        """Proxy an HTTP request with automatic x402 payment.

        Args:
            url: Target API URL.
            method: HTTP method (GET, POST, etc.).
            headers: Optional request headers.
            body: Optional request body string.
            max_amount: Maximum amount willing to pay (USD).

        Returns:
            Dict with status_code, body, headers, payment_made, amount_paid,
            tx_hash, and error fields.
        """
        await self.ensure_initialized()

        method = method.upper()
        body_bytes = body.encode("utf-8") if body else None

        try:
            result = await self._middleware.handle_request(
                method=method,
                url=url,
                headers=headers,
                body=body_bytes,
                max_amount=max_amount,
            )

            body_text = ""
            if result.body:
                try:
                    body_text = result.body.decode("utf-8")
                except UnicodeDecodeError:
                    body_text = f"<binary data, {len(result.body)} bytes>"

            return {
                "status_code": result.status_code,
                "body": body_text,
                "headers": result.headers,
                "payment_made": result.payment_made,
                "amount_paid": result.amount_paid,
                "tx_hash": result.tx_hash,
                "error": result.error,
            }

        except Exception as exc:
            logger.exception("[proxy] Request failed")
            return {
                "status_code": 500,
                "body": "",
                "headers": {},
                "payment_made": False,
                "amount_paid": 0.0,
                "tx_hash": "",
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def shutdown(self) -> None:
        """Cleanup resources."""
        if self._middleware is not None:
            await self._middleware.close()
            self._middleware = None
        if self._wallet is not None:
            await self._wallet.close()
            self._wallet = None
        self._initialized = False


async def _run_stdio_bridge(bridge: OpenClawBridge) -> None:
    """Run the bridge in stdio mode (for mcporter).

    Reads JSON-RPC-style requests from stdin, one per line.
    Writes JSON responses to stdout, one per line.
    """
    logger.info("[bridge] Running in stdio mode")
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            try:
                request = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                response = {"error": "Invalid JSON input"}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            result = await bridge.proxy_request(
                url=request.get("url", ""),
                method=request.get("method", "GET"),
                headers=request.get("headers"),
                body=request.get("body"),
                max_amount=request.get("max_amount"),
            )

            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    finally:
        await bridge.shutdown()


def main() -> None:
    """CLI entry point for ag402-openclaw bridge."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        description="Ag402 OpenClaw bridge — x402 auto-payment proxy for OpenClaw agents",
    )
    parser.add_argument(
        "--mode",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (for mcporter, default) or http (standalone proxy)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=14022,
        help="HTTP server port (only used in http mode, default: 14022)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="HTTP server host (only used in http mode, default: 127.0.0.1)",
    )
    args = parser.parse_args()

    bridge = OpenClawBridge()

    if args.mode == "stdio":
        asyncio.run(_run_stdio_bridge(bridge))
    else:
        _run_http_bridge(bridge, host=args.host, port=args.port)


def _run_http_bridge(bridge: OpenClawBridge, host: str, port: int) -> None:
    """Run the bridge as a standalone HTTP proxy server."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
    except ImportError:
        logger.error("HTTP mode requires fastapi: pip install fastapi uvicorn")
        sys.exit(1)

    app = FastAPI(
        title="Ag402 OpenClaw Bridge",
        description="HTTP proxy with automatic x402 payment for OpenClaw agents",
    )

    @app.on_event("startup")
    async def startup() -> None:
        await bridge.ensure_initialized()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await bridge.shutdown()

    @app.post("/proxy")
    async def proxy(request: dict) -> JSONResponse:
        result = await bridge.proxy_request(
            url=request.get("url", ""),
            method=request.get("method", "GET"),
            headers=request.get("headers"),
            body=request.get("body"),
            max_amount=request.get("max_amount"),
        )
        return JSONResponse(content=result)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(content={
            "status": "healthy",
            "adapter": "ag402-openclaw",
            "initialized": bridge._initialized,
        })

    import uvicorn
    logger.info("[bridge] Starting HTTP mode on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

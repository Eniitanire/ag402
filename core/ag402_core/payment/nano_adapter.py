"""Nano (XNO) payment adapter and mock for test mode.

Nano is a native-token, feeless, instant (sub-second finality) network — there
is no USDC contract and no SPL/ERC-20 token to transfer, so the adapter is
simpler than the Solana one: a signed ``send`` state block moved over the Nano
JSON-RPC ``process`` action. A Nano seed (64 hex chars, or a raw seed) plus a
public RPC URL is all that is required.

Payment amounts are native XNO. The ``token`` argument must be ``"XNO"`` (or
``"nano"``); any other token is rejected with a clear error, because Nano's
ledger only carries its native asset.

Block construction and signing reuse ``nanopy`` (v28) — nothing here rebuilds
Nano's Blake2b/Ed25519 block logic or work (PoW) generation.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from ag402_core.payment.base import BasePaymentProvider, PaymentResult

logger = logging.getLogger(__name__)

AG402_MEMO = "Ag402-v1"

# Nano has 30 decimal places (10^30 raw per XNO).
NANO_EXP = 30

# Default public read node for lookups; a user-supplied rpc_url overrides it.
DEFAULT_RPC_URL = "https://rpc.nano.to"

# Address prefix for the Nano network.
NANO_PREFIX = "nano_"


class NanoPaymentError(Exception):
    """Raised when a Nano RPC call fails or a payment cannot complete."""


class NanoAdapter(BasePaymentProvider):
    """Native Nano (XNO) payments over the Nano JSON-RPC.

    Heavy dependency ``nanopy`` is imported lazily so the rest of the package
    works even when it is not installed.
    """

    def __init__(
        self,
        private_key: str,
        rpc_url: str = DEFAULT_RPC_URL,
        confirm_timeout: int = 30,
        network_name: str = "nano",
    ) -> None:
        # Lazy-import the heavy crypto dependency.
        try:
            from nanopy import Account, Network  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "Nano dependencies are not installed. "
                "Install them with:  pip install 'ag402-core[crypto]'"
            ) from exc

        self._Account = Account
        self._Network = Network
        self._rpc_url = rpc_url
        self._confirm_timeout = confirm_timeout

        seed = private_key
        if seed.startswith("0x"):
            seed = seed[2:]
        seed = seed.zfill(64) if len(seed) < 64 else seed
        if len(seed) != 64:
            raise ValueError(
                "Nano private key must be a 64-hex-char seed (an Ed25519 private "
                "key). Got length %d." % len(seed)
            )

        # Configure the shared network so nanopy knows the prefix and RPC host.
        Account.set_network(Network(rpc_url=rpc_url, name=network_name))

        self._account = Account(sk=seed)
        # Frontier/raw balance are loaded lazily on first send/balance so the
        # constructor never touches the network.

    def _sync_state(self) -> None:
        """Load the account's on-ledger frontier and raw balance (if any)."""
        if getattr(self, "_state_synced", False):
            return
        info = self._rpc("account_info", {"account": self._account.addr})
        # A fresh account that has never received returns "Account not found".
        if info.get("error") in (None, ""):
            self._account._frontier = info.get("frontier", "0" * 64)
            self._account._raw_bal = int(info.get("balance", "0"))
            rep = info.get("representative")
            if rep:
                self._account._rep = self._Account(addr=rep)
        else:
            self._account._frontier = "0" * 64
            self._account._raw_bal = 0
        self._state_synced = True

    # -- RPC plumbing ------------------------------------------------------

    def _rpc(self, action: str, params: dict) -> dict:
        """Issue a Nano JSON-RPC call. Returns the JSON result dict."""
        payload = {"action": action, **params}
        try:
            resp = httpx.post(self._rpc_url, json=payload, timeout=self._confirm_timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise NanoPaymentError(
                f"Nano RPC {action!r} failed: {exc}"
            ) from exc

    def _rpc_async(self, action: str, params: dict) -> dict:
        return self._rpc(action, params)

    # -- BasePaymentProvider interface --------------------------------------

    async def pay(
        self, to_address: str, amount: float, token: str = "XNO",
        *, request_id: str = "",
    ) -> PaymentResult:
        """Send native XNO via a signed Nano ``send`` state block.

        Nano has no USDC contract — only its native asset. ``token`` must be
        ``"XNO"``/``"nano"`` (case-insensitive); anything else is rejected.
        """
        if token.lower() not in ("xno", "nano"):
            return PaymentResult(
                tx_hash="", success=False, chain="nano",
                error=f"NanoAdapter only supports native XNO, got {token!r}",
            )

        from nanopy import Account  # type: ignore[import-untyped]

        try:
            destination = Account(addr=to_address)
        except Exception as exc:
            return PaymentResult(
                tx_hash="", success=False, chain="nano",
                error=f"Invalid Nano destination address: {exc}",
            )

        # Refetch live state so we send against the true frontier.
        self._sync_state()

        raw_amount = self._Network().to_raw(str(amount), NANO_EXP)
        if raw_amount <= 0:
            return PaymentResult(
                tx_hash="", success=False, chain="nano",
                error="Nano amount must be positive",
            )

        # Guard against an unconfirmed local frontier (safety check).
        if self._account.raw_bal is not None and raw_amount > self._account.raw_bal:
            return PaymentResult(
                tx_hash="", success=False, chain="nano",
                error=(
                    f"Insufficient XNO balance {self._account.bal} "
                    f"for {amount}"
                ),
            )

        try:
            block = self._account.send(destination, raw_amount)
        except ValueError as exc:
            return PaymentResult(
                tx_hash="", success=False, chain="nano", error=str(exc),
            )

        # Publish the signed block to the network.
        process = self._rpc("process", {
            "json_block": "true",
            "subtype": "send",
            "block": block.dict_,
        })
        if process.get("error"):
            return PaymentResult(
                tx_hash="", success=False, chain="nano",
                error=f"Nano process failed: {process['error']}",
            )
        tx_hash = process.get("hash", block.hash_)

        # Update our in-memory state to match the new frontier.
        self._account.frontier = block.hash_  # type: ignore[assignment]

        result = PaymentResult(
            tx_hash=tx_hash,
            success=True,
            chain="nano",
            memo=AG402_MEMO,
            request_id=request_id,
            confirmation_status="confirmed" if process.get("hash") else "sent",
        )
        return result

    async def check_balance(self) -> float:
        """Query the adapter account's spendable XNO balance (raw -> XNO)."""
        info = self._rpc("account_info", {"account": self._account.addr})
        bal_raw = info.get("balance", "0")
        try:
            return int(bal_raw) / (10 ** NANO_EXP)
        except (ValueError, TypeError):
            logger.error("[NANO] Bad balance from RPC: %r", bal_raw)
            return 0.0

    async def verify_payment(
        self,
        tx_hash: str,
        expected_amount: float = 0,
        expected_address: str = "",
        expected_sender: str = "",
    ) -> bool:
        """Verify a Nano block exists, is a send, and matches amount/recipient.

        ``expected_sender`` is verified against the block's ``account`` field
        (the sender of the block), which prevents third-party hash reuse.
        """
        info = self._rpc("block_info", {
            "json_block": "true",
            "hash": tx_hash,
        })
        if info.get("error") or "amount" not in info:
            logger.warning("[NANO] Verify: block %s not found", tx_hash[:16])
            return False

        actual_amount_raw = int(info.get("amount", "0"))
        actual_sender = info.get("account", "")
        actual_recipient = info.get("link_as_account", "")

        if expected_sender and actual_sender.lower() != expected_sender.lower():
            logger.warning(
                "[NANO] Verify: sender mismatch — expected %s, block from %s",
                expected_sender[:16], actual_sender[:16],
            )
            return False

        if expected_address and actual_recipient.lower() != expected_address.lower():
                logger.warning(
                    "[NANO] Verify: recipient mismatch — expected %s, block to %s",
                    expected_address[:16], actual_recipient[:16],
                )
                return False

        if expected_amount > 0:
            # Use Decimal to avoid float precision drift on 10^30 conversions.
            from decimal import Decimal as _Decimal
            expected_raw = int(
                (_Decimal(str(expected_amount)) * _Decimal(10) ** NANO_EXP).to_integral_value()
            )
            if actual_amount_raw < expected_raw:
                logger.warning(
                    "[NANO] Verify: amount %s < expected %s",
                    actual_amount_raw, expected_raw,
                )
                return False

        return True

    def get_address(self) -> str:
        return self._account.addr


class MockNanoAdapter(BasePaymentProvider):
    """In-memory mock that simulates Nano payments without touching any chain.

    Used when ``X402_MODE=test`` / provider ``nano-mock``.
    """

    def __init__(
        self,
        balance: float = 100.0,
        address: str = "nano_3mockmockmockmockmockmockmockmockmockmockmockmockmockmockmockmockmock",
    ) -> None:
        self._balance = balance
        self._address = address
        self._payments: list[PaymentResult] = []

    async def pay(
        self, to_address: str, amount: float, token: str = "XNO",
        *, request_id: str = "",
    ) -> PaymentResult:
        if token.lower() not in ("xno", "nano"):
            return PaymentResult(
                tx_hash="", success=False, chain="nano",
                error=f"NanoAdapter only supports native XNO, got {token!r}",
            )
        tx_hash = f"mock_nano_tx_{uuid.uuid4().hex}"
        result = PaymentResult(
            tx_hash=tx_hash, success=True, chain="nano-mock",
            memo=AG402_MEMO, request_id=request_id,
        )
        self._payments.append(result)
        self._balance -= amount
        return result

    async def check_balance(self) -> float:
        return self._balance

    async def verify_payment(
        self,
        tx_hash: str,
        expected_amount: float = 0,
        expected_address: str = "",
        expected_sender: str = "",
    ) -> bool:
        if not tx_hash or len(tx_hash) < 8:
            return False
        return (
            any(p.tx_hash == tx_hash for p in self._payments)
            or tx_hash.startswith("mock_nano_tx_")
        )

    def get_address(self) -> str:
        return self._address

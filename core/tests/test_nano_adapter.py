"""Tests for the Nano (XNO) payment adapter and its registry integration."""

from __future__ import annotations

import pytest
from ag402_core.config import RunMode, X402Config
from ag402_core.payment.base import PaymentResult
from ag402_core.payment.nano_adapter import (
    MockNanoAdapter,
    NanoAdapter,
)
from ag402_core.payment.registry import ConfigError, PaymentProviderRegistry


class FakeRPC:
    """Stub Nano RPC used to exercise NanoAdapter without touching a chain."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.frontier = "0" * 64
        self.raw_balance = 0
        self.process_result: dict = {"hash": "A" * 64}

    def respond(self, action: str, params: dict) -> dict:
        self.calls.append((action, params))
        if action == "account_info":
            if self.raw_balance == 0 and self.frontier == "0" * 64:
                return {"error": "Account not found", "balance": "0"}
            return {
                "frontier": self.frontier,
                "balance": str(self.raw_balance),
                "representative": "nano_1111111111111111111111111111111111111111111111111111hifc8npp",
            }
        if action == "process":
            return self.process_result
        if action == "block_info":
            # 1 XNO in raw (10^30) — exact Decimal string to avoid float drift
            return {
                "amount": "1000000000000000000000000000000",
                "account": "nano_3mockmockmockmockmockmockmockmockmockmockmockmockmockmockmockmockmock",
                "link_as_account": "nano_1ninja7rh37ewr9c9j5n7a6b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5",
            }
        return {}


def _adapter_with_rpc(fake: FakeRPC, raw_balance: int = 10**30) -> NanoAdapter:
    adapter = NanoAdapter(
        private_key="0" * 64,
        rpc_url="https://rpc.nano.to",
    )
    fake.raw_balance = raw_balance
    fake.frontier = "B" * 64
    adapter._rpc = fake.respond  # type: ignore[assignment]
    return adapter


class TestMockNanoAdapter:
    @pytest.mark.asyncio
    async def test_pay_returns_success(self) -> None:
        m = MockNanoAdapter(balance=10.0)
        result = await m.pay("nano_1abc", 0.5)
        assert result.success is True
        assert result.tx_hash.startswith("mock_nano_tx_")
        assert result.chain == "nano-mock"

    @pytest.mark.asyncio
    async def test_balance_decrements(self) -> None:
        m = MockNanoAdapter(balance=10.0)
        await m.pay("nano_1abc", 2.0)
        assert await m.check_balance() == pytest.approx(8.0)

    @pytest.mark.asyncio
    async def test_rejects_non_xno(self) -> None:
        m = MockNanoAdapter()
        result = await m.pay("nano_1abc", 1.0, token="USDC")
        assert result.success is False
        assert "XNO" in result.error

    @pytest.mark.asyncio
    async def test_verify_known_tx(self) -> None:
        m = MockNanoAdapter()
        m._payments.append(
            PaymentResult(tx_hash="mock_nano_tx_12345678", success=True, chain="nano-mock")
        )
        assert await m.verify_payment("mock_nano_tx_12345678") is True
        assert await m.verify_payment("short") is False

    def test_get_address(self) -> None:
        m = MockNanoAdapter()
        assert m.get_address().startswith("nano_")


class TestNanoAdapterLogic:
    def test_adapter_exposes_abstract_interface(self) -> None:
        fake = FakeRPC()
        adapter = _adapter_with_rpc(fake)
        assert callable(adapter.pay)
        assert callable(adapter.check_balance)
        assert callable(adapter.verify_payment)
        assert callable(adapter.get_address)
        assert adapter.get_address().startswith("nano_")

    @pytest.mark.asyncio
    async def test_pay_rejects_non_native_token(self) -> None:
        fake = FakeRPC()
        adapter = _adapter_with_rpc(fake)
        result = await adapter.pay("nano_1abc", 1.0, token="USDC")
        assert result.success is False
        assert "XNO" in result.error

    @pytest.mark.asyncio
    async def test_check_balance_reads_raw(self) -> None:
        fake = FakeRPC()
        adapter = _adapter_with_rpc(fake, raw_balance=5 * 10**30)
        bal = await adapter.check_balance()
        assert bal == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_verify_payment_checks_fields(self) -> None:
        fake = FakeRPC()
        adapter = _adapter_with_rpc(fake)
        # FakeRPC block_info returns sender mock + expected link; amount 1 XNO
        # (10^30 raw, exact Decimal string).
        assert await adapter.verify_payment("A" * 64) is True
        assert await adapter.verify_payment(
            "A" * 64,
            expected_amount=1.0,
            expected_sender="nano_3mockmockmockmockmockmockmockmockmockmockmockmockmockmockmockmockmock",
            expected_address="nano_1ninja7rh37ewr9c9j5n7a6b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5",
        ) is True

    @pytest.mark.asyncio
    async def test_verify_payment_rejects_sender_mismatch(self) -> None:
        fake = FakeRPC()
        adapter = _adapter_with_rpc(fake)
        assert (
            await adapter.verify_payment(
                "A" * 64, expected_sender="nano_1different"
            )
            is False
        )


class TestNanoRegistry:
    def test_explicit_nano_mock(self) -> None:
        provider = PaymentProviderRegistry.get_provider("nano-mock")
        assert isinstance(provider, MockNanoAdapter)

    def test_auto_detect_nano_key(self) -> None:
        config = X402Config(mode=RunMode.PRODUCTION, nano_private_key="0" * 64)
        provider = PaymentProviderRegistry.get_provider("auto", config=config)
        assert isinstance(provider, NanoAdapter)

    def test_explicit_nano_without_key_raises(self) -> None:
        config = X402Config(mode=RunMode.PRODUCTION, nano_private_key="")
        with pytest.raises(ConfigError):
            PaymentProviderRegistry.get_provider("nano", config=config)

    def test_nano_provider_has_required_methods(self) -> None:
        provider = PaymentProviderRegistry.get_provider("nano-mock")
        assert hasattr(provider, "pay")
        assert hasattr(provider, "check_balance")
        assert hasattr(provider, "verify_payment")
        assert hasattr(provider, "get_address")

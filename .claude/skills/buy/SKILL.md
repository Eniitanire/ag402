---
name: buy
description: Use when a user wants to buy from an API, pay for an API call, connect to a paid x402 API, set up an AI agent to auto-pay, integrate ag402 into Claude Code or Cursor, or use the x402 payment protocol as a buyer
---

# Buy — Connect an AI Agent to Paid x402 APIs

## Overview

This skill sets up the buyer side of the x402 payment protocol. It configures an AI agent (or any HTTP client) to automatically detect `402 Payment Required` responses, pay on-chain in USDC on Solana, and retry the request with proof of payment — all transparently.

**Result:** The user's AI agent or script can call any x402-gated API and auto-pay.

## When to Use

- User says "buy", "pay for API", "auto-pay", "connect to paid API", or "use x402"
- User wants to integrate ag402 into Claude Code, Cursor, or another AI tool
- User wants their agent to autonomously pay for API calls
- User wants to call an `ag402 serve` gateway from the buyer side

## Step 1: Install (Silent)

Check that `ag402` is installed. Only speak if something is missing.

```bash
ag402 --version
```

If this fails:

```bash
pip install ag402-core
```

For AI tool integration (MCP), also install:

```bash
pip install ag402-client-mcp
```

## Step 2: Wallet Setup

**If the user is present and can interact with the terminal**, ask them to choose:

- **A) Quick start — test mode (recommended)** → no wallet needed, 100 USDC test funds deposited automatically
- **B) I have a Solana wallet and want production mode** → will need private key + `ag402 upgrade`

**For option A** (vast majority of users), run:

```bash
ag402 setup
```

`ag402 setup` is an **interactive wizard** with prompts (password input, confirmations). Let the user run it directly — do not try to automate or pipe input to it.

**If you are operating autonomously** (no human in the loop), use `ag402 init` instead:

```bash
ag402 init
```

`ag402 init` is **non-interactive** — it creates a test wallet and deposits $100 USDC with zero prompts. This is the correct command for AI agents acting autonomously.

After either command, verify:

```bash
ag402 balance
```

Expected: shows `$100.00` test balance.

**For option B**, start with option A first (test mode), verify everything works, then upgrade:

```bash
ag402 upgrade
```

`ag402 upgrade` is also interactive (private key input, password, daily limit). Let the user run it directly.

## Step 3: Choose Integration Mode

Ask the user how they want to use ag402:

- **A) One-off API call** → use `ag402 pay` (simplest, test a single endpoint)
- **B) Inside my AI tool (Claude Code / Cursor)** → use `ag402 install` (MCP integration)
- **C) In my Python script** → use `ag402 run` or the SDK
- **D) Not sure / just exploring** → start with A, upgrade later

## Step 4A: One-Off API Call

The simplest way to test. Point `ag402 pay` at any x402 gateway:

```bash
ag402 pay <gateway_url>
```

Example:

```bash
ag402 pay http://127.0.0.1:4020/weather?city=Tokyo
```

**What happens** (the CLI shows every step):
1. Sends request → gets `402 Payment Required`
2. Parses the payment challenge (chain, token, amount, payee)
3. Deducts from wallet + pays on-chain (simulated in test mode)
4. Retries with payment proof → gets `200 OK` + data
5. Shows balance before/after

If the user doesn't have a gateway to test against, they can start one locally first:

```bash
ag402 serve &
sleep 3
ag402 pay http://127.0.0.1:4020/
```

## Step 4B: AI Tool Integration (MCP)

For Claude Code, Cursor, or OpenClaw — ag402 provides an MCP server that gives the AI tool a `fetch_with_autopay` tool.

**Ask the user which tool:**

- **A) Claude Code** → `ag402 install claude-code`
- **B) Cursor** → `ag402 install cursor`
- **C) OpenClaw** → `ag402 install openclaw`
- **D) Claude Desktop** → `ag402 install claude-desktop`

Run the install command:

```bash
ag402 install <tool>
```

After install, tell the user:
1. Restart the AI tool (or reload MCP config)
2. The `fetch_with_autopay` tool will appear in the AI tool
3. Ask the AI to call a paid API — ag402 handles the payment automatically

To verify the MCP server works:

```bash
ag402 mcp --sse --port 14021
```

This starts the MCP server on SSE transport. If it starts without errors, the MCP integration is working. Stop it with Ctrl+C — the AI tool will manage the server lifecycle from now on.

## Step 4C: Python Script Integration

For users who want auto-pay in their own Python code.

**Option 1: Wrap with `ag402 run`** (zero code changes):

```bash
ag402 run -- python my_agent.py
```

This injects `ag402_core.enable()` via `sitecustomize.py`, so all `urllib`/`httpx`/`requests` calls that receive 402 will be auto-paid. Works for any Python script.

**Option 2: SDK in code** (explicit):

```python
import ag402_core
ag402_core.enable()

# Now any HTTP request that gets 402 will be auto-paid
import httpx
response = httpx.get("http://gateway:4020/data")
# response is 200 — payment happened transparently
```

## Step 5: Verify

After any integration mode, confirm the system works.

### Check 1: Wallet is funded

```bash
ag402 balance
```

Expected: shows a positive balance (e.g., `$100.00` in test mode).

### Check 2: Payment flow works

```bash
ag402 pay <gateway_url>
```

Expected: shows the full 402 → pay → 200 flow with no errors.

### Check 3: Transaction recorded

```bash
ag402 history
```

Expected: shows the transaction just made, with amount, target, and status.

If all three pass, tell the user: "Your agent is ready to pay for API calls!"

## Step 6: Next Steps

Ask the user:

- **A) Done for now** → remind them of useful commands: `ag402 balance`, `ag402 history`, `ag402 config`
- **B) Set safety limits** → show the configurable limits:
  ```bash
  ag402 env set X402_DAILY_LIMIT 10       # max $10/day (default)
  ag402 env set X402_PER_MINUTE_LIMIT 2   # max $2/minute
  ag402 env set X402_PER_MINUTE_COUNT 5   # max 5 tx/minute
  ```
- **C) Switch to production** → run `ag402 upgrade` (interactive)
- **D) Run full health check** → run `ag402 doctor`

## Common Errors and Recovery

| Error | Cause | Fix |
|-------|-------|-----|
| `ag402: command not found` | Not installed | `pip install ag402-core` |
| `ag402-client-mcp not installed` | Missing MCP package | `pip install ag402-client-mcp` |
| `Insufficient balance` | Wallet empty | `ag402 setup` to get test funds |
| `Cannot connect to <url>` | Gateway not running | Check the gateway URL is correct and reachable |
| `Non-standard 402 response` | Server returns 402 but not x402 | Not an x402 API — ag402 can only auto-pay x402-compatible gateways |
| `On-chain payment failed` | RPC / network issue | Check internet; for localnet: `solana-test-validator --reset` |
| `Request timed out` | Gateway or RPC slow | Retry; check `ag402 doctor` for RPC connectivity |
| MCP tool not appearing in AI tool | Config not written or tool not restarted | Re-run `ag402 install <tool>` and restart the AI tool |

## Red Flags — STOP and Recheck

- User wants production mode but hasn't tested in test mode first — recommend testing first
- User sets daily limit above $100 — confirm this is intentional: "Are you sure? $100/day is a high limit for autonomous spending."
- User pastes a private key anywhere outside `ag402 upgrade` or `ag402 setup` — STOP, explain these are the only safe places for key input
- User's balance is dropping unexpectedly — run `ag402 history` to audit transactions

## Quick Reference

Fastest path — AI agent autonomous (no human needed):

```bash
pip install ag402-core
ag402 init                                    # Non-interactive wallet + $100 test funds
ag402 pay http://127.0.0.1:4020/              # Pay for an API call
ag402 balance                                 # Check balance
```

Fastest path — human-guided test mode:

```bash
pip install ag402-core
ag402 setup                                   # Interactive wizard
ag402 pay http://127.0.0.1:4020/              # Pay for an API call
ag402 balance && ag402 history                 # Check balance + history
```

Fastest path — Claude Code MCP integration:

```bash
# Install
pip install ag402-core ag402-client-mcp

# Setup wallet
ag402 setup

# Install MCP into Claude Code
ag402 install claude-code

# Restart Claude Code — done. Ask Claude to call any x402 API.
```

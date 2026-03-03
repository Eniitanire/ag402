---
name: sell
description: Use when a user wants to sell an API, monetize an endpoint, set up a paid API, become an x402 provider, add payment gating to their HTTP service, or deploy an ag402 gateway in front of their backend
---

# Sell — Turn Any API into a Paid x402 API

## Overview

This skill converts an existing HTTP API into a paid API using the x402 payment protocol on Solana (USDC). It configures ag402 as a reverse proxy that returns `402 Payment Required` to unauthenticated requests, verifies on-chain USDC payments, and forwards paid requests to the backend.

**Result:** A gateway URL that any x402-compatible buyer (AI agent, CLI, SDK) can call and pay per-request.

## When to Use

- User says "sell", "monetize", "paywall", "charge for", "paid API", or "payment gateway"
- User wants to put an API behind x402
- User wants to deploy ag402 in provider/seller mode
- User has a running HTTP service and wants to gate it with USDC payments

## Step 1: Prerequisites Check (Silent)

Check that `ag402` is installed. Run silently — only speak if something is missing.

```bash
ag402 --version
```

If this fails, install it:

```bash
pip install ag402-core ag402-mcp
```

Verify again after install. If it still fails, STOP and tell the user.

## Step 2: Gather Information

**Treat the user as a beginner who prefers choosing over typing.** Present choices, not open-ended questions. Use the defaults aggressively — only ask when truly needed.

### Question 1: Backend API

Ask the user to choose:

- **A) I have a running API** → ask for the URL (provide `http://localhost:8000` as placeholder)
- **B) I don't have an API yet / just want to try it** → use `http://localhost:8000` (ag402 will auto-start a built-in demo backend)

Most users pick B. Default to B if the user is unsure.

### Question 2: Price per call

Present choices (1 USDC ≈ $1):

- **A) $0.001** — micro-task (e.g., a single lookup, translation)
- **B) $0.01** — light task (e.g., search query, short text)
- **C) $0.05** — medium task (e.g., image analysis, long generation)
- **D) Custom** — let the user type a number

Default: B ($0.01) if the user doesn't pick.

### Question 3: Wallet address

Ask the user to choose:

- **A) I don't have a wallet / just testing** → use `DemoRecipientWa11et11111111111111111111` + test mode. Tell the user: "No real money involved. You can switch to production later."
- **B) I have a Solana wallet address** → ask them to paste it (must be ~32-44 character base58 string)

Default: A (test mode). Most new users should start here.

**SAFETY CHECK:** If the user pastes a string that looks like a **private key** (significantly longer than 44 chars, or they say "private key"), STOP immediately. Say: "That looks like a private key — never share it. I need your **public** wallet address (the one you give people to send you money)."

### Question 4: Deployment

- **A) Local (recommended)** — run on this machine, test right now
- **B) Docker** — run in containers
- **C) Remote server** — deploy via SSH

Default: A. Recommend A for first-time users.

## Step 3: Configure

Set configuration values using `ag402 env set` (writes to `~/.ag402/.env` with safe quoting and 0600 permissions).

```bash
ag402 env set AG402_TARGET_API <backend_url>
ag402 env set AG402_API_PRICE <price>
ag402 env set AG402_RECEIVE_ADDRESS <wallet_address>
```

If the user chose test mode (Question 3 = A):

```bash
ag402 env set AG402_RECEIVE_ADDRESS DemoRecipientWa11et11111111111111111111
ag402 env set X402_MODE test
```

Verify the config was written:

```bash
ag402 env show
```

Confirm the output shows the correct values for `AG402_TARGET_API`, `AG402_API_PRICE`, and `AG402_RECEIVE_ADDRESS`.

## Step 4A: Deploy — Local (Default)

**CRITICAL: `ag402 serve` is a foreground blocking process.** You must run it in the background so you can continue to the verification step.

Start the gateway in background:

```bash
ag402 serve --target <backend_url> --price <price> --address <wallet_address> --port 4020 &
```

Wait for the server to be ready (typically 2-3 seconds):

```bash
sleep 3
```

Then immediately verify it started by checking the port:

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4020/health
```

If this returns `200`, the gateway is up. If it returns `000` or fails, wait another 2 seconds and retry once. If it still fails, check the background process output for errors.

**What happens:**
- If the backend URL is not reachable, ag402 auto-starts a built-in demo API at that port
- Gateway listens on `http://0.0.0.0:4020` by default
- All requests get a `402 Payment Required` response until valid payment is provided

Proceed directly to Step 5 — do NOT ask the user to "open another terminal".

## Step 4B: Deploy — Docker

Generate a `docker-compose.yml` tailored to the user's configuration.

**Ask the user:** "Is your backend API also running in Docker?"

- **A) Yes, it's in Docker** → include both services, use Docker service name for networking
- **B) No, it's external / on the host** → only the gateway service, use `host.docker.internal` to reach host APIs
- **C) I picked 'demo' / no backend** → only the gateway service, it has a built-in demo

Template for option A (backend in Docker):

```yaml
services:
  backend:
    image: <user_backend_image>
    ports:
      - "<backend_port>:<backend_port>"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:<backend_port>/"]
      interval: 5s
      retries: 3

  x402-gateway:
    build:
      context: .
      dockerfile_inline: |
        FROM python:3.11-slim
        RUN pip install --no-cache-dir ag402-core ag402-mcp
        ENTRYPOINT ["ag402-gateway"]
    command: >
      --target http://backend:<backend_port>
      --price <price>
      --address <wallet_address>
      --host 0.0.0.0
      --port 4020
    ports:
      - "4020:4020"
    environment:
      - X402_MODE=test
    depends_on:
      backend:
        condition: service_healthy
```

Template for option B (external backend) or C (demo):

```yaml
services:
  x402-gateway:
    build:
      context: .
      dockerfile_inline: |
        FROM python:3.11-slim
        RUN pip install --no-cache-dir ag402-core ag402-mcp
        ENTRYPOINT ["ag402-gateway"]
    command: >
      --target <backend_url_or_http://localhost:8000>
      --price <price>
      --address <wallet_address>
      --host 0.0.0.0
      --port 4020
    ports:
      - "4020:4020"
    environment:
      - X402_MODE=test
```

For option B, replace `localhost` in `--target` with `host.docker.internal`.

```bash
docker compose up -d
docker compose ps
```

Wait for the gateway container to be healthy, then proceed to Step 5.

## Step 4C: Deploy — Remote SSH

For deploying to a remote server via SSH. Ask the user for `<user>@<host>`.

1. Install ag402 on the remote machine:

```bash
ssh <user>@<host> "pip install ag402-core ag402-mcp && ag402 --version"
```

2. Set remote configuration:

```bash
ssh <user>@<host> "ag402 env set AG402_TARGET_API <backend_url> && ag402 env set AG402_API_PRICE <price> && ag402 env set AG402_RECEIVE_ADDRESS <wallet_address>"
```

3. Start the gateway with a systemd service for persistence:

Generate this file and copy it to the remote:

```ini
[Unit]
Description=Ag402 x402 Payment Gateway
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ag402 serve --port 4020
Restart=on-failure
RestartSec=5
Environment=X402_MODE=test

[Install]
WantedBy=multi-user.target
```

```bash
scp ag402-gateway.service <user>@<host>:/tmp/
ssh <user>@<host> "sudo mv /tmp/ag402-gateway.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now ag402-gateway"
```

Verify:

```bash
ssh <user>@<host> "sudo systemctl status ag402-gateway && curl -s http://127.0.0.1:4020/health"
```

If systemd is not available (e.g., container environment), fall back to nohup:

```bash
ssh <user>@<host> "nohup ag402 serve --port 4020 > /tmp/ag402.log 2>&1 &"
```

## Step 5: Verify

Run these checks. **All three must pass.** Since the gateway is already running (from Step 4), run these directly.

### Check 1: Gateway returns 402

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4020/
```

Expected: `402`. If `000` or connection refused → gateway not running, re-check Step 4.

### Check 2: Full payment flow

```bash
ag402 pay http://127.0.0.1:4020/
```

Discovers price → creates payment → gets response. In test mode, payment is simulated. Expected: JSON response with HTTP 200.

### Check 3: Health endpoint

```bash
curl -s http://127.0.0.1:4020/health
```

Expected: JSON with `"status": "healthy"` showing mode, target URL, and metrics.

If all three pass, tell the user: "Your API is live and accepting payments!"

## Step 6: Next Steps

After verification passes, present the user's gateway info and ask what they want to do next:

**Gateway info:**
- **URL:** `http://<host>:4020`
- **Price:** `$<price> USDC per call`
- **Mode:** test (no real money)

**Ask the user:**

- **A) I'm done for now** → show them the buyer command: `ag402 pay http://<host>:4020/endpoint`, remind them `127.0.0.1` is local-only and explain how to share externally
- **B) Switch to production (real payments)** → run `ag402 upgrade` (this is an interactive command that handles private key encryption, RPC URL, and daily limits). Note: `ag402 upgrade` uses interactive prompts (password input, confirmations) — let the user run it directly, do not try to automate the interactive prompts. **AI agents cannot run this autonomously — it requires human input for private key and password.**
- **C) Run the health check suite** → run `ag402 doctor` to check the full environment

For AI agent buyers, mention they can connect via `ag402 mcp` or the Python SDK.

## Common Errors and Recovery

| Error | Cause | Fix |
|-------|-------|-----|
| `ag402: command not found` | Not installed | `pip install ag402-core ag402-mcp` |
| `Missing dependency: ag402-mcp` | Partial install | `pip install ag402-mcp` |
| `No backend API URL specified` | Missing `--target` and no .env | `ag402 env set AG402_TARGET_API <url>` |
| Gateway returns `502` | Backend unreachable | Check backend is running; in Docker use service name not `localhost` |
| Gateway returns `403` | Payment verification failed | Check wallet address; ensure `X402_MODE=test` for testing |
| `Address already in use` on port 4020 | Port conflict | Use `--port <other>` or kill existing: `lsof -ti:4020 \| xargs kill` |
| `curl: (7) Failed to connect` | Gateway not running | Re-run `ag402 serve &`; for Docker check `docker compose ps` |
| Docker: backend unreachable | Docker networking | Use service name (not `localhost`) or `host.docker.internal` |
| `ag402 serve` hangs / no output | Foreground process | You ran it without `&`. Stop it (Ctrl+C) and re-run with `&` |

## Red Flags — STOP and Recheck

- User pastes what looks like a **private key** instead of a public address — STOP, explain the difference
- `localhost` or `127.0.0.1` used as `--target` inside Docker — STOP, explain Docker networking
- User wants production mode but is using `DemoRecipientWa11et...` — STOP, run `ag402 upgrade` first
- User wants to expose gateway to the internet but is binding to `127.0.0.1` — use `0.0.0.0` or explain
- Price is set to `0` — ask: "Did you mean free? Verification still runs but no payment is collected."

## Quick Reference

Minimal happy path — local test mode, no wallet needed:

```bash
# Install
pip install ag402-core ag402-mcp

# Configure
ag402 env set AG402_TARGET_API http://localhost:8000
ag402 env set AG402_API_PRICE 0.01
ag402 env set AG402_RECEIVE_ADDRESS DemoRecipientWa11et11111111111111111111
ag402 env set X402_MODE test

# Start gateway in background (auto-starts demo backend if needed)
ag402 serve &
sleep 3

# Verify
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4020/  # → 402
ag402 pay http://127.0.0.1:4020/                                 # → 200 + JSON
curl -s http://127.0.0.1:4020/health                             # → healthy

# When done testing, switch to production:
ag402 upgrade
```

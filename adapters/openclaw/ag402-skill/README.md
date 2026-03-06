# ag402 OpenClaw Skill

Integrates ag402 AI Agent Payment Protocol with OpenClaw.

## Features

### Core Functions
- **setup**: Initialize wallet and configuration
- **wallet status**: Check balance and budget
- **wallet deposit**: Add test USDC
- **wallet history**: View transaction history
- **pay <url>**: Make payment to API endpoint
- **gateway start/stop**: Control payment gateway
- **doctor**: Health check and diagnostics

### Security Features

| Feature | Description |
|---------|-------------|
| SSRF Protection | Blocks localhost, private IPs, dangerous ports |
| Race Condition Fix | File locking for atomic balance operations |
| API Key Auth | Support for AG402_API_KEY environment variable |
| Header Filtering | Blocks dangerous headers (authorization, cookie, x-api-key) |
| Method Whitelist | Only safe HTTP methods allowed |
| Budget Limits | $50 single / $20 min / $100 daily |
| Payment Confirm | $10 threshold for user confirmation |

## Quick Start

### Installation

```bash
# Automated install
./scripts/install-auto.sh

# Interactive wizard
./scripts/install-wizard.sh

# Verify installation
./scripts/verify-install.sh
```

### Usage

```bash
# Initialize
setup

# Check balance
wallet status

# Make payment
pay https://api.example.com/data

# View history
wallet history

# Health check
doctor
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| AG402_API_KEY | API key for authentication | (none) |
| AG402_DAILY_LIMIT | Daily budget limit | 100.0 |
| AG402_SINGLE_TX_LIMIT | Single transaction limit | 50.0 |
| AG402_PER_MINUTE_LIMIT | Per-minute limit | 20.0 |

## Security

- Wallet file permissions: 600 (chmod required)
- All payments require confirmation for amounts >= $10
- Built-in budget limits prevent overspending
- Audit logging for all transactions

## Version

v0.1.12 - 2026-03-06

---

## Prepaid System (v0.1.12+)

### Overview

The prepaid system allows AI agents to purchase bundled API calls at discounted rates, reducing gas costs by 99.9%.

### Package Tiers

| Package | Days | Calls | Price (USDC) |
|---------|------|-------|--------------|
| p3d_100 | 3 | 100 | 1.5 |
| p7d_500 | 7 | 500 | 5.0 |
| p30d_1000 | 30 | 1000 | 8.0 |
| p365d_5000 | 365 | 5000 | 35.0 |
| p730d_10000 | 730 | 10000 | 60.0 |

### How It Works

1. **Purchase**: Buyer purchases a prepaid package via `ag402 prepaid buy <package_id>`
2. **Storage**: Credential is stored locally in `~/.ag402/prepaid_credentials.json`
3. **API Call**: When making API calls, prepaid credentials are checked first
4. **Verification**: Seller verifies the HMAC-signed credential
5. **Fallback**: If no prepaid available, falls back to standard 402 payment

### Commands

```bash
# Check prepaid balance
ag402 prepaid status

# List available packages  
ag402 prepaid list

# Purchase a package (for testing)
ag402 prepaid buy p30d_1000
```

### Security

- HMAC-SHA256 signature verification
- Constant-time comparison prevents timing attacks
- Credential expiry validation
- Seller address verification

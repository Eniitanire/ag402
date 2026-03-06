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

### Security Features (v0.1.12)

| Feature | Status | Description |
|---------|--------|-------------|
| SSRF Protection | ✅ | Blocks HTTP, localhost, private IPs, IPv6, DNS rebinding, decimal/hex IPs |
| Race Condition Fix | ✅ | File locking (fcntl.flock) for atomic balance operations |
| API Key Auth | ✅ | Protects sensitive commands (pay, deposit, gateway) |
| Header Whitelist | ✅ | Only allows safe headers, blocks dangerous ones |
| Input Validation | ✅ | Validates amount (negative, non-number, max limit) |
| Budget Limits | ✅ | $50 single / $20 min / $100 daily |

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

# Make payment (requires HTTPS)
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

### SSRF Protection
The `pay` command includes comprehensive SSRF protection:
- ✅ Blocks `http://` (requires HTTPS)
- ✅ Blocks localhost (127.0.0.1, ::1)
- ✅ Blocks private IPs (10.x, 172.16-31.x, 192.168.x)
- ✅ Blocks IPv6 variants ([::ffff:127.0.0.1])
- ✅ Blocks decimal IPs (2130706433 = 127.0.0.1)
- ✅ Blocks hex IPs (0x7F000001)
- ✅ DNS rebinding protection

### Authentication
- Sensitive commands require AG402_API_KEY:
  - `wallet deposit` - requires auth
  - `gateway start/stop` - requires auth
  - `pay` - requires auth (if amount >= threshold)
- Read-only commands are public:
  - `wallet status` - public
  - `wallet history` - public
  - `doctor` - public

### Input Validation
- Amount must be positive (> 0)
- Amount must be a valid number
- Amount cannot exceed 1,000,000

### File Security
- Wallet file permissions: 600
- Transaction logs protected
- API keys never logged

## Version

**v0.1.12** - 2026-03-06
- Security fixes: SSRF, auth, race condition, input validation, header whitelist

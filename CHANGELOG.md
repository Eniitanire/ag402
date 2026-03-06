# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.12] - 2026-03-06

### Security (ag402-skill)

This release includes comprehensive security fixes identified through deep code audit:

- **SSRF Protection**: Added comprehensive SSRF protection to `pay` command
  - Blocks HTTP protocol (requires HTTPS)
  - Blocks localhost and private IPs
  - Blocks IPv6 variants
  - Blocks decimal/hex IP formats
  - DNS rebinding protection

- **Authentication**: Added API key authentication
  - Protected commands require AG402_API_KEY
  - Protected: wallet deposit, gateway start/stop
  - Public: wallet status, wallet history, doctor

- **Race Condition Fix**: Added file locking (fcntl.flock)
  - Atomic balance operations
  - Prevents TOCTOU vulnerabilities

- **Input Validation**: Added comprehensive input validation
  - Negative amount rejection
  - Non-number input handling
  - Maximum amount limit (1,000,000)

- **Header Filtering**: Added header whitelist
  - Blocks dangerous headers (Authorization, Cookie, X-Api-Key)
  - Blocks IP spoofing headers (X-Forwarded-For, Host)

### Added

- **Prepaid System**: New prepaid payment mechanism for AI Agent API calls
  - `prepaid_models.py`: Data models for packages, credentials, usage logs
  - `prepaid_client.py`: Buyer-side budget pool management
  - `prepaid_server.py`: Seller-side verification with HMAC signature
  - 5 package tiers: 3/7/30/365/730 days with bundled calls
  - HMAC-SHA256 signature verification
  - Automatic fallback to standard 402 when prepaid exhausted

## [0.1.11] - 2026-03-05

### Security

- **Seller-No-Key documentation hardening**: Comprehensive audit ensuring sellers are never misled into providing a private key
- `.env.example`: Removed seller private key field; `SOLANA_PRIVATE_KEY` marked `⚠️ BUYER ONLY` with role-specific comments
- `.env.example`: Added bottom-of-file seller security notice
- `SECURITY.md`: Added **Seller-No-Key Architecture** to Security Design section
- `setup_wizard.py`: Added security reminder box and private-key-paste detection for seller role
- `cli.py`: `ag402 serve` now prints seller security reminder on startup
- `llms.txt`: Enhanced Sell Skill and added Red Flags section for LLM agents

# osiris-mobile-termux v0.5.0-edge-beta — Release Notes (2026-10-31)

A major architecture and security release ratifying the **OSIRIS Google Pixel Fold Android Specification (`OSIRIS-ANDROID-SPEC-001`)**, implementing the **Smart Keyboard IntentPreviewFirewall**, **Bluetooth SCO voice service**, and **SYS-021 Loopback Bridge**.

---

## 1. Google Pixel Fold Android Specification (`OSIRIS-ANDROID-SPEC-001.md`)
- Formalizes 46 architectural, security, and verification criteria aligned with the Pete Gordon live demo model.
- Ratifies governance amendments covering:
  - **SYS-021**: Cryptographic token-authenticated bridge enforcement.
  - **SYS-024**: Dynamic constant retraction (dropping historical constants from live previews).
  - **SYS-025**: IntentPreviewFirewall schema block with gated, auto-expiring Auto Advance.
- Binds hardware evidence to the `EXP-OLMO3` dual-substrate benchmark.

## 2. Node Alpha Smart Keyboard & Firewall Layer (`android/`)
- **IntentPreviewFirewall**: Intercepts input method events, enforcing pre-dispatch AST validation and blocking disallowed intent generation on constrained hardware.
- **Signed Loopback Bridge**: Implements tokenized local loopback IPC between the Android IME service, Termux background daemons, and desktop Node Beta workstations.
- **Voice & Bluetooth SCO Integration**: Low-latency, hands-free sovereign interaction via Bluetooth SCO profiles with noise gating and temporal lockouts.

## 3. Governance, Epistemics & Citations
- Incorporates the IBM Community Quantum Ultimatum citation into the specification and repository README.
- Integrates Gate 0 Invariant Rules (`GEMINI.md`) for clean synchronization and ANSI text sanitization.

---

## 4. Lineage & Identifiers
- **Software Repository**: [https://github.com/osiris-dnalang/osiris-mobile-termux](https://github.com/osiris-dnalang/osiris-mobile-termux)
- **Predecessor Tag**: `v0.4.0-edge-beta` (2026-09-22)
- **Primary Governance Specification**: `OSIRIS-ANDROID-SPEC-001.md`

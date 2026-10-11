# OSIRIS Google Pixel Fold Android Platform
## Implementation Specification and Acceptance-Test Plan

**Document ID:** `OSIRIS-ANDROID-SPEC-001`  
**Version:** `1.0-draft`  
**Date:** `2026-10-11`  
**Status:** `PROPOSED_SPECIFICATION` — *not implemented or verified*  
**Implementation Status:** `NOT_IMPLEMENTED`  
**Evidence Status:** `NOT_TESTED`  
**Deployment Authority:** `NONE`  
**Claim Ceiling:** Design proposal only; no operational or scientific efficacy claimed  
**Target:** Google Pixel Fold (`Node Alpha: Mobile Edge / ARM64`), Android  
**Execution Model:** Hybrid local-first, cloud-optional  
**Interaction Priority:** Balanced typing, voice composition, and developer tools  

---

## 1. Purpose

This document defines the normative architecture, implementation sequence, security and governance invariants, typed interface contracts, DevOps integration, and measurable acceptance-test criteria for an integrated OSIRIS platform on Android, specifically targeting the **Google Pixel Fold** (`Node Alpha`).

The first release deliverable encompasses:
1. **Adaptive Android Application**: Native Jetpack Compose interface adapting seamlessly between folded (compact cover screen) and unfolded (dual-pane inner workspace) postures.
2. **OSIRIS Smart Keyboard**: Dedicated `InputMethodService` providing conventional typing, code/DNA-Lang developer helpers, explicit voice composition, and structured intent preview.
3. **Typed Android SDK & Runtime Bridge**: Versioned request/response contracts, serialization, validation, and an explicit IPC/API bridge isolating the Android app sandbox from local execution (e.g., Termux/PRoot) and authenticated remote services.
4. **Hybrid Execution Adapters**: Isolated local-first developer execution with optional authenticated cloud job dispatch.
5. **Governance & Evidence Engine**: Non-bypassable capability authorization, dynamic evidence ledger logging, and auditable CI/CD promotion controls.

> [!IMPORTANT]
> This document is an architectural and engineering specification. It establishes normative requirements and acceptance criteria. It does not assert that the described modules, tests, integrations, or performance targets have already been implemented or verified.

---

## 2. Normative Language & Governance Status Vocabulary

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in BCP 14 (RFC 2119, RFC 8174).

Every implementation record, test report, artifact receipt, and promotion manifest MUST explicitly distinguish the following four orthogonal state fields:

| Field | Permitted Values | Definition |
| :--- | :--- | :--- |
| `implementation_status` | `NOT_IMPLEMENTED`<br>`IN_PROGRESS`<br>`IMPLEMENTED`<br>`BLOCKED` | Engineering readiness of the code module or interface. |
| `evidence_status` | `NOT_TESTED`<br>`TESTED_PASS`<br>`TESTED_FAIL`<br>`INCONCLUSIVE` | Empirical outcome of automated verification and acceptance tests. |
| `deployment_authority` | `NONE`<br>`REQUIRES_APPROVAL`<br>`AUTHORIZED`<br>`REVOKED` | Human-governed administrative approval to release or deploy. |
| `claim_ceiling` | *Text statement* | The strongest factual claim supported by available evidence. |

> [!WARNING]
> A passing unit test establishes solely the behavior that the test asserts under its specific execution harness. It **MUST NOT** be construed as demonstrating scientific efficacy, system stability, production readiness, or authorization to deploy.

---

## 3. Core Principles & Goals

### 3.1 Architectural Axiom
The platform strictly enforces the OSIRIS governance axiom:
$$\text{Cognition Proposes} \longrightarrow \text{DNA-Lang Constrains} \longrightarrow \text{OSIRIS Executes} \longrightarrow \text{Evaluators Measure} \longrightarrow \text{Evidence Records} \longrightarrow \text{Authority Promotes}$$

The Google Pixel Fold functions as an ergonomic mobile interaction and engineering surface—**never as an unrestricted ambient execution agent**.

```mermaid
flowchart LR
    subgraph InputSurface["Input Surface"]
        direction TB
        UI["Pixel Fold Compose UI"]
        IME["Smart Keyboard (IME)"]
        Voice["Voice Composition"]
    end

    subgraph SDKBoundary["SDK & Contract Gate"]
        direction TB
        SDK["OsirisClient (Typed SDK)"]
        Val["DNA-Lang L0 Validator"]
    end

    subgraph GovernanceBoundary["Governance Boundary"]
        direction TB
        Gov["Capability Engine"]
        Policy["Policy & Expiry Rules"]
    end

    subgraph ExecutionPlane["Execution Plane"]
        direction TB
        Local["Local Adapter (Termux / PRoot)"]
        Remote["Remote Adapter (Cloud Worker)"]
    end

    subgraph LedgerBoundary["Evidence & Promotion Gate"]
        direction TB
        Eval["Independent Evaluators"]
        Ledger["Dynamic Evidence Ledger"]
        AuthGate{"Human Authority Gate"}
        Deploy["Release / Deployment"]
    end

    InputSurface -->|Typed Intent| SDKBoundary
    SDKBoundary -->|Validated Intent| GovernanceBoundary
    GovernanceBoundary -->|Authorized Capability| ExecutionPlane
    ExecutionPlane -->|Execution Artifacts| LedgerBoundary
    Eval --> Ledger
    Ledger --> AuthGate
    AuthGate -->|Explicit Approval| Deploy
```

### 3.2 Goals
- **Adaptive Ergonomics**: Native, accessible development environment tailored to both cover screen (compact single-pane) and inner folding display (expanded dual-pane workspace).
- **Structured Intent Synthesis**: Transform human requests into validated, typed DNA-Lang intent genomes with deterministic validation before execution.
- **Local-First Autonomy**: Full task composition, draft inspection, cached repository browsing, and local test evaluation functional without network access.
- **Strict Capability Governance**: Least-privilege capability grants for every consequential action (filesystem writes, Git commits, network requests, secret access).
- **Durable Provenance & Evidence**: Cryptographic manifests recording input revisions, tool versions, test telemetry, and approval receipts across all lifecycle events.
- **Reproducible Promotion**: Byte-verifiable CI/CD promotion pipelines requiring signed human authorization before distribution.

### 3.3 Explicit Non-Goals (First Deliverable)
- **NO Unrestricted Shell Access**: The Android application and keyboard SHALL NOT have ambient, arbitrary shell execution rights.
- **NO Silent Execution**: Typing, dictation, autocompletion, or model generation MUST NEVER directly trigger code execution, Git mutation, or network dispatch without explicit user intent preview and confirmation.
- **NO Autonomous Model Promotion**: A language model proposal cannot authorize its own merge, release, or deployment.
- **NO Ambient Snooping**: Zero capture of background app keystrokes, clipboard history, password fields, or personal notifications.
- **NO Premature Scientific Claims**: No claim that OSIRIS or NCLM has achieved continuous learning efficacy without a separate preregistered empirical evidence package.
- **NO Digest-as-Trust Fallacy**: A cryptographic digest establishes byte identity, not trustworthiness or safety.

---

## 4. Trust Boundaries & Security Invariants

### 4.1 Boundary Matrix

```mermaid
flowchart TD
    subgraph UntrustedZone["Untrusted Input Zone"]
        KBD["Keyboard Input / Dictation"]
        LLM["Model Output / Proposals"]
        Web["External Tool Responses"]
        Repo["Untrusted Code / Repos"]
    end

    subgraph AndroidAppSandbox["Android Application Sandbox"]
        ComposeUI["Adaptive Compose UI"]
        RoomDB["Encrypted Room DB (Task State)"]
        Keystore["Android Keystore (Keys / Secrets)"]
    end

    subgraph LocalExecutionSandbox["Local Developer Runtime (Node Alpha)"]
        Termux["Termux / PRoot Environment"]
        PythonCore["OSIRIS CLI / DNA-Lang Python"]
        OllamaLocal["Local SLM / Ollama (127.0.0.1)"]
    end

    subgraph RemoteExecutionPlane["Remote Compute Plane (Node Beta / Cloud)"]
        CloudWorker["Authenticated Worker / Container"]
        QPU["Quantum Hardware Bridge (IBM / Heron)"]
    end

    UntrustedZone -->|Typed Sanitization| AndroidAppSandbox
    AndroidAppSandbox -->|Explicit IPC Bridge (Policy Checked)| LocalExecutionSandbox
    AndroidAppSandbox -->|mTLS / OAuth2 (Short-Lived Token)| RemoteExecutionPlane
```

1. **Keyboard is an Input Surface**: The input method service possesses zero execution privileges. It communicates only with the host app via bounded Android Intents/IPC.
2. **Sandbox Separation**: The Android application sandbox and Termux/PRoot developer environments are isolated. Inter-environment communication MUST traverse an explicit, audited bridge with strict path/argument validation.
3. **No Embedded Credentials**: Service account keys, cloud tokens, and signing secrets MUST NEVER be packaged in the APK or AAB bundle.
4. **Independent Execution Identities**: Local edge execution (`Node Alpha: Fold7`) and remote workstation/cloud execution (`Node Beta: WSL/GCP`) MUST carry distinct cryptographic identities, policy rules, and provenance tags in the evidence ledger.

---

## 5. Pixel Fold Adaptive UI Specification

### 5.1 Display Form Factors & Postures

The application MUST query `androidx.window.layout.WindowInfoTracker` to continuously monitor window metrics and folding hinge posture:

```mermaid
stateDiagram-v2
    [*] --> Folded_Cover
    Folded_Cover --> Unfolded_Flat: Hinge opens (180°)
    Unfolded_Flat --> Folded_Cover: Hinge closes (0°)
    Unfolded_Flat --> Tabletop_Posture: Half-folded horizontal (90°-120°)
    Unfolded_Flat --> Book_Posture: Half-folded vertical (90°-120°)
    Tabletop_Posture --> Unfolded_Flat: Flattened
    Book_Posture --> Unfolded_Flat: Flattened
```

| Window Configuration | Layout Pattern | Display Allocation | User Workflow |
| :--- | :--- | :--- | :--- |
| **Folded (Cover Screen)**<br>`Compact (< 600dp)` | Single-pane navigation stack | Full width: 1 primary pane | Task capture, status monitor, quick approvals, voice composition. |
| **Unfolded (Inner Screen)**<br>`Expanded (≥ 840dp)` | Dual-pane master-detail / supporting pane | Left: 40% (Project/Task Tree)<br>Right: 60% (Editor / Evidence Viewer) | Full technical workflow: code review, AST inspection, test telemetry. |
| **Tabletop Posture**<br>`Half-opened (horizontal)` | Split horizontal presentation | Upper: Log output / telemetry viewer<br>Lower: Smart keyboard / command deck | Hands-free monitoring and quick command interaction. |
| **Book Posture**<br>`Half-opened (vertical)` | Two-page document review | Left: Spec / Diff<br>Right: Acceptance test checklist | Document review and preregistration verification. |
| **Multi-Window / Split** | Adaptive responsive pane | Minimum width: 320dp; reflows controls gracefully | Side-by-side terminal or reference doc pairing. |

### 5.2 Lifecycle & State Preservation Invariants
- **Config Change Continuity**: 100% of acknowledged task IDs, uncommitted drafts, scroll positions, and pending approval prompts MUST survive fold/unfold, rotation, and multi-window resizing without data loss.
- **Process Recreation**: If the OS terminates the app process during background task execution, the durable task state in Room MUST restore to the exact pre-death state, displaying `RUNNING` or `AWAITING_RECONNECT`. An unconfirmed task MUST NEVER be reported as completed.
- **Accessibility Invariants**: All interactive components MUST provide content descriptions, support logical focus navigation for hardware keyboards, maintain minimum 48×48dp touch targets, support 200% dynamic font scaling, and never convey status via color alone.

---

## 6. OSIRIS Smart Keyboard (`InputMethodService`)

### 6.1 Functional Architecture

```mermaid
flowchart TD
    subgraph IME["OSIRIS Smart Keyboard Service"]
        Touch["Touch Input Engine"]
        VoiceEngine["Voice Transcription Engine"]
        DevToolbar["Developer Quick-Bar"]
        IntentComp["Intent Composer Engine"]
    end

    subgraph PrivacyFilter["Privacy & Input Filter"]
        PassDetect{"InputType is Password / Sensitive?"}
        Redact["Suppress Suggestions & Remote Sync"]
        Normal["Active Context Engine"]
    end

    subgraph UIOutput["Keyboard UI Deck"]
        KeyGrid["Adaptive Key Deck (QWERTY / Dev)"]
        TranscriptPreview["Editable Voice Transcript"]
        IntentPreviewDeck["Intent & Capability Preview Deck"]
    end

    Touch --> PassDetect
    VoiceEngine --> TranscriptPreview
    DevToolbar --> Touch
    PassDetect -->|Yes| Redact
    PassDetect -->|No| Normal
    Redact --> KeyGrid
    Normal --> KeyGrid
    TranscriptPreview --> IntentComp
    IntentComp --> IntentPreviewDeck
```

### 6.2 Key Modes & Interactions
1. **Conventional Typing**: Full QWERTY layout, punctuation, auto-correction, cursor gestures, and text selection.
2. **Developer & DNA-Lang Deck**:
   - Direct-access programming symbols: `{ } [ ] ( ) < > : : ; " ' \ / | _ = + - * % $ # @ ~ ^ &`.
   - DNA-Lang token snippets: `intent::`, `probe::`, `verify::`, `genome::`, `ledger::`.
   - Indentation helpers: Tab, Shift-Tab, multi-line comment wrapping.
3. **Explicit Voice Composition**:
   - Voice capture is strictly opt-in and initiated by a dedicated microphone press.
   - Real-time audio waveform is visibly displayed.
   - Raw audio stream is ephemeral and deleted immediately after local transcription.
   - Recognized text appears in an **editable transcript field** before submission.
4. **Context Attachment Deck**:
   - User can deliberately attach active files, git diffs, recent test failures, or log traces to the task draft.
5. **Intent Preview & Gate**:
   - Shows summary of proposed task, target files, requested capabilities, and potential side effects.
   - User must tap an explicit "Submit Intent" button; typing or dictation alone **NEVER** initiates execution.

### 6.3 Privacy & Data Isolation Guarantees
- **No Keystroke Logging**: The keyboard service SHALL NOT log raw keystrokes to disk or send keystrokes over any network.
- **Password Field Suppression**: When `EditorInfo.inputType` matches `TYPE_TEXT_VARIATION_PASSWORD`, `TYPE_TEXT_VARIATION_WEB_PASSWORD`, or `TYPE_TEXT_VARIATION_VISIBLE_PASSWORD`, the keyboard MUST:
  - Disable all suggestions and autocompletions.
  - Disable voice capture and cloud routing.
  - Suppress telemetry and memory learning.
- **Clipboard Isolation**: Access to platform clipboard MUST be explicitly confirmed by user action.

---

## 7. Typed Android SDK & Contract Specification

### 7.1 Proposed Kotlin Interface Contract

```kotlin
package org.osiris.android.sdk

/**
 * Normative entry point for OSIRIS Android runtime interactions.
 * All operations return typed, versioned data contracts.
 */
interface OsirisClient {
    /**
     * Submits a user-authored task intent for validation and scheduling.
     * Enforces idempotency via request.idempotencyKey.
     */
    suspend fun submitIntent(request: IntentRequest): IntentReceipt

    /**
     * Polls or streams the live execution state of an accepted task.
     */
    suspend fun inspectExecution(executionId: String): ExecutionSnapshot

    /**
     * Retrieves the independent evaluation report for a completed execution.
     */
    suspend fun evaluate(executionId: String): EvaluationReport

    /**
     * Retrieves the cryptographic evidence manifest and hash audit trail.
     */
    suspend fun getEvidence(executionId: String): EvidenceManifest

    /**
     * Requests authorization for a consequential operation.
     */
    suspend fun requestCapability(request: CapabilityRequest): CapabilityDecision
}
```

### 7.2 Core Data Schemas

```mermaid
classDiagram
    class IntentRequest {
        +String schemaVersion
        +String requestId
        +String idempotencyKey
        +String naturalLanguageTask
        +List~ContextRef~ contextAttachments
        +ExecutionMode requestedMode
        +Map~String, String~ parameters
        +Instant createdAt
    }

    class IntentReceipt {
        +String schemaVersion
        +String executionId
        +ReceiptStatus status
        +String requestDigestSha256
        +List~ValidationDiagnostic~ diagnostics
        +Instant timestamp
    }

    class ExecutionSnapshot {
        +String executionId
        +ExecutionState state
        +ExecutionAdapterType adapter
        +Long currentSequence
        +Integer exitCode
        +List~String~ recentLogLines
        +Instant updatedAt
    }

    class CapabilityRequest {
        +String requestId
        +String subject
        +ActionType action
        +String targetResource
        +Scope scope
        +Duration requestedLifetime
        +RiskClass riskClass
        +String justification
    }

    class CapabilityDecision {
        +String decisionId
        +DecisionStatus status
        +String grantId
        +Scope grantedScope
        +Instant expiresAt
        +String policyVersion
        +String reasonCode
    }

    class EvaluationReport {
        +String executionId
        +String evaluatorIdentity
        +String evaluatorVersion
        +EvaluationOutcome outcome
        +List~TestResult~ testResults
        +Map~String, Double~ measuredMetrics
        +List~String~ limitations
    }

    class EvidenceManifest {
        +String schemaVersion
        +String executionId
        +String repositoryCommit
        +String genomeRevision
        +String policyRevision
        +ExecutionMode mode
        +Instant startedAt
        +Instant finishedAt
        +Map~String, String~ artifactDigests
        +String approvalReceiptId
        +String claimCeiling
    }

    IntentRequest --> IntentReceipt
    IntentReceipt --> ExecutionSnapshot
    CapabilityRequest --> CapabilityDecision
    ExecutionSnapshot --> EvaluationReport
    EvaluationReport --> EvidenceManifest
```

### 7.3 Execution State Machine

```mermaid
stateDiagram-v2
    [*] --> DRAFT: User drafts intent in Smart Keyboard
    DRAFT --> VALIDATED: DNA-Lang L0 AST validation passes
    DRAFT --> REJECTED: AST syntax / policy failure
    
    VALIDATED --> AWAITING_AUTHORIZATION: Consequential capability required
    VALIDATED --> QUEUED: Low-risk / pre-authorized action
    
    AWAITING_AUTHORIZATION --> QUEUED: User grants explicit capability
    AWAITING_AUTHORIZATION --> REJECTED: User denies grant or grant expires
    
    QUEUED --> RUNNING: Dispatch to local / remote adapter
    RUNNING --> EVALUATING: Process completes with exit code 0
    RUNNING --> FAILED: Process exit code != 0 or runtime crash
    RUNNING --> CANCELLED: Explicit user cancellation confirmed
    RUNNING --> EXPIRED: Temporal horizon reached (300s Alpha / 1800s Beta)
    
    EVALUATING --> COMPLETED: All evaluators pass; evidence generated
    EVALUATING --> FAILED: Evaluator assertions fail
    EVALUATING --> INCONCLUSIVE: Evaluator missing or timed out
    
    COMPLETED --> [*]
    FAILED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
    INCONCLUSIVE --> [*]
```

---

## 8. Hybrid Local-First Execution Architecture

### 8.1 Node Alpha Local Execution (Fold7 / Termux)
- **Local Developer Adapter**: Interacts with the local Termux / PRoot environment over a strictly controlled local Unix domain socket or loopback interface (`127.0.0.1`).
- **Temporal Horizon Enforcement**: Under the OSIRIS Sovereign Execution Contract, all local commands on Node Alpha are bounded by a hard **300.0s** execution limit to protect mobile thermal and battery limits.
- **Path Sanitization**: Relative paths, directory traversal (`..`), shell metacharacters, and unauthorized root access are rejected prior to dispatch.

### 8.2 Node Beta / Cloud Remote Execution
- **Remote Execution Adapter**: Connects to the user's primary workstation (`Node Beta`) or cloud runner via mutual TLS (mTLS) and short-lived signed tokens.
- **Workstation Horizon**: Jobs executing on Node Beta operate under an extended **1800.0s** horizon with full AVX2/AVX-VNNI batching.
- **No Stored Cloud Secrets**: Cloud credentials reside exclusively in server-side Secret Manager environments.

### 8.3 Offline Resilience & State Reconciliation
- **Inspectable Offline State**: All previously synced projects, genomes, manifests, and local drafts remain fully inspectable without network connectivity.
- **Idempotency & Reconnection**: Tasks queued for remote execution require valid, unexpired capability grants. If network is lost during remote execution, the task transitions to `AWAITING_RECONNECT`. The app polls for task completion using the immutable `idempotencyKey` and `executionId` without launching duplicate jobs.

---

## 9. Measurable Acceptance-Test Plan (39 Criteria)

### Suite A: Build & Contract Integrity

| Test ID | Title | Method / Harness | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| `AT-BLD-01` | Clean Gradle Build | Execute `./gradlew assembleDebug` on clean clone | 100% build success using pinned Kotlin, AGP, and Gradle toolchain without network downloads during build. |
| `AT-BLD-02` | Build Repeatability | Perform two successive builds from identical commit | Source and artifact manifests are byte-equivalent; APK signing metadata matches declared identity. |
| `AT-API-01` | Contract Serialization | Round-trip JSON/CBOR serialization of all contract fixtures | 100% of checked-in fixtures match normalized golden representations byte-for-byte. |
| `AT-API-02` | Invalid Input Rejection | Feed malformed schemas and unsupported major versions | 100% rejected with deterministic error taxonomy (`ERR_SCHEMA_MISMATCH`, `ERR_VERSION_UNSUPPORTED`). |
| `AT-API-03` | Idempotent Submission | Replay identical `IntentRequest` 100 times consecutively | Exactly 1 logical task created; subsequent submissions return identical `executionId` with zero side effects. |
| `AT-API-04` | State Machine Invariants | Attempt 100 invalid state transitions (e.g., `DRAFT → COMPLETED`) | 100% of illegal transitions rejected, logged, and state preserved in durable store. |

### Suite B: Pixel Fold UI & Lifecycle

| Test ID | Title | Method / Harness | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| `AT-UI-01` | Fold/Unfold Transitions | 20 automated fold/unfold cycles on physical Pixel Fold / Emulator | Zero crash, zero ANR, 100% acknowledged task state and uncommitted text preserved across transitions. |
| `AT-UI-02` | Screen Rotation & Resizing | 20 rapid configuration rotation cycles (0°, 90°, 180°, 270°) | No layout clipping of primary controls (approval buttons, log decks); active ViewModel state retained intact. |
| `AT-UI-03` | Multi-Window Split Operation | Resize app window dynamically between 33%, 50%, 67%, 100% | Critical task inspection, cancellation, and capability approval buttons remain visible and interactive. |
| `AT-UI-04` | Process Death Recovery | Force process kill (`kill -9`) while task is in `QUEUED` / `RUNNING` | On relaunch, task state restores from Room DB; task NEVER falsely reported as completed without receipt. |
| `AT-UI-05` | Accessibility Standards | Android Accessibility Scanner & TalkBack traversal | 0 critical/major a11y errors; all interactive touch targets ≥ 48×48dp; focus order matches visual hierarchy. |
| `AT-UI-06` | Dynamic Theming & Font Scaling | Evaluate UI in Light, Dark, and 200% dynamic font scaling | All labels readable without truncation of essential numbers or cryptographic hashes. |

### Suite C: Smart Keyboard (`InputMethodService`)

| Test ID | Title | Method / Harness | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| `AT-IME-01` | Standard Text Editing | Type, select, delete, replace across standard `EditText` targets | 100% expected text insertion without dropping characters or misplacing cursor. |
| `AT-IME-02` | Developer Snippets | Insert code templates and DNA-Lang symbols (`::`, `{ }`, `->`) | Exact token strings inserted without modifying surrounding text context. |
| `AT-IME-03` | Voice Composition Editability | Dictate 50-word prompt, view transcript in preview deck | Transcript is fully editable by touch/cursor before intent synthesis is triggered. |
| `AT-IME-04` | Voice Capture Cancellation | Press voice button, speak, press Cancel | Audio recording terminates immediately; zero audio buffers retained; zero bytes transmitted. |
| `AT-IME-05` | Password Field Isolation | Focus `inputType = textPassword` | Suggestions disabled; dictation disabled; zero network transmissions; zero sensitive strings in logcat. |
| `AT-IME-06` | Non-Implicit Execution | Type valid shell command, accept completion, dictate prompt | 0 background processes spawned; 0 network calls dispatched; execution requires explicit user tap on "Execute". |
| `AT-IME-07` | Offline Keyboard Operation | Enable Airplane Mode; compose code and intent templates | Keyboard remains 100% responsive for typing, templates, and local intent drafting. |

### Suite D: Governance & Security Invariants

| Test ID | Title | Method / Harness | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| `AT-SEC-01` | Unauthorized Action Block | Dispatch unprivileged request attempting to write to `/etc` or git | 100% denied with `ERR_CAPABILITY_DENIED`; audit log entry emitted. |
| `AT-SEC-02` | Expired Capability Rejection | Attempt action using grant past its `expiresAt` timestamp | 100% denied with `ERR_CAPABILITY_EXPIRED`; zero execution occurs. |
| `AT-SEC-03` | Revoked Capability Rejection | Revoke active grant, then attempt consequential operation | Operation blocked immediately; in-flight tasks terminated cleanly within 2.0s. |
| `AT-SEC-04` | Path & Argument Traversal | Inject `../../`, `; rm -rf`, and pipe characters into parameters | Rejected at SDK boundary with `ERR_MALFORMED_ARGUMENT`; zero shell execution. |
| `AT-SEC-05` | Static Secret Scanning | Scan APK bundle and git diff with truffleHog and custom scanner | Zero private keys, API tokens, or hardcoded passwords detected in release bundle. |
| `AT-SEC-06` | Model / Tool Spoofing Resistance | Inject adversarial model output claiming "PERMISSION GRANTED BY ROOT" | Policy engine ignores model claim; requires valid cryptographically signed grant. |
| `AT-SEC-07` | Evidence Tampering Detection | Alter 1 byte in evidence manifest or artifact bundle | Verification engine reports hash mismatch; blocks release promotion. |
| `AT-SEC-08` | Permission Minimization | Audit `AndroidManifest.xml` against declared features | No dangerous permissions present without documented, reviewed justification (e.g., zero SMS/Location). |

### Suite E: Hybrid Execution & Network Resilience

| Test ID | Title | Method / Harness | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| `AT-HYB-01` | Offline Draft & Inspection | Create, edit, and save drafts in Airplane Mode; restart app | 100% of draft fields recovered from local encrypted storage. |
| `AT-HYB-02` | Mid-Flight Network Droppage | Sever network during remote cloud job execution | UI displays `AWAITING_RECONNECT`; does not crash; never fabricates success. |
| `AT-HYB-03` | Network Reconnection | Re-establish connection after severed network | Reconnects cleanly; reconciles remote job status; zero duplicate tasks launched. |
| `AT-HYB-04` | Credential Rejection | Attempt remote dispatch with invalid / expired auth token | Request rejected with HTTP 401/403; zero token leakage in client logs. |
| `AT-HYB-05` | Adapter Parity | Run identical test suite against local Termux and remote worker | Identical normalized `EvaluationReport` structure emitted across both substrates. |
| `AT-HYB-06` | Bounded Execution Horizon | Launch long-running command exceeding temporal horizon | Process forcefully terminated at 300.0s (Node Alpha) or 1800.0s (Node Beta); state = `EXPIRED`. |

### Suite F: Evidence, Release & Promotion Governance

| Test ID | Title | Method / Harness | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| `AT-EVD-01` | Manifest Completeness | Verify output of completed task runs | 100% of manifests contain all mandatory fields; missing mandatory field blocks promotion. |
| `AT-EVD-02` | Artifact Digest Verification | Recompute SHA-256 for all produced artifacts | 100% match recorded digests in `EvidenceManifest`. |
| `AT-EVD-03` | Failing Test Blocks Promotion | Deliberately inject 1 unit test failure into release candidate | CI/CD promotion gate halts immediately; release artifact tagging blocked. |
| `AT-EVD-04` | Missing Evaluator Handling | Run task with missing or crashing evaluator script | Result marked `INCONCLUSIVE` or `BLOCKED`; NEVER marked as `TESTED_PASS`. |
| `AT-REL-01` | Human Authorization Enforcement | Attempt release promotion without valid signed approval receipt | Pipeline halts at Gate 0; release cannot be published to GitHub or Zenodo. |
| `AT-REL-02` | Unauthorized Branch Promotion | Attempt merge into `main` without required checks | Git branch protection and OCCR authority block merge; audit event logged. |
| `AT-REL-03` | Full Provenance Traceability | Inspect release candidate metadata | Contains git commit, build toolchain, test report hash, and signing identity. |
| `AT-REL-04` | Automated Staging Rollback | Trigger simulated release failure in staging deployment | Restores previous verified artifact within 60s; emits rollback evidence receipt. |

### Suite G: Performance Benchmarks (Pixel Fold Hardware)

| Test ID | Metric | Measurement Condition | Initial Target Threshold |
| :--- | :--- | :--- | :--- |
| `AT-PERF-01` | Warm App Launch | From background to interactive UI on Pixel Fold | $p_{95} \le 2.0\text{ seconds}$ |
| `AT-PERF-02` | UI Interaction Latency | Local navigation, draft switching, task inspection | $p_{95} \le 100\text{ ms}$ |
| `AT-PERF-03` | 30-Minute Soak Stability | Continuous scripted typing, folding, and task creation | 0 ANRs, 0 unhandled exceptions, memory stable |
| `AT-PERF-04` | Idle Network Activity | App idle with remote sync disabled | 0 background network transmissions |
| `AT-PERF-05` | Thermal & Battery Footprint | Continuous 15-minute local intent compilation | Temperature $\le 41^\circ\text{C}$; battery drain $\le 1.5\% / \text{hr}$ |

---

## 10. Phased Implementation Roadmap & Exit Gates

```mermaid
gantt
    title OSIRIS Pixel Fold Android Delivery Phases
    dateFormat  YYYY-MM-DD
    section Phase 1: Foundation
    Compose App Shell & Adaptive Layout     :p1_1, 2026-10-12, 14d
    Typed SDK Contracts & Serialization     :p1_2, after p1_1, 10d
    Local Fake Runtime & Room DB            :p1_3, after p1_2, 7d
    Phase 1 Exit Gate Review                :crit, p1_gate, after p1_3, 3d

    section Phase 2: Smart Keyboard
    InputMethodService & Typing Engine       :p2_1, after p1_gate, 14d
    Developer Symbols & DNA-Lang Deck       :p2_2, after p2_1, 7d
    Explicit Voice Composition Engine       :p2_3, after p2_2, 10d
    Privacy Filters & Sensitive Fields      :p2_4, after p2_3, 7d
    Phase 2 Exit Gate Review                :crit, p2_gate, after p2_4, 3d

    section Phase 3: Governance & Local
    DNA-Lang L0 AST Parser Integration      :p3_1, after p2_gate, 10d
    Capability Decision Engine              :p3_2, after p3_1, 10d
    Termux / PRoot Local Bridge             :p3_3, after p3_2, 10d
    Evidence Ledger & Digest Recorder       :p3_4, after p3_3, 7d
    Phase 3 Exit Gate Review                :crit, p3_gate, after p3_4, 3d

    section Phase 4: DevOps & Cloud
    Authenticated Remote Execution Bridge   :p4_1, after p3_gate, 14d
    Git & CI/CD Pipeline Automation         :p4_2, after p4_1, 10d
    Release Attestation & Provenance Gate   :p4_3, after p4_2, 7d
    Phase 4 Exit Gate Review                :crit, p4_gate, after p4_3, 3d

    section Phase 5: Hardening & Release
    Physical Pixel Fold Soak Testing        :p5_1, after p4_gate, 10d
    Accessibility & Performance Audit       :p5_2, after p5_1, 7d
    Final Security Review & Signing Audit   :p5_3, after p5_2, 7d
    Release Candidate Authorization         :crit, p5_gate, after p5_3, 3d
```

### Exit Gate Criteria
- **Phase 1 Gate**: Debug APK builds cleanly; 100% contract serialization tests pass; fold/unfold maintains acknowledged task state.
- **Phase 2 Gate**: Keyboard passes IME matrix; password fields emit 0 logs/network requests; zero actions trigger from typing alone.
- **Phase 3 Gate**: Unauthorized execution matrix 100% blocked; state transitions fully replayable; missing evidence halts execution.
- **Phase 4 Gate**: Remote network failure recovery verified; zero credentials embedded in APK; failing tests block promotion.
- **Phase 5 Gate**: 0 high/critical vulnerabilities; all 39 acceptance criteria marked `TESTED_PASS`; human authorization signed.

---

## 11. Proposed Project Directory Structure

```text
osiris-android/
├── app/                          # Native Android Jetpack Compose Application
│   ├── src/main/kotlin/          # UI ViewModels, Screens, Navigation
│   │   ├── adaptive/             # WindowSizeClass & Folding Hinge Posture Handlers
│   │   ├── journal/              # Task Journal & Local Status Views
│   │   ├── evidence/             # Evidence Ledger & Manifest Inspector
│   │   └── approvals/            # Human Capability Authorization Deck
│   └── src/main/res/             # Layouts, themes, drawables, accessibility strings
├── keyboard/                     # OSIRIS Smart Keyboard (InputMethodService)
│   ├── src/main/kotlin/
│   │   ├── ime/                  # InputMethodService lifecycle & key event dispatch
│   │   ├── voice/                # Ephemeral voice capture & local transcription
│   │   ├── devdeck/              # Developer quick-bar & DNA-Lang snippet engine
│   │   └── privacy/              # Sensitive input field detector & content sanitizer
├── sdk/                          # Platform Client SDK
│   ├── contracts/                # Versioned data models (IntentRequest, Manifest, etc.)
│   ├── client/                   # OsirisClient implementation & IPC handler
│   └── security/                 # Capability request & Android Keystore bindings
├── runtime-bridge/               # Local Edge Execution Bridge (Node Alpha)
│   ├── termux/                   # Unix domain socket / loopback adapter for Termux
│   └── proot/                    # Sandboxed command dispatcher & argument validator
├── dnalang-adapter/              # DNA-Lang Intent Compiler & L0 AST Validator
├── governance/                   # Capability & Policy Decision Engine
├── execution/                    # Execution Substrates
│   ├── local/                    # Local-first executor (300s temporal lock)
│   └── remote/                   # Authenticated remote job runner (1800s horizon)
├── evidence/                     # Dynamic Evidence Ledger & Digest Calculator
├── evaluation/                   # Independent Test Runners & Metric Evaluators
├── devops/                       # CI/CD Workflows, Signing Scripts, Provenance Tools
└── docs/
    ├── architecture.md           # Subsystem architecture diagrams
    ├── threat-model.md           # STRIDE security & privacy threat model
    └── acceptance-tests.md       # Full 39-point test execution guide
```

---

## 12. Architectural Decision Records (ADRs) to Resolve

| ADR ID | Decision Title | Scope | Status |
| :--- | :--- | :--- | :--- |
| `ADR-AND-001` | Minimum Android API Level | Target API 35 (Android 15), Min API 33 (Android 13) | `PROPOSED` |
| `ADR-AND-002` | App-to-Termux IPC Mechanism | Unix Domain Socket over Local Abstract Namespace vs. File Provider | `PROPOSED` |
| `ADR-AND-003` | On-Device Speech Transcription | Local Whisper.tflite / Vosk vs. System SpeechRecognizer API | `PROPOSED` |
| `ADR-AND-004` | Local Storage Encryption | SQLCipher / EncryptedSharedPreferences via Android Keystore | `PROPOSED` |
| `ADR-AND-005` | Release Signing Identity Custody | Hardware Security Module (YubiKey/KMS) with separate release officer role | `PROPOSED` |

---

## 13. Release Decision Rule

A release candidate is eligible for human review **ONLY** when:
1. All mandatory acceptance tests (`AT-BLD-01` through `AT-REL-04`) possess documented evidence with `TESTED_PASS` status.
2. Zero open high or critical security findings remain without a formal exception record signed by the governance officer.
3. Source commit, build environment, dependencies, toolchain, artifact digests, and signing key fingerprints are recorded in the release manifest.
4. The promotion policy independently certifies that all evidence manifests are complete and untampered.

> [!CAUTION]
> **Eligibility for review is strictly distinct from authorization to deploy.** Human authorization remains an explicit, non-delegable administrative act.

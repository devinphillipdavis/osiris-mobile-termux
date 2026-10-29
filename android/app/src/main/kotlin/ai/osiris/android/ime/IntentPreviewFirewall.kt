package ai.osiris.android.ime

import java.util.Locale

/**
 * Risk classification for AST-analyzed operations.
 */
enum class RiskLevel {
    LOW,
    MODERATE,
    HIGH,
    CRITICAL
}

/**
 * Mobile session task risk level classification.
 */
enum class IntentRiskLevel {
    SAFE, LOW, MEDIUM, HIGH, CRITICAL, UNTRUSTED
}

/**
 * Epistemic provenance and validation status of an AST command candidate.
 */
sealed interface AstProvenance {
    companion object {
        operator fun invoke(
            nodeType: String,
            identifier: String,
            arguments: List<String> = emptyList(),
            isSystemPrimitive: Boolean = false,
            chainsToDestructive: Boolean = false
        ): Node = Node(
            nodeType = nodeType,
            identifier = identifier,
            arguments = arguments,
            isSystemPrimitive = isSystemPrimitive,
            chainsToDestructive = chainsToDestructive
        )
    }

    /**
     * Verified action successfully parsed and confirmed safe by the local trusted computing base (TCB).
     */
    data class VerifiedKernelAst(
        val toolName: String,
        val targetResource: String,
        val riskLevel: RiskLevel,
        val modifiesState: Boolean,
        val parameters: Map<String, String> = emptyMap(),
        val description: String = ""
    ) : AstProvenance

    /**
     * Rejected, ambiguous, or untrusted candidate payload intercepted by the L0 firewall.
     */
    data class UnverifiedOrUntrusted(
        val rawInput: String,
        val firewallRejectionReason: String,
        val detectedDangerousTokens: List<String> = emptyList()
    ) : AstProvenance

    /**
     * Syntactic AST node provenance for mobile session firewall checks.
     */
    data class Node(
        val nodeType: String,
        val identifier: String,
        val arguments: List<String> = emptyList(),
        val isSystemPrimitive: Boolean = false,
        val chainsToDestructive: Boolean = false
    ) : AstProvenance
}

sealed interface ActionPreviewResult {
    data class Allowed(val targetUri: String, val parameters: Map<String, String>, val risk: IntentRiskLevel) : ActionPreviewResult
    data class Rejected(val reason: String, val violatingAst: AstProvenance.Node) : ActionPreviewResult
}

/**
 * Deterministic AST Action Preview Firewall.
 *
 * Interposition Rule:
 * Resolves action previews strictly via local static AST parsing inside the trusted computing base.
 * NEVER uses model completion text or speculative LLM summaries to generate side-effect previews.
 */
interface IntentPreviewFirewall {
    /**
     * Analyzes candidate command string and produces verified AST provenance.
     */
    fun analyzeCommand(commandText: String): AstProvenance =
        DefaultIntentPreviewFirewall().analyzeCommand(commandText)

    /**
     * Parses and validates a mobile intent string into an ActionPreviewResult.
     */
    fun parseAndValidateIntent(rawIntent: String, context: Any? = null): ActionPreviewResult =
        IntentPreviewFirewallImpl().parseAndValidateIntent(rawIntent, context)
}

/**
 * Mobile session implementation of IntentPreviewFirewall returning ActionPreviewResult.
 */
class IntentPreviewFirewallImpl : IntentPreviewFirewall {

    companion object {
        private val DENYLISTED_PRIMITIVES = setOf(
            "exec", "eval", "compile", "__import__", "os.system", "subprocess", "rm -rf", "/etc/passwd"
        )
        private val CHAINING_OPERATORS = setOf("&&", ";", "||")
        private val IMMUTABLE_GOVERNANCE_TARGETS = setOf("policy.json", "cloudbuild.yaml")
        private val ALLOWLISTED_GRAMMAR = setOf("/ignite", "/learn", "/dna", "/ledger", "/status", "/sim")
    }

    override fun parseAndValidateIntent(rawIntent: String, context: Any?): ActionPreviewResult {
        val normalized = rawIntent.trim()
        if (normalized.isEmpty()) {
            return ActionPreviewResult.Rejected(
                reason = "Empty intent is not permitted.",
                violatingAst = AstProvenance("Empty", rawIntent)
            )
        }

        // 1. First check for primitives so that primitive rejection takes precedence before any allowlist match
        val violatedPrimitive = DENYLISTED_PRIMITIVES.firstOrNull { normalized.contains(it) }
        if (violatedPrimitive != null) {
            return ActionPreviewResult.Rejected(
                reason = "Forbidden execution primitive detected: $violatedPrimitive",
                violatingAst = AstProvenance("Call", violatedPrimitive, isSystemPrimitive = true)
            )
        }

        // 2. Chaining operators MUST be evaluated before any allowlist match
        val hasChaining = CHAINING_OPERATORS.any { normalized.contains(it) } ||
            normalized.contains("\n") || normalized.contains("\r") || normalized.contains("|") ||
            normalized.contains("`") || normalized.contains("$(")
        if (hasChaining) {
            return ActionPreviewResult.Rejected(
                reason = "Multi-statement chaining is strictly prohibited.",
                violatingAst = AstProvenance("ChainOperator", rawIntent, chainsToDestructive = true)
            )
        }

        // 3. Governance Target Mutation Check MUST be evaluated before any allowlist match
        val targetsGovernance = IMMUTABLE_GOVERNANCE_TARGETS.firstOrNull { normalized.contains(it) }
        if (targetsGovernance != null) {
            return ActionPreviewResult.Rejected(
                reason = "Attempted mutation of immutable governance target: $targetsGovernance",
                violatingAst = AstProvenance("FileWrite", targetsGovernance)
            )
        }

        // 4. Strict command token allowlist check and argument extraction
        val tokens = normalized.split(Regex("\\s+"))
        val command = tokens.first()
        if (command in ALLOWLISTED_GRAMMAR) {
            val args = tokens.drop(1)
            val params = args.mapIndexed { idx, arg -> "arg$idx" to arg }.toMap()
            return ActionPreviewResult.Allowed(
                targetUri = command,
                parameters = params,
                risk = IntentRiskLevel.SAFE
            )
        }

        return ActionPreviewResult.Rejected(
            reason = "Intent does not match allowlisted grammar and requires manual review.",
            violatingAst = AstProvenance("Unknown", rawIntent)
        )
    }
}

/**
 * Canonical implementation of the OSIRIS Deterministic Intent Preview Firewall.
 */
class DefaultIntentPreviewFirewall : IntentPreviewFirewall {

    companion object {
        // Prohibited dynamic execution and shell escape primitives (AT-SEC-11)
        private val DANGEROUS_TOKENS = setOf(
            "exec(", "eval(", "compile(", "__import__",
            "os.system", "subprocess.popen", "subprocess.run",
            "rm -rf", "rmdir /s", "mkfs", "dd if=",
            "/etc/passwd", "/etc/shadow", "/dev/mem", "/sys/kernel",
            "curl -s | bash", "wget -O- | sh", ":(){ :|:& };:"
        )

        // Sensitive paths protected against direct file mutations
        private val PROTECTED_TARGETS = setOf(
            "policy.json",
            "cloudbuild.yaml",
            "quarantine_notice.md",
            "core_test.py",
            "osiris_master_specification"
        )
    }

    override fun analyzeCommand(commandText: String): AstProvenance {
        val trimmed = commandText.trim()
        if (trimmed.isEmpty()) {
            return AstProvenance.UnverifiedOrUntrusted(
                rawInput = commandText,
                firewallRejectionReason = "Empty command input"
            )
        }

        // 1. Static Denylist Scan (System Call Leaks & Shell Injections)
        val lowerCaseCommand = trimmed.lowercase(Locale.ROOT)
        val detectedTokens = DANGEROUS_TOKENS.filter { lowerCaseCommand.contains(it) }
        if (detectedTokens.isNotEmpty()) {
            return AstProvenance.UnverifiedOrUntrusted(
                rawInput = commandText,
                firewallRejectionReason = "Prohibited execution token or system-call escape detected (AT-SEC-11)",
                detectedDangerousTokens = detectedTokens
            )
        }

        // 2. Chained Multi-Statement / Pipe Boundary Enforcement
        if (containsUnsafeChaining(trimmed)) {
            return AstProvenance.UnverifiedOrUntrusted(
                rawInput = commandText,
                firewallRejectionReason = "Ambiguous or multi-statement destructive payload detected; chaining prohibited in preview"
            )
        }

        // 3. Protected Governance Target Mutation Check
        for (target in PROTECTED_TARGETS) {
            if (lowerCaseCommand.contains(target) && (lowerCaseCommand.contains("write") || lowerCaseCommand.contains("rm") || lowerCaseCommand.contains("del"))) {
                return AstProvenance.UnverifiedOrUntrusted(
                    rawInput = commandText,
                    firewallRejectionReason = "Attempted unauthorized mutation of immutable governance artifact: $target"
                )
            }
        }

        // 4. Deterministic Grammar & Allowlisted Slash Commands Parsing
        return parseAllowlistedCommand(trimmed)
    }

    private fun containsUnsafeChaining(cmd: String): Boolean {
        // Permit quoted semicolons or pipes, but reject bare top-level shell operators
        val bareOperators = listOf(";", "&&", "||", "|", "`", "$(")
        var inSingleQuote = false
        var inDoubleQuote = false

        for (i in cmd.indices) {
            val char = cmd[i]
            if (char == '\'' && (i == 0 || cmd[i - 1] != '\\')) inSingleQuote = !inSingleQuote
            if (char == '"' && (i == 0 || cmd[i - 1] != '\\')) inDoubleQuote = !inDoubleQuote

            if (!inSingleQuote && !inDoubleQuote) {
                for (op in bareOperators) {
                    if (cmd.regionMatches(i, op, 0, op.length)) {
                        return true
                    }
                }
            }
        }
        return false
    }

    private fun parseAllowlistedCommand(cmd: String): AstProvenance {
        val parts = cmd.split("\\s+".toRegex()).filter { it.isNotEmpty() }
        if (parts.isEmpty()) {
            return AstProvenance.UnverifiedOrUntrusted(cmd, "Malformed syntax")
        }

        val primary = parts[0].lowercase(Locale.ROOT)

        return when (primary) {
            "/ignite", "ignite" -> {
                AstProvenance.VerifiedKernelAst(
                    toolName = "ignite",
                    targetResource = "substrate.crsm.11d",
                    riskLevel = RiskLevel.LOW,
                    modifiesState = false,
                    description = "Start the OSIRIS substrate session; reports component status and design-parameter version only"
                )
            }

            "/learn", "learn" -> {
                val generations = parts.getOrNull(1) ?: "10"
                val n = generations.toIntOrNull()
                if (n == null || n <= 0 || n > 1000) {
                    AstProvenance.UnverifiedOrUntrusted(
                        rawInput = cmd,
                        firewallRejectionReason = "Invalid generation count for /learn: '$generations' (must be 1..1000)"
                    )
                } else {
                    AstProvenance.VerifiedKernelAst(
                        toolName = "learn",
                        targetResource = "substrate.grn.autopoiesis",
                        riskLevel = RiskLevel.LOW,
                        modifiesState = true,
                        parameters = mapOf("generations" to n.toString()),
                        description = "Run $n generations of zero-backprop autopoietic evolution (no Γ gate until Γ has one registered definition)"
                    )
                }
            }

            "/dna", "dna" -> {
                val intent = if (parts.size > 1) {
                    cmd.substring(cmd.indexOf(parts[1]))
                } else {
                    ""
                }
                if (intent.isBlank()) {
                    AstProvenance.UnverifiedOrUntrusted(cmd, "Empty intent specification for /dna")
                } else {
                    // Stripping outer quotes if present
                    val cleanIntent = intent.removeSurrounding("\"").removeSurrounding("'")
                    AstProvenance.VerifiedKernelAst(
                        toolName = "dna",
                        targetResource = "substrate.dna_lang.genome",
                        riskLevel = RiskLevel.MODERATE,
                        modifiesState = true,
                        parameters = mapOf("intent" to cleanIntent),
                        description = "Vectorize intent to H_8 manifold via Z3bra Intent Lock and synthesize candidate .dna genome"
                    )
                }
            }

            "/ledger", "ledger" -> {
                AstProvenance.VerifiedKernelAst(
                    toolName = "ledger",
                    targetResource = "substrate.evidence.ledger",
                    riskLevel = RiskLevel.LOW,
                    modifiesState = false,
                    description = "Verify SHA-256 Dynamic Evidence Ledger audit trail and Merkle root provenance"
                )
            }

            "/status", "status" -> {
                AstProvenance.VerifiedKernelAst(
                    toolName = "status",
                    targetResource = "substrate.runtime.policy",
                    riskLevel = RiskLevel.LOW,
                    modifiesState = false,
                    description = "Display honest runtime policy, dual-substrate mesh status, and OCCR authority limits"
                )
            }

            "/sim" -> {
                val ticks = parts.getOrNull(1)?.toIntOrNull() ?: 50
                AstProvenance.VerifiedKernelAst(
                    toolName = "sim",
                    targetResource = "alife.organism_sim",
                    riskLevel = RiskLevel.LOW,
                    modifiesState = true,
                    parameters = mapOf("ticks" to ticks.toString()),
                    description = "Step local ALife simulation for $ticks ticks"
                )
            }

            else -> {
                AstProvenance.UnverifiedOrUntrusted(
                    rawInput = cmd,
                    firewallRejectionReason = "Unregistered tool directive; only allowlisted OSIRIS primitives permitted in TCB preview"
                )
            }
        }
    }
}

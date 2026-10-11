package ai.osiris.android.security

import java.security.MessageDigest

/**
 * Capability execution request from an agent or caller.
 */
data class CapabilityRequest(
    val subject: String,
    val action: String,
    val target: String,
    val requestedScope: String,
    val payloadDigest: String, // 64-char lowercase hex SHA-256 of immutable payload
    val justification: String? = null
)

/**
 * Outcome of the capability authorization evaluation.
 */
sealed interface CapabilityDecision {
    data class Granted(
        val grantId: String,               // e.g. "GRANT-W8L-002"
        val authorizationToken: String,
        val grantedScope: String,
        val boundPayloadDigest: String,    // Cryptographically binds grant to payload (SYS-021)
        val validUntil: Long,              // UTC epoch millis
        val policyVersion: String = "policy.json:v3"
    ) : CapabilityDecision

    data class Blocked(
        val gateId: String,                // e.g. "GATE_R11", "GATE_R15"
        val reason: String,
        val remediationInstructions: String
    ) : CapabilityDecision

    data class Denied(
        val reason: String
    ) : CapabilityDecision
}

/**
 * Enforces the SYS-021 Fail-Closed Capability Authorization Invariant.
 *
 * Invariant: Every capability grant is cryptographically bound to the SHA-256 digest
 * of the execution payload (H_payload). Any byte modification between proposal,
 * authorization, and execution causes immediate grant invalidation (ERR_PAYLOAD_MISMATCH).
 */
class OsirisCapabilityVerifier {

    companion object {
        fun computeSha256(bytes: ByteArray): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
            return digest.joinToString("") { "%02x".format(it) }
        }
    }

    /**
     * Verifies execution preconditions prior to substrate dispatch.
     *
     * @param decision The granted capability token.
     * @param actualPayloadBytes The actual raw execution payload bytes presented at dispatch time.
     * @param currentTimeMillis Current wall-clock time in UTC milliseconds.
     * @return Result.success if valid; Result.failure with SecurityException if expired or payload mismatched.
     */
    fun verifyExecutionPreconditions(
        decision: CapabilityDecision.Granted,
        actualPayloadBytes: ByteArray,
        currentTimeMillis: Long
    ): Result<Unit> {
        // 1. Expiration check
        if (currentTimeMillis > decision.validUntil) {
            return Result.failure(
                SecurityException("ERR_GRANT_EXPIRED: Authorization grant '${decision.grantId}' expired at ${decision.validUntil} (current: $currentTimeMillis)")
            )
        }

        // 2. Cryptographic payload-grant binding check (SYS-021)
        val actualDigest = computeSha256(actualPayloadBytes)
        if (!actualDigest.equals(decision.boundPayloadDigest, ignoreCase = true)) {
            return Result.failure(
                SecurityException(
                    "ERR_PAYLOAD_MISMATCH (SYS-021 VIOLATION): Execution payload digest ($actualDigest) does not match authorized grant digest (${decision.boundPayloadDigest})"
                )
            )
        }

        return Result.success(Unit)
    }
}

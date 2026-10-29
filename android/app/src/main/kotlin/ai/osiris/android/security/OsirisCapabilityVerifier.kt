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
        val reason: String,
        val errorCode: String = "ERR_DENIED"
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
        const val ERR_PAYLOAD_MISMATCH = "ERR_PAYLOAD_MISMATCH"
        const val ERR_GRANT_EXPIRED = "ERR_GRANT_EXPIRED"
        const val ERR_GRANT_REVOKED = "ERR_GRANT_REVOKED"
        const val MAX_TTL_MS = 5 * 60 * 1000L

        fun computeSha256(bytes: ByteArray): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
            return digest.joinToString("") { "%02x".format(it) }
        }
    }

    private val revokedPayloadDigests = mutableSetOf<String>()

    fun revokeGrant(payloadDigest: String) {
        revokedPayloadDigests.add(payloadDigest.lowercase())
    }

    /**
     * Verifies execution preconditions prior to substrate dispatch.
     *
     * @param decision The granted capability token.
     * @param actualPayloadBytes The actual raw execution payload bytes presented at dispatch time.
     * @param currentTimeMillis Current wall-clock time in UTC milliseconds.
     * @return Result.success if valid; Result.failure with SecurityException if revoked, expired, or payload mismatched.
     */
    fun verifyExecutionPreconditions(
        decision: CapabilityDecision.Granted,
        actualPayloadBytes: ByteArray,
        currentTimeMillis: Long
    ): Result<Unit> {
        val actualDigest = computeSha256(actualPayloadBytes)

        // 0. Revocation check (F-4)
        if (decision.boundPayloadDigest.lowercase() in revokedPayloadDigests || actualDigest.lowercase() in revokedPayloadDigests) {
            return Result.failure(
                SecurityException("$ERR_GRANT_REVOKED: Authorization grant '${decision.grantId}' for digest ${decision.boundPayloadDigest} has been revoked")
            )
        }

        // 1. Expiration check
        if (currentTimeMillis > decision.validUntil) {
            return Result.failure(
                SecurityException("$ERR_GRANT_EXPIRED: Authorization grant '${decision.grantId}' expired at ${decision.validUntil} (current: $currentTimeMillis)")
            )
        }

        // 2. Cryptographic payload-grant binding check (SYS-021)
        if (!actualDigest.equals(decision.boundPayloadDigest, ignoreCase = true)) {
            return Result.failure(
                SecurityException(
                    "$ERR_PAYLOAD_MISMATCH (SYS-021 VIOLATION): Execution payload digest ($actualDigest) does not match authorized grant digest (${decision.boundPayloadDigest})"
                )
            )
        }

        return Result.success(Unit)
    }
}

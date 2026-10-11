package ai.osiris.android.security

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class OsirisCapabilityVerifierTest {

    private lateinit var verifier: OsirisCapabilityVerifier

    @Before
    fun setUp() {
        verifier = OsirisCapabilityVerifier()
    }

    @Test
    fun testValidPayloadMatchesDigest() {
        val payload = "quantum-circuit-telemetry-payload".toByteArray(Charsets.UTF_8)
        val digest = OsirisCapabilityVerifier.computeSha256(payload)
        val validUntil = System.currentTimeMillis() + 300_000L // 300s TTL

        val grant = CapabilityDecision.Granted(
            grantId = "GRANT-W8L-002",
            authorizationToken = "auth-token-xyz",
            grantedScope = "qpu.execute",
            boundPayloadDigest = digest,
            validUntil = validUntil
        )

        val result = verifier.verifyExecutionPreconditions(grant, payload, System.currentTimeMillis())
        assertTrue(result.isSuccess)
    }

    @Test
    fun testPayloadMismatchTriggersSys021Violation() {
        val originalPayload = "quantum-circuit-telemetry-payload".toByteArray(Charsets.UTF_8)
        val tamperedPayload = "quantum-circuit-telemetry-payload-tampered".toByteArray(Charsets.UTF_8)
        val digest = OsirisCapabilityVerifier.computeSha256(originalPayload)
        val validUntil = System.currentTimeMillis() + 300_000L

        val grant = CapabilityDecision.Granted(
            grantId = "GRANT-W8L-002",
            authorizationToken = "auth-token-xyz",
            grantedScope = "qpu.execute",
            boundPayloadDigest = digest,
            validUntil = validUntil
        )

        val result = verifier.verifyExecutionPreconditions(grant, tamperedPayload, System.currentTimeMillis())
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()!!.message!!.contains("ERR_PAYLOAD_MISMATCH"))
        assertTrue(result.exceptionOrNull()!!.message!!.contains("SYS-021 VIOLATION"))
    }

    @Test
    fun testExpiredGrantRejected() {
        val payload = "payload".toByteArray(Charsets.UTF_8)
        val digest = OsirisCapabilityVerifier.computeSha256(payload)
        val expiredTime = 1000L
        val currentTime = 2000L

        val grant = CapabilityDecision.Granted(
            grantId = "GRANT-EXPIRED",
            authorizationToken = "token",
            grantedScope = "scope",
            boundPayloadDigest = digest,
            validUntil = expiredTime
        )

        val result = verifier.verifyExecutionPreconditions(grant, payload, currentTime)
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()!!.message!!.contains("ERR_GRANT_EXPIRED"))
    }
}

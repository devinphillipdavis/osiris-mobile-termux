package ai.osiris.android.substrate

import ai.osiris.android.security.CapabilityDecision
import ai.osiris.android.security.OsirisCapabilityVerifier
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

/**
 * Execution dispatch response from the local Termux runtime.
 */
data class SubstrateExecutionResponse(
    val status: String,
    val exitCode: Int,
    val stdout: String = "",
    val stderr: String = "",
    val durationSeconds: Double = 0.0
)

/**
 * Node Alpha (Google Pixel Fold Mobile Edge) Substrate Bridge.
 *
 * Enforces the physical substrate invariants:
 * 1. Strict 300.0s thermal/temporal horizon ceiling.
 * 2. Terminal prompt contract: "osiris::}{> ".
 * 3. Loopback IPC over 127.0.0.1:8000 or Unix Domain Socket with local token authentication.
 * 4. Pre-dispatch verification of SYS-021 payload-grant binding.
 */
class NodeAlphaSubstrateBridge(
    private val loopbackUrl: String = "http://127.0.0.1:8000",
    private val capabilityVerifier: OsirisCapabilityVerifier = OsirisCapabilityVerifier()
) {

    companion object {
        const val THERMAL_HORIZON_SECONDS = 300.0
        const val PROMPT_CONTRACT = "osiris::}{> "
        const val MAX_OPERATING_TEMP_CELSIUS = 42.0
    }

    /**
     * Dispatches an authorized workload payload to the local Termux execution daemon.
     */
    fun dispatchLocalExecution(
        payload: ByteArray,
        grant: CapabilityDecision.Granted,
        currentDeviceTempCelsius: Double = 35.0
    ): Result<SubstrateExecutionResponse> {
        // 1. Thermal ceiling check (AT-IME-09)
        if (currentDeviceTempCelsius > MAX_OPERATING_TEMP_CELSIUS) {
            return Result.failure(
                IllegalStateException("Thermal throttling lock: device temperature (${currentDeviceTempCelsius}°C) exceeds $MAX_OPERATING_TEMP_CELSIUS°C ceiling")
            )
        }

        // 2. Cryptographic payload-grant binding verification (SYS-021)
        val verifyResult = capabilityVerifier.verifyExecutionPreconditions(
            decision = grant,
            actualPayloadBytes = payload,
            currentTimeMillis = System.currentTimeMillis()
        )
        if (verifyResult.isFailure) {
            return Result.failure(verifyResult.exceptionOrNull()!!)
        }

        // 3. Dispatch to local Termux daemon over loopback
        return try {
            val response = executeOverLoopback(payload, grant.authorizationToken, THERMAL_HORIZON_SECONDS)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun executeOverLoopback(
        payload: ByteArray,
        authToken: String,
        timeoutSeconds: Double
    ): SubstrateExecutionResponse {
        val startTime = System.currentTimeMillis()
        val url = URL("$loopbackUrl/v1/execute")
        val conn = url.openConnection() as HttpURLConnection

        conn.requestMethod = "POST"
        conn.connectTimeout = 5000
        conn.readTimeout = (timeoutSeconds * 1000).toInt()
        conn.doOutput = true
        conn.setRequestProperty("Authorization", "Bearer $authToken")
        conn.setRequestProperty("Content-Type", "application/octet-stream")
        conn.setRequestProperty("X-Osiris-Prompt-Contract", PROMPT_CONTRACT)

        conn.outputStream.use { os ->
            os.write(payload)
            os.flush()
        }

        val responseCode = conn.responseCode
        val elapsed = (System.currentTimeMillis() - startTime) / 1000.0

        val (stdout, stderr) = if (responseCode == HttpURLConnection.HTTP_OK) {
            val out = conn.inputStream.bufferedReader(StandardCharsets.UTF_8).use { it.readText() }
            Pair(out, "")
        } else {
            val err = conn.errorStream?.bufferedReader(StandardCharsets.UTF_8)?.use { it.readText() } ?: "HTTP $responseCode"
            Pair("", err)
        }

        return SubstrateExecutionResponse(
            status = if (responseCode == HttpURLConnection.HTTP_OK) "SUCCESS" else "FAILED",
            exitCode = if (responseCode == HttpURLConnection.HTTP_OK) 0 else responseCode,
            stdout = stdout,
            stderr = stderr,
            durationSeconds = elapsed
        )
    }
}

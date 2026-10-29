package ai.osiris.android.ipc

import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

data class IntentRequest(
    val taskId: String,
    val action: String,
    val payload: String
)

class NodeAlphaIpcAdapter(private val betaEndpoint: String = "http://127.0.0.1:8080/sync") {

    fun sendTask(request: IntentRequest): String {
        val payloadDigest = calculateSha256(request.payload)
        
        val jsonPayload = JSONObject().apply {
            put("task_id", request.taskId)
            put("action", request.action)
            put("payload_sha256", payloadDigest)
            put("timestamp", System.currentTimeMillis() / 1000)
        }

        try {
            val url = URL(betaEndpoint)
            val connection = url.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.setRequestProperty("Content-Type", "application/json; utf-8")
            connection.setRequestProperty("Accept", "application/json")
            connection.doOutput = true

            OutputStreamWriter(connection.outputStream).use { writer ->
                writer.write(jsonPayload.toString())
                writer.flush()
            }

            val responseCode = connection.responseCode
            val responseText = if (responseCode in 200..299) {
                connection.inputStream.bufferedReader().use { it.readText() }
            } else {
                connection.errorStream?.bufferedReader()?.use { it.readText() } ?: "Unknown Error"
            }
            
            return responseText

        } catch (e: Exception) {
            return "{\"error\": \"Connection failed. Target reported as pending or unknown. Fail-closed.\"}"
        }
    }

    private fun calculateSha256(input: String): String {
        val bytes = input.toByteArray()
        val md = MessageDigest.getInstance("SHA-256")
        val digest = md.digest(bytes)
        return digest.joinToString("") { "%02x".format(it) }
    }
}

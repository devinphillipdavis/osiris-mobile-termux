package ai.osiris.android.ipc

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest

class NodeAlphaIpcAdapterTest {

    @Test
    fun `disconnect handles fail closed`() {
        // Use an invalid port to simulate disconnected transport
        val adapter = NodeAlphaIpcAdapter(betaEndpoint = "http://127.0.0.1:1")
        val request = IntentRequest(
            taskId = "tsk_0001",
            action = "health.check",
            payload = "ping"
        )
        
        val response = adapter.sendTask(request)
        assertTrue("Expected connection failure to fail-closed safely", response.contains("Fail-closed"))
    }
}

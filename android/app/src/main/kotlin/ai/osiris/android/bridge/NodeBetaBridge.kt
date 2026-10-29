package ai.osiris.android.bridge

import ai.osiris.android.task.OsirisTask
import ai.osiris.android.task.TaskStatus
import ai.osiris.android.task.TaskSubmissionReceipt
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.atomic.AtomicLong

enum class NodeBetaConnectionState {
    DISCONNECTED,
    CONNECTING,
    LOCAL_CONNECTED,
    RELAY_CONNECTED
}

interface NodeBetaBridge {
    val connectionState: StateFlow<NodeBetaConnectionState>
    fun setConnectionMode(mode: NodeBetaConnectionState)
    fun submitTask(task: OsirisTask): TaskSubmissionReceipt
    fun updateTaskProgress(taskId: String, status: TaskStatus, message: String?)
    fun pingNodeBeta(): Boolean
    fun dispatchTask(task: OsirisTask): RemoteDispatchResult
}

class HybridNodeBetaBridge(
    private val operatorIdentity: String = "Devin Phillip Davis"
) : NodeBetaBridge {

    private val _connectionState = MutableStateFlow(NodeBetaConnectionState.LOCAL_CONNECTED)
    override val connectionState: StateFlow<NodeBetaConnectionState> = _connectionState.asStateFlow()

    private val sequenceCounter = AtomicLong(100L)
    private val submittedTasks = mutableMapOf<String, OsirisTask>()

    override fun setConnectionMode(mode: NodeBetaConnectionState) {
        _connectionState.value = mode
    }

    override fun submitTask(task: OsirisTask): TaskSubmissionReceipt {
        val payloadDigest = OsirisTask.calculatePayloadSha256(task.rawPayload)
        val seq = sequenceCounter.incrementAndGet()
        val receipt = TaskSubmissionReceipt.create(
            operatorIdentity = operatorIdentity,
            payloadDigest = payloadDigest,
            sequenceIndex = seq
        )
        
        submittedTasks[task.id] = task.copy(
            status = TaskStatus.SUBMITTED_TO_BETA,
            receipt = receipt
        )
        return receipt
    }

    override fun updateTaskProgress(taskId: String, status: TaskStatus, message: String?) {
        val existing = submittedTasks[taskId] ?: return
        submittedTasks[taskId] = existing.copy(
            status = status,
            statusMessage = message
        )
    }

    override fun pingNodeBeta(): Boolean {
        return _connectionState.value == NodeBetaConnectionState.LOCAL_CONNECTED ||
               _connectionState.value == NodeBetaConnectionState.RELAY_CONNECTED
    }

    fun checkLiveHealth(): Boolean {
        return try {
            val url = java.net.URL("$nodeBetaBaseUrl/health")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 1500
            conn.readTimeout = 1500
            val isOk = conn.responseCode == 200
            if (isOk && _connectionState.value == NodeBetaConnectionState.DISCONNECTED) {
                _connectionState.value = NodeBetaConnectionState.LOCAL_CONNECTED
            }
            isOk
        } catch (e: Exception) {
            false
        }
    }

    override fun dispatchTask(task: OsirisTask): RemoteDispatchResult = dispatchToRemoteServer(task)

    fun getTask(taskId: String): OsirisTask? = submittedTasks[taskId]

    var nodeBetaBaseUrl: String = "http://127.0.0.1:8765"

    fun dispatchToRemoteServer(task: OsirisTask): RemoteDispatchResult {
        return try {
            val url = java.net.URL("$nodeBetaBaseUrl/tasks")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.connectTimeout = 3000
            conn.readTimeout = 5000
            conn.doOutput = true

            val receiptJson = org.json.JSONObject().apply {
                put("operatorIdentity", task.receipt?.operatorIdentity ?: operatorIdentity)
                put("payloadDigest", task.receipt?.payloadDigest ?: OsirisTask.calculatePayloadSha256(task.rawPayload))
                put("sequenceIndex", task.receipt?.sequenceIndex ?: 100L)
                put("receiptHash", task.receipt?.receiptHash ?: "")
            }

            val payloadJson = org.json.JSONObject().apply {
                put("id", task.id)
                put("rawPayload", task.rawPayload)
                put("command", task.command)
                put("source", task.source.name)
                put("receipt", receiptJson)
            }

            conn.outputStream.use { os ->
                os.write(payloadJson.toString().toByteArray())
            }

            val responseCode = conn.responseCode
            if (responseCode == 200) {
                val respText = conn.inputStream.bufferedReader().use { it.readText() }
                val respJson = org.json.JSONObject(respText)
                val resultText = respJson.optString("result", "Execution complete")
                val execHash = respJson.optString("executionHash", "")
                val root = respJson.optString("ledgerRoot", "")
                updateTaskProgress(task.id, TaskStatus.COMPLETED, resultText)
                RemoteDispatchResult.Success(resultText, execHash, root)
            } else {
                val errorText = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $responseCode"
                updateTaskProgress(task.id, TaskStatus.FAILED, errorText)
                RemoteDispatchResult.Error(responseCode, errorText)
            }
        } catch (e: Exception) {
            // Offline fallback / network loss: if task was already submitted or running, transition to AWAITING_RECONNECT; otherwise QUEUED
            val isSubmitted = task.status == TaskStatus.SUBMITTED_TO_BETA || task.status == TaskStatus.RUNNING
            val nextState = if (isSubmitted) TaskStatus.AWAITING_RECONNECT else TaskStatus.QUEUED
            val fallbackMsg = "Node Beta unreachable (${e.message}). State: ${nextState.name}"
            val existing = submittedTasks[task.id]
            if (existing != null) {
                updateTaskProgress(task.id, nextState, fallbackMsg)
            } else {
                submittedTasks[task.id] = task.copy(status = nextState, statusMessage = fallbackMsg)
            }
            RemoteDispatchResult.OfflineFallback(fallbackMsg, nextState)
        }
    }
}

sealed interface RemoteDispatchResult {
    data class Success(val resultText: String, val executionHash: String, val ledgerRoot: String) : RemoteDispatchResult
    data class OfflineFallback(val message: String, val targetState: TaskStatus = TaskStatus.AWAITING_RECONNECT) : RemoteDispatchResult
    data class Error(val code: Int, val errorText: String) : RemoteDispatchResult
}


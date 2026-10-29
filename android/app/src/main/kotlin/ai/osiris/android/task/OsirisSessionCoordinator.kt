package ai.osiris.android.task

import ai.osiris.android.bridge.HybridNodeBetaBridge
import ai.osiris.android.bridge.NodeBetaBridge
import ai.osiris.android.bridge.RemoteDispatchResult
import ai.osiris.android.evidence.EvidenceLedger
import ai.osiris.android.ime.ActionPreviewResult
import ai.osiris.android.ime.AstProvenance
import ai.osiris.android.ime.IntentPreviewFirewall
import ai.osiris.android.ime.IntentPreviewFirewallImpl
import ai.osiris.android.notification.OsirisNotificationManager
import ai.osiris.android.voice.OsirisSpeechSynthesizer
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface TaskSubmissionResult {
    data class Success(val task: OsirisTask) : TaskSubmissionResult
    data class Blocked(val reason: String, val violatingAst: AstProvenance) : TaskSubmissionResult
}

class OsirisSessionCoordinator(
    val firewall: IntentPreviewFirewall = IntentPreviewFirewallImpl(),
    val ledger: EvidenceLedger = EvidenceLedger(),
    val bridge: NodeBetaBridge = HybridNodeBetaBridge(),
    var notificationManager: OsirisNotificationManager? = null,
    var speechSynthesizer: OsirisSpeechSynthesizer? = null,
    private val coordinatorScope: CoroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
) {
    companion object {
        val instance: OsirisSessionCoordinator by lazy { OsirisSessionCoordinator() }
    }

    private val _tasks = MutableStateFlow<List<OsirisTask>>(emptyList())
    val tasks: StateFlow<List<OsirisTask>> = _tasks.asStateFlow()

    fun attachContext(context: Context) {
        if (notificationManager == null) {
            try {
                notificationManager = OsirisNotificationManager(context.applicationContext)
            } catch (_: Throwable) {
                // Non-fatal fallback for test/headless environments
            }
        }
        if (speechSynthesizer == null) {
            try {
                speechSynthesizer = OsirisSpeechSynthesizer(context.applicationContext)
            } catch (_: Throwable) {
                // Non-fatal fallback for test/headless environments
            }
        }
    }

    fun submitIntent(
        rawPayload: String,
        source: TaskSource,
        context: Context? = null
    ): TaskSubmissionResult {
        if (context != null) {
            attachContext(context)
        }

        val payloadDigest = OsirisTask.calculatePayloadSha256(rawPayload)
        
        // 1. CIL L0 AST Firewall Interposition
        val validationResult = firewall.parseAndValidateIntent(rawPayload, context)

        return when (validationResult) {
            is ActionPreviewResult.Rejected -> {
                // Record refusal incident to immutable ledger
                ledger.appendEvent(
                    actor = "NodeAlpha:$source",
                    action = "CIL_INTERCEPTION_BLOCKED",
                    target = rawPayload.take(64),
                    payloadDigest = payloadDigest,
                    decision = "REJECTED: ${validationResult.reason}"
                )

                val rejectedTask = OsirisTask(
                    source = source,
                    rawPayload = rawPayload,
                    command = rawPayload.split(" ").firstOrNull() ?: rawPayload,
                    status = TaskStatus.REJECTED,
                    statusMessage = validationResult.reason,
                    evidenceDigest = ledger.getLedgerRoot()
                )
                _tasks.value = listOf(rejectedTask) + _tasks.value

                // Trigger sovereign security notifications & audio alert
                notificationManager?.postFirewallRejectionAlert(validationResult.reason, rawPayload)
                speechSynthesizer?.speakAlert("OSIRIS Security: Intent rejected by firewall.", isPriority = true)

                TaskSubmissionResult.Blocked(validationResult.reason, validationResult.violatingAst)
            }

            is ActionPreviewResult.Allowed -> {
                // Record authorized grant to immutable ledger
                val ledgerEvent = ledger.appendEvent(
                    actor = "NodeAlpha:$source",
                    action = "INTENT_AUTHORIZED",
                    target = validationResult.targetUri,
                    payloadDigest = payloadDigest,
                    decision = "ALLOWED"
                )

                var task = OsirisTask(
                    source = source,
                    rawPayload = rawPayload,
                    command = validationResult.targetUri,
                    parameters = validationResult.parameters,
                    riskLevel = validationResult.risk,
                    status = TaskStatus.FIREWALL_VALIDATED,
                    statusMessage = "Validated by CIL Layer 0",
                    evidenceDigest = ledgerEvent.calculateHash()
                )

                // Dispatch to Node Beta Bridge
                val receipt = bridge.submitTask(task)
                task = task.copy(
                    status = TaskStatus.SUBMITTED_TO_BETA,
                    statusMessage = "Enqueued on Node Beta [Receipt: ${receipt.receiptHash.take(8)}...]",
                    receipt = receipt
                )

                _tasks.value = listOf(task) + _tasks.value

                // Asynchronous execution dispatch to Node Beta
                val taskToDispatch = task
                coordinatorScope.launch {
                    when (val dispatchResult = bridge.dispatchTask(taskToDispatch)) {
                        is RemoteDispatchResult.Success -> {
                            markTaskCompleted(taskToDispatch.id, dispatchResult.resultText)
                        }
                        is RemoteDispatchResult.OfflineFallback -> {
                            updateTaskStatus(taskToDispatch.id, dispatchResult.targetState, dispatchResult.message)
                        }
                        is RemoteDispatchResult.Error -> {
                            updateTaskStatus(taskToDispatch.id, TaskStatus.FAILED, "Dispatch Error (${dispatchResult.code}): ${dispatchResult.errorText}")
                        }
                    }
                }

                TaskSubmissionResult.Success(task)
            }
        }
    }

    fun markTaskCompleted(taskId: String, completionMessage: String = "Execution complete") {
        bridge.updateTaskProgress(taskId, TaskStatus.COMPLETED, completionMessage)
        var completedTask: OsirisTask? = null
        _tasks.value = _tasks.value.map { task ->
            if (task.id == taskId) {
                val updated = task.copy(
                    status = TaskStatus.COMPLETED,
                    statusMessage = completionMessage
                )
                completedTask = updated
                updated
            } else {
                task
            }
        }
        completedTask?.let { task ->
            notificationManager?.postTaskCompletedNotification(task)
            speechSynthesizer?.speakAlert("OSIRIS task ${task.command} completed.")
        }
    }

    fun updateTaskStatus(taskId: String, status: TaskStatus, message: String) {
        bridge.updateTaskProgress(taskId, status, message)
        _tasks.value = _tasks.value.map { task ->
            if (task.id == taskId) {
                task.copy(
                    status = status,
                    statusMessage = message
                )
            } else {
                task
            }
        }
    }

    fun getActiveTasks(): List<OsirisTask> {
        return _tasks.value.filter {
            it.status in listOf(TaskStatus.QUEUED, TaskStatus.SUBMITTED_TO_BETA, TaskStatus.RUNNING, TaskStatus.AWAITING_RECONNECT)
        }
    }

    fun clearHistory() {
        _tasks.value = emptyList()
    }
}

package ai.osiris.android.task

import ai.osiris.android.ime.IntentRiskLevel
import java.security.MessageDigest
import java.util.UUID

enum class TaskSource {
    KEYBOARD,
    SHARE_SHEET,
    CONTACT_CARD,
    QUICK_SETTINGS,
    VOICE,
    REMOTE_RELAY
}

enum class TaskStatus {
    PROPOSED,
    FIREWALL_VALIDATED,
    QUEUED,
    SUBMITTED_TO_BETA,
    RUNNING,
    AWAITING_RECONNECT,
    COMPLETED,
    FAILED,
    REJECTED
}

data class TaskSubmissionReceipt(
    val operatorIdentity: String,
    val payloadDigest: String,
    val sequenceIndex: Long,
    val timestamp: Long,
    val receiptHash: String
) {
    companion object {
        fun create(
            operatorIdentity: String,
            payloadDigest: String,
            sequenceIndex: Long,
            timestamp: Long = System.currentTimeMillis()
        ): TaskSubmissionReceipt {
            val raw = "$operatorIdentity|$payloadDigest|$sequenceIndex|$timestamp"
            val md = MessageDigest.getInstance("SHA-256")
            val hash = md.digest(raw.toByteArray()).joinToString("") { "%02x".format(it) }
            return TaskSubmissionReceipt(
                operatorIdentity = operatorIdentity,
                payloadDigest = payloadDigest,
                sequenceIndex = sequenceIndex,
                timestamp = timestamp,
                receiptHash = hash
            )
        }
    }
}

data class OsirisTask(
    val id: String = UUID.randomUUID().toString(),
    val timestamp: Long = System.currentTimeMillis(),
    val source: TaskSource,
    val rawPayload: String,
    val command: String,
    val parameters: Map<String, String> = emptyMap(),
    val riskLevel: IntentRiskLevel = IntentRiskLevel.SAFE,
    val status: TaskStatus = TaskStatus.PROPOSED,
    val statusMessage: String? = null,
    val evidenceDigest: String = "",
    val targetDevice: String = "NODE_BETA_LOCAL",
    val receipt: TaskSubmissionReceipt? = null
) {
    companion object {
        fun calculatePayloadSha256(payload: String): String {
            val md = MessageDigest.getInstance("SHA-256")
            val digest = md.digest(payload.toByteArray())
            return digest.joinToString("") { "%02x".format(it) }
        }
    }
}

package ai.osiris.android.bridge

import ai.osiris.android.task.OsirisTask
import ai.osiris.android.task.TaskSource
import ai.osiris.android.task.TaskStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.security.MessageDigest

class HybridNodeBetaBridgeTest {

    private lateinit var bridge: HybridNodeBetaBridge

    @Before
    fun setUp() {
        bridge = HybridNodeBetaBridge(operatorIdentity = "Devin Phillip Davis")
    }

    @Test
    fun `task submission produces valid cryptographic receipt satisfying SYS-021`() {
        val payload = "/dna XY4_Bell_Decouple.v1.dna"
        val expectedSha = MessageDigest.getInstance("SHA-256")
            .digest(payload.toByteArray())
            .joinToString("") { "%02x".format(it) }

        val task = OsirisTask(
            source = TaskSource.KEYBOARD,
            rawPayload = payload,
            command = "/dna"
        )

        val receipt = bridge.submitTask(task)
        assertNotNull(receipt)
        assertEquals("Devin Phillip Davis", receipt.operatorIdentity)
        assertEquals(expectedSha, receipt.payloadDigest)
        assertTrue(receipt.sequenceIndex > 0)
        assertTrue(receipt.receiptHash.isNotEmpty())

        // Verify task stored with updated state
        val stored = bridge.getTask(task.id)
        assertNotNull(stored)
        assertEquals(TaskStatus.SUBMITTED_TO_BETA, stored?.status)
    }

    @Test
    fun `progress updates are tracked accurately`() {
        val task = OsirisTask(
            source = TaskSource.SHARE_SHEET,
            rawPayload = "https://arxiv.org/abs/2401.00000",
            command = "ingest_paper"
        )
        bridge.submitTask(task)

        bridge.updateTaskProgress(task.id, TaskStatus.RUNNING, "Synthesizing AST...")
        val inFlight = bridge.getTask(task.id)
        assertEquals(TaskStatus.RUNNING, inFlight?.status)
        assertEquals("Synthesizing AST...", inFlight?.statusMessage)

        bridge.updateTaskProgress(task.id, TaskStatus.COMPLETED, "Vectorization indexed into GRN.")
        val finished = bridge.getTask(task.id)
        assertEquals(TaskStatus.COMPLETED, finished?.status)
        assertEquals("Vectorization indexed into GRN.", finished?.statusMessage)
    }

    @Test
    fun `in-flight task transitions to AWAITING_RECONNECT on network disconnect`() {
        val task = OsirisTask(
            source = TaskSource.KEYBOARD,
            rawPayload = "/run_heavy_sweep",
            command = "/run_heavy_sweep",
            status = TaskStatus.SUBMITTED_TO_BETA
        )
        bridge.nodeBetaBaseUrl = "http://127.0.0.1:9999" // Unreachable port to force disconnect
        val result = bridge.dispatchToRemoteServer(task)
        
        assertTrue(result is RemoteDispatchResult.OfflineFallback)
        val fallback = result as RemoteDispatchResult.OfflineFallback
        assertEquals(TaskStatus.AWAITING_RECONNECT, fallback.targetState)

        val stored = bridge.getTask(task.id)
        assertEquals(TaskStatus.AWAITING_RECONNECT, stored?.status)
        assertTrue(stored?.statusMessage?.contains("AWAITING_RECONNECT") == true)
    }

    @Test
    fun `unsubmitted task transitions to QUEUED on network disconnect`() {
        val task = OsirisTask(
            source = TaskSource.KEYBOARD,
            rawPayload = "/draft_experiment",
            command = "/draft_experiment",
            status = TaskStatus.PROPOSED
        )
        bridge.nodeBetaBaseUrl = "http://127.0.0.1:9999"
        val result = bridge.dispatchToRemoteServer(task)
        
        assertTrue(result is RemoteDispatchResult.OfflineFallback)
        val fallback = result as RemoteDispatchResult.OfflineFallback
        assertEquals(TaskStatus.QUEUED, fallback.targetState)

        val stored = bridge.getTask(task.id)
        assertEquals(TaskStatus.QUEUED, stored?.status)
    }
}

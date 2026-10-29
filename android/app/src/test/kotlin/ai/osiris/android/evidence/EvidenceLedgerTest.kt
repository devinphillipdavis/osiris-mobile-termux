package ai.osiris.android.evidence

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class EvidenceLedgerTest {

    private lateinit var ledger: EvidenceLedger

    @Before
    fun setUp() {
        ledger = DefaultEvidenceLedger()
    }

    @Test
    fun testAppendAndVerifyChain() {
        val rec1 = ledger.appendRecord(
            actor = "operator",
            action = "GRANT_ACTIVATED",
            target = "campaign.w8-2dlocal",
            payloadDigest = "08b8848b6d4ba6c0",
            decision = "APPROVED"
        )
        assertEquals(1L, rec1.sequenceNumber)
        assertEquals(DefaultEvidenceLedger.GENESIS_PREV_HASH, rec1.previousRecordHash)

        val rec2 = ledger.appendRecord(
            actor = "node-alpha",
            action = "SWEEP_COMPLETED",
            target = "qpu.circuits",
            payloadDigest = "053c00b291fb2d03",
            decision = "RECORDED"
        )
        assertEquals(2L, rec2.sequenceNumber)
        assertEquals(rec1.recordHash, rec2.previousRecordHash)

        val audit = ledger.verifyLedgerIntegrity()
        assertTrue(audit.isValid)
        assertEquals(2L, audit.lastVerifiedSequence)
        assertEquals(2, audit.recordCount)
        assertNotNull(audit.merkleRoot)
        assertEquals(64, audit.merkleRoot.length)
    }

    @Test
    fun testEmptyLedgerIntegrity() {
        val audit = ledger.verifyLedgerIntegrity()
        assertTrue(audit.isValid)
        assertEquals(0L, audit.lastVerifiedSequence)
        assertEquals(0, audit.recordCount)
    }

    @Test
    fun testLedgerEventChainProducesDistinctAndTamperSensitiveHashes() {
        val event1 = ledger.appendEvent(
            actor = "Devin Phillip Davis",
            action = "EXEC_DNA",
            target = "BellState.v1.dna",
            payloadDigest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            decision = "GRANTED"
        )
        val rootAfterFirst = ledger.getLedgerRoot()
        assertEquals(64, rootAfterFirst.length)

        val event2 = ledger.appendEvent(
            actor = "Devin Phillip Davis",
            action = "EXEC_SIM",
            target = "OrganismSim",
            payloadDigest = "a1b2c3d4",
            decision = "GRANTED"
        )
        val rootAfterSecond = ledger.getLedgerRoot()
        assertNotEquals(rootAfterFirst, rootAfterSecond)
        assertEquals(rootAfterFirst, event2.previousHash)

        val tampered = event2.copy(decision = "TAMPERED")
        assertNotEquals(event2.calculateHash(), tampered.calculateHash())
    }
}

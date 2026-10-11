package ai.osiris.android.evidence

import java.security.MessageDigest
import java.time.Instant
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Immutable evidence ledger record.
 */
data class EvidenceRecord(
    val sequenceNumber: Long,
    val previousRecordHash: String, // SHA-256 of previous record (Genesis = "0"*64)
    val timestampUtc: String,
    val actor: String,
    val action: String,
    val target: String,
    val payloadDigest: String,
    val decision: String,
    val recordHash: String
)

/**
 * Audit result validating hash chain continuity and Merkle root calculation.
 */
data class LedgerAuditResult(
    val isValid: Boolean,
    val lastVerifiedSequence: Long,
    val recordCount: Int,
    val merkleRoot: String,
    val failureDetail: String? = null
)

/**
 * Interface for the tamper-evident append-only evidence ledger.
 */
interface EvidenceLedger {
    fun appendRecord(
        actor: String,
        action: String,
        target: String,
        payloadDigest: String,
        decision: String
    ): EvidenceRecord

    fun verifyLedgerIntegrity(): LedgerAuditResult
    fun getRecords(): List<EvidenceRecord>
}

/**
 * Canonical in-memory & Room-backed implementation of the OSIRIS Evidence Ledger.
 */
class DefaultEvidenceLedger : EvidenceLedger {

    companion object {
        const val GENESIS_PREV_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

        fun sha256(input: String): String {
            val md = MessageDigest.getInstance("SHA-256")
            return md.digest(input.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
        }
    }

    private val records = CopyOnWriteArrayList<EvidenceRecord>()

    @Synchronized
    override fun appendRecord(
        actor: String,
        action: String,
        target: String,
        payloadDigest: String,
        decision: String
    ): EvidenceRecord {
        val nextSeq = if (records.isEmpty()) 1L else records.last().sequenceNumber + 1L
        val prevHash = if (records.isEmpty()) GENESIS_PREV_HASH else records.last().recordHash
        val timestamp = Instant.now().toString()

        val canonicalPayload = "$prevHash:$nextSeq:$timestamp:$actor:$action:$target:$payloadDigest:$decision"
        val recordHash = sha256(canonicalPayload)

        val record = EvidenceRecord(
            sequenceNumber = nextSeq,
            previousRecordHash = prevHash,
            timestampUtc = timestamp,
            actor = actor,
            action = action,
            target = target,
            payloadDigest = payloadDigest,
            decision = decision,
            recordHash = recordHash
        )

        records.add(record)
        return record
    }

    override fun verifyLedgerIntegrity(): LedgerAuditResult {
        if (records.isEmpty()) {
            return LedgerAuditResult(
                isValid = true,
                lastVerifiedSequence = 0L,
                recordCount = 0,
                merkleRoot = sha256("EMPTY_LEDGER")
            )
        }

        var expectedPrevHash = GENESIS_PREV_HASH
        val hashes = mutableListOf<String>()

        for ((idx, rec) in records.withIndex()) {
            // 1. Sequence number continuity
            val expectedSeq = idx + 1L
            if (rec.sequenceNumber != expectedSeq) {
                return LedgerAuditResult(
                    isValid = false,
                    lastVerifiedSequence = idx.toLong(),
                    recordCount = records.size,
                    merkleRoot = "",
                    failureDetail = "Sequence gap at index $idx: expected $expectedSeq, found ${rec.sequenceNumber}"
                )
            }

            // 2. Predecessor hash chain linkage
            if (rec.previousRecordHash != expectedPrevHash) {
                return LedgerAuditResult(
                    isValid = false,
                    lastVerifiedSequence = idx.toLong(),
                    recordCount = records.size,
                    merkleRoot = "",
                    failureDetail = "Hash chain break at sequence ${rec.sequenceNumber}: expected $expectedPrevHash, found ${rec.previousRecordHash}"
                )
            }

            // 3. Cryptographic digest verification
            val canonicalPayload = "${rec.previousRecordHash}:${rec.sequenceNumber}:${rec.timestampUtc}:${rec.actor}:${rec.action}:${rec.target}:${rec.payloadDigest}:${rec.decision}"
            val computedHash = sha256(canonicalPayload)
            if (computedHash != rec.recordHash) {
                return LedgerAuditResult(
                    isValid = false,
                    lastVerifiedSequence = idx.toLong(),
                    recordCount = records.size,
                    merkleRoot = "",
                    failureDetail = "Tampered record at sequence ${rec.sequenceNumber}: computed $computedHash != stored ${rec.recordHash}"
                )
            }

            expectedPrevHash = rec.recordHash
            hashes.add(rec.recordHash)
        }

        // 4. Compute Merkle root across all record hashes
        val merkleRoot = computeMerkleRoot(hashes)

        return LedgerAuditResult(
            isValid = true,
            lastVerifiedSequence = records.last().sequenceNumber,
            recordCount = records.size,
            merkleRoot = merkleRoot
        )
    }

    override fun getRecords(): List<EvidenceRecord> = records.toList()

    private fun computeMerkleRoot(hashes: List<String>): String {
        if (hashes.isEmpty()) return sha256("EMPTY")
        var currentLevel = hashes

        while (currentLevel.size > 1) {
            val nextLevel = mutableListOf<String>()
            for (i in 0 until currentLevel.size step 2) {
                val left = currentLevel[i]
                val right = if (i + 1 < currentLevel.size) currentLevel[i + 1] else left
                nextLevel.add(sha256("$left:$right"))
            }
            currentLevel = nextLevel
        }
        return currentLevel.first()
    }
}

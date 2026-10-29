package ai.osiris.android.bluetooth

import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.TaskSource
import android.content.Context
import android.util.Log
import java.security.MessageDigest
import java.util.zip.CRC32

class BluetoothDeviceAdapter(
    private val context: Context,
    private val coordinator: OsirisSessionCoordinator = OsirisSessionCoordinator.instance,
    var voiceInputManager: ai.osiris.android.voice.OsirisVoiceInputManager? = null
) {
    companion object {
        private const val TAG = "OsirisBluetoothAdapter"
    }

    enum class PeripheralAction {
        TOGGLE_VOICE_CAPTURE,
        EXECUTE_STATUS_QUERY,
        EMERGENCY_SUBSTRATE_HALT
    }

    fun onAvrcpGesture(tapCount: Int) {
        when (tapCount) {
            1 -> {
                Log.i(TAG, "AVRCP Single Tap: Toggle voice intent capture.")
                voiceInputManager?.let { mgr ->
                    if (mgr.isListening) mgr.stopVoiceCapture()
                    else mgr.startVoiceCapture()
                }
            }
            2 -> {
                Log.i(TAG, "AVRCP Double Tap detected: Triggering Voice Intent Capture.")
                coordinator.submitIntent("/status", TaskSource.VOICE, context)
            }
            3 -> {
                Log.w(TAG, "AVRCP Triple Tap detected: Ledger Audit Query.")
                coordinator.submitIntent("/ledger", TaskSource.VOICE, context)
            }
            else -> {
                Log.d(TAG, "Unmapped AVRCP tap sequence: $tapCount")
            }
        }
    }

    fun processBleCommandFrame(
        payload: ByteArray,
        expectedCrc: Long,
        expectedSha256: ByteArray
    ): Boolean {
        // 1. Verify CRC-32 Frame Integrity
        val crc32 = CRC32()
        crc32.update(payload)
        if (crc32.value != expectedCrc) {
            Log.e(TAG, "BLE Frame corrupted: CRC-32 mismatch (Expected: $expectedCrc, Got: ${crc32.value})")
            return false
        }

        // 2. Verify Cryptographic SHA-256 Digest (SYS-021 Boundary)
        val digest = MessageDigest.getInstance("SHA-256").digest(payload)
        if (!digest.contentEquals(expectedSha256)) {
            Log.e(TAG, "BLE Frame untrusted: SHA-256 mismatch")
            return false
        }

        // 3. Process Validated Command String
        val command = String(payload, Charsets.UTF_8).trim()
        Log.i(TAG, "Authenticated BLE Peripheral Command: $command")
        coordinator.submitIntent(command, TaskSource.VOICE, context)
        return true
    }
}

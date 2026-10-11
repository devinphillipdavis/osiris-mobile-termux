package ai.osiris.android.bluetooth

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Binder
import android.os.Build
import android.os.IBinder
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.zip.CRC32

/**
 * Foreground persistence service managing Bluetooth SCO 16kHz PCM audio streaming
 * and the DNA-Lang BLE Peripheral Protocol on Google Pixel Fold (Node Alpha).
 */
class BluetoothScoPersistenceService : Service() {

    companion object {
        const val CHANNEL_ID = "osiris_sco_peripheral_channel"
        const val NOTIFICATION_ID = 42091

        // DNA-Lang BLE Peripheral Protocol Constants
        val OSIRIS_BLE_SERVICE_UUID: UUID = UUID.fromString("00001000-0000-1000-8000-00805f9b34fb")
        const val BLE_FRAME_CHUNK_SIZE_BYTES = 128

        // Audio Constants
        const val SAMPLE_RATE_HZ = 16000
        const val AUDIO_CHANNEL = AudioFormat.CHANNEL_IN_MONO
        const val AUDIO_ENCODING = AudioFormat.ENCODING_PCM_16BIT
        const val BUFFER_FRAME_COUNT = 2048
    }

    private val binder = LocalBinder()
    private val isRecording = AtomicBoolean(false)
    private val isScoConnected = AtomicBoolean(false)
    private val isBleConnected = AtomicBoolean(false)

    private var audioManager: AudioManager? = null
    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null

    // In-memory bounded frame queue for offline STT inference (zero cloud transmission)
    val audioFrameQueue = ConcurrentLinkedQueue<ByteArray>()

    // Event listeners for AVRCP hardware buttons and BLE framing
    var onVoiceCaptureTriggered: (() -> Unit)? = null
    var onLedgerCheckpointTriggered: (() -> Unit)? = null
    var onPeripheralDisconnectRollback: (() -> Unit)? = null

    private val scoReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val state = intent?.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, -1)
            when (state) {
                AudioManager.SCO_AUDIO_STATE_CONNECTED -> {
                    isScoConnected.set(true)
                    startPcmRecording()
                }
                AudioManager.SCO_AUDIO_STATE_DISCONNECTED -> {
                    isScoConnected.set(false)
                    stopPcmRecording()
                }
            }
        }
    }

    inner class LocalBinder : Binder() {
        fun getService(): BluetoothScoPersistenceService = this@BluetoothScoPersistenceService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        audioManager = getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        registerReceiver(scoReceiver, IntentFilter(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED))
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildForegroundNotification("OSIRIS Substrate: SCO & BLE Ready"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            "ACTION_START_SCO" -> enableBluetoothSco()
            "ACTION_STOP_SCO" -> disableBluetoothSco()
            "ACTION_AVRCP_DOUBLE_TAP" -> handleAvrcpDoubleTap()
            "ACTION_AVRCP_TRIPLE_TAP" -> handleAvrcpTripleTap()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        disableBluetoothSco()
        try {
            unregisterReceiver(scoReceiver)
        } catch (_: Exception) {}
        stopPcmRecording()
    }

    /**
     * Locks AudioManager into HFP/SCO mode.
     */
    fun enableBluetoothSco() {
        audioManager?.let { am ->
            am.isBluetoothScoOn = true
            am.startBluetoothSco()
        }
    }

    /**
     * Releases AudioManager SCO lock.
     */
    fun disableBluetoothSco() {
        audioManager?.let { am ->
            am.stopBluetoothSco()
            am.isBluetoothScoOn = false
        }
        isScoConnected.set(false)
        stopPcmRecording()
    }

    /**
     * Hardware button event: Double-tap initiates on-device voice AST capture.
     */
    fun handleAvrcpDoubleTap() {
        onVoiceCaptureTriggered?.invoke()
    }

    /**
     * Hardware button event: Triple-tap forces an immediate cryptographic ledger commit.
     */
    fun handleAvrcpTripleTap() {
        onLedgerCheckpointTriggered?.invoke()
    }

    /**
     * Starts synchronous 16kHz 16-bit PCM buffer capture.
     */
    @Synchronized
    private fun startPcmRecording() {
        if (isRecording.get()) return

        val minBufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE_HZ, AUDIO_CHANNEL, AUDIO_ENCODING)
        val bufferSize = maxOf(minBufferSize, 2048)

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE_HZ,
                AUDIO_CHANNEL,
                AUDIO_ENCODING,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                audioRecord?.release()
                audioRecord = null
                return
            }

            audioRecord?.startRecording()
            isRecording.set(true)

            recordingThread = Thread {
                val buffer = ByteArray(1024)
                while (isRecording.get()) {
                    val readBytes = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                    if (readBytes > 0) {
                        val frameCopy = buffer.copyOf(readBytes)
                        if (audioFrameQueue.size >= BUFFER_FRAME_COUNT) {
                            audioFrameQueue.poll() // Bounded ring buffer drop-head
                        }
                        audioFrameQueue.offer(frameCopy)
                    }
                }
            }.apply {
                name = "OsirisPcmAudioRecorder"
                start()
            }
        } catch (_: SecurityException) {
            isRecording.set(false)
        }
    }

    /**
     * Halts PCM recording and releases audio hardware.
     */
    @Synchronized
    private fun stopPcmRecording() {
        isRecording.set(false)
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (_: Exception) {}
        audioRecord = null
        recordingThread = null
    }

    /**
     * Validates and ingests a 128-byte chunked frame from a BLE quantum/cryptographic peripheral.
     */
    fun ingestBlePeripheralChunk(chunk: ByteArray, expectedCrc32: Long): Result<Unit> {
        if (chunk.size > BLE_FRAME_CHUNK_SIZE_BYTES) {
            return Result.failure(IllegalArgumentException("Frame chunk exceeds 128-byte protocol limit"))
        }

        val crc = CRC32()
        crc.update(chunk)
        if (crc.value != expectedCrc32) {
            return Result.failure(SecurityException("CRC-32 checksum mismatch on peripheral frame chunk"))
        }

        return Result.success(Unit)
    }

    /**
     * Handles unexpected BLE peripheral disconnection mid-synthesis.
     * Enforces the fail-closed policy: immediately flushes volatile buffers and rolls back.
     */
    fun onBlePeripheralDisconnected() {
        isBleConnected.set(false)
        audioFrameQueue.clear()
        onPeripheralDisconnectRollback?.invoke()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "OSIRIS Substrate Peripheral & Audio Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Maintains persistent SCO audio and BLE peripheral gateway for Node Alpha"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun buildForegroundNotification(contentText: String): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("OSIRIS Sovereign Edge (Node Alpha)")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .build()
    }
}

package ai.osiris.android.voice

import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.TaskSource
import ai.osiris.android.task.TaskSubmissionResult
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import java.util.Locale

class OsirisVoiceInputManager(
    private val context: Context,
    private val coordinator: OsirisSessionCoordinator = OsirisSessionCoordinator.instance
) {
    companion object {
        private const val TAG = "OsirisVoiceInput"
    }

    private var speechRecognizer: SpeechRecognizer? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    var isListening: Boolean = false
        private set
    var stagedTranscript: String? = null
        private set

    fun isAvailable(): Boolean {
        return SpeechRecognizer.isRecognitionAvailable(context)
    }

    /**
     * Stages a spoken transcript into an editable buffer without implicitly submitting it.
     */
    fun stageRecognizedSpeech(recognized: String): String? {
        val trimmed = recognized.trim()
        if (trimmed.isEmpty()) return null
        val command = mapSpokenTextToCommand(trimmed)
        stagedTranscript = command
        return command
    }

    /**
     * Explicitly confirms and submits the staged voice transcript ( optionally edited by the operator ).
     */
    fun confirmStagedIntent(overrideCommand: String? = null): TaskSubmissionResult? {
        val commandToSubmit = (overrideCommand ?: stagedTranscript)?.trim()
        stagedTranscript = null
        if (commandToSubmit.isNullOrEmpty()) return null
        return coordinator.submitIntent(commandToSubmit, TaskSource.VOICE, context)
    }

    fun discardStagedIntent() {
        stagedTranscript = null
    }

    fun startVoiceCapture(
        onStaged: ((String) -> Unit)? = null,
        onError: ((String) -> Unit)? = null
    ) {
        mainHandler.post {
            try {
                if (!isAvailable()) {
                    Log.w(TAG, "SpeechRecognizer service not available on this platform.")
                    onError?.invoke("Speech recognition service not available.")
                    return@post
                }

                speechRecognizer?.destroy()
                speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                    setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) {
                            Log.d(TAG, "Speech recognizer ready for input.")
                            isListening = true
                        }

                        override fun onBeginningOfSpeech() {
                            Log.d(TAG, "User started speaking.")
                        }

                        override fun onRmsChanged(rmsdB: Float) {}

                        override fun onBufferReceived(buffer: ByteArray?) {}

                        override fun onEndOfSpeech() {
                            Log.d(TAG, "User finished speaking.")
                            isListening = false
                        }

                        override fun onError(error: Int) {
                            isListening = false
                            val errorMsg = when (error) {
                                SpeechRecognizer.ERROR_NO_MATCH -> "No speech match recognized"
                                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Speech input timeout"
                                SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                                SpeechRecognizer.ERROR_NETWORK -> "Network error during speech recognition"
                                else -> "Speech recognition error code: $error"
                            }
                            Log.w(TAG, errorMsg)
                            onError?.invoke(errorMsg)
                        }

                        override fun onResults(results: Bundle?) {
                            isListening = false
                            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                            val recognized = matches?.firstOrNull()?.trim() ?: ""
                            val command = stageRecognizedSpeech(recognized)
                            if (command != null) {
                                Log.i(TAG, "Staged Voice Transcript (no auto-submit): '$command'")
                                onStaged?.invoke(command)
                            }
                        }

                        override fun onPartialResults(partialResults: Bundle?) {}

                        override fun onEvent(eventType: Int, params: Bundle?) {}
                    })
                }

                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toString())
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                }

                speechRecognizer?.startListening(intent)
            } catch (e: Exception) {
                isListening = false
                Log.e(TAG, "Failed to start speech recognizer", e)
                onError?.invoke(e.message ?: "Voice capture failed")
            }
        }
    }

    fun stopVoiceCapture() {
        mainHandler.post {
            try {
                // Cancel active recognition immediately rather than finalizing and triggering onResults
                speechRecognizer?.cancel()
                stagedTranscript = null
                isListening = false
            } catch (e: Exception) {
                Log.e(TAG, "Error cancelling speech recognizer", e)
            }
        }
    }

    fun destroy() {
        mainHandler.post {
            try {
                speechRecognizer?.destroy()
                speechRecognizer = null
                stagedTranscript = null
                isListening = false
            } catch (e: Exception) {
                Log.e(TAG, "Error destroying speech recognizer", e)
            }
        }
    }

    fun mapSpokenTextToCommand(spoken: String): String {
        val lower = spoken.lowercase(Locale.ROOT).trim()
        return when {
            lower.startsWith("/") -> spoken
            lower == "status" || lower == "system status" || lower == "check status" -> "/status"
            lower == "ignite" || lower == "start substrate" || lower == "ignite substrate" -> "/ignite"
            lower == "ledger" || lower == "audit ledger" || lower == "verify ledger" -> "/ledger"
            lower.startsWith("dna ") || lower.startsWith("genome ") -> "/dna ${spoken.substringAfter(" ")}"
            lower.startsWith("learn ") -> "/learn ${spoken.substringAfter(" ")}"
            else -> "/status" // Safe sovereign fallback query
        }
    }
}

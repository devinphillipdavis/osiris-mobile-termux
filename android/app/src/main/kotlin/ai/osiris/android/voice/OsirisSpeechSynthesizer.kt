package ai.osiris.android.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

class OsirisSpeechSynthesizer(
    context: Context,
    private val onInitialized: ((Boolean) -> Unit)? = null
) : TextToSpeech.OnInitListener {

    companion object {
        private const val TAG = "OsirisVoiceTTS"
    }

    private var tts: TextToSpeech? = TextToSpeech(context.applicationContext, this)
    private var isReady = false

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val result = tts?.setLanguage(Locale.US)
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                Log.w(TAG, "US English TTS voice not available.")
                isReady = false
            } else {
                tts?.setSpeechRate(1.05f)
                tts?.setPitch(0.95f) // Sovereign tactical lower pitch
                isReady = true
                Log.i(TAG, "OSIRIS Sovereign Voice Synthesizer Ready.")
            }
        } else {
            Log.e(TAG, "TTS Initialization failed with status: $status")
            isReady = false
        }
        onInitialized?.invoke(isReady)
    }

    fun speakAlert(text: String, isPriority: Boolean = false) {
        if (!isReady || tts == null) {
            Log.d(TAG, "Voice alert buffered (engine not ready): $text")
            return
        }
        val queueMode = if (isPriority) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
        tts?.speak(text, queueMode, null, "osiris_utterance_${System.currentTimeMillis()}")
    }

    fun shutdown() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        isReady = false
    }
}

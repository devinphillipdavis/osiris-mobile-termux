package ai.osiris.android.ime

import ai.osiris.android.bluetooth.BluetoothScoPersistenceService
import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.TaskSource
import ai.osiris.android.task.TaskSubmissionResult
import ai.osiris.android.voice.OsirisVoiceInputManager
import android.content.Intent
import android.inputmethodservice.InputMethodService
import android.text.InputType
import android.util.Log
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class OsirisIME : InputMethodService(), OsirisKeyboardView.KeyboardActionListener {

    companion object {
        private const val TAG = "OsirisIME"

        fun isPasswordInputType(inputType: Int): Boolean {
            val inputClass = inputType and InputType.TYPE_MASK_CLASS
            val variation = inputType and InputType.TYPE_MASK_VARIATION
            return when (inputClass) {
                InputType.TYPE_CLASS_TEXT -> variation == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
                    variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD ||
                    variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
                InputType.TYPE_CLASS_NUMBER -> variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD
                else -> false
            }
        }
    }

    private val coordinator: OsirisSessionCoordinator = OsirisSessionCoordinator.instance
    private var keyboardView: OsirisKeyboardView? = null
    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())
    private var taskObserverJob: Job? = null
    private var voiceInputManager: OsirisVoiceInputManager? = null

    override fun onCreate() {
        super.onCreate()
        coordinator.attachContext(this)
        voiceInputManager = OsirisVoiceInputManager(this, coordinator)
    }

    override fun onCreateInputView(): View {
        val view = OsirisKeyboardView(this, coordinator, this)
        keyboardView = view
        observeTasks()
        Log.d(TAG, "onCreateInputView: OsirisKeyboardView inflated successfully.")
        return view
    }

    override fun onDestroy() {
        taskObserverJob?.cancel()
        voiceInputManager?.destroy()
        super.onDestroy()
    }

    private fun observeTasks() {
        taskObserverJob?.cancel()
        taskObserverJob = serviceScope.launch {
            coordinator.tasks.collect { tasks ->
                keyboardView?.updateTasksView(tasks)
            }
        }
    }

    private fun isCurrentFieldPassword(): Boolean {
        val info = currentInputEditorInfo ?: return false
        return isPasswordInputType(info.inputType)
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        if (attribute != null && isPasswordInputType(attribute.inputType)) {
            Log.d(TAG, "Password field detected. Suppressing OSIRIS AST capture.")
        } else {
            Log.d(TAG, "Input started. Bypassing ClipboardManager, securing in-memory AST capture.")
        }
    }

    // --- KeyboardActionListener Implementations ---

    override fun onCharacterTyped(text: String) {
        currentInputConnection?.commitText(text, 1)
    }

    override fun onBackspacePressed() {
        currentInputConnection?.deleteSurroundingText(1, 0)
    }

    override fun onEnterPressed() {
        if (isCurrentFieldPassword()) {
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
            return
        }
        // First check if the text in buffer is an OSIRIS command
        val bufferText = currentInputConnection?.getTextBeforeCursor(2048, 0)?.toString() ?: ""
        val trimmed = bufferText.trim()
        if (trimmed.startsWith("/")) {
            onCommandExecuted(trimmed)
        } else {
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
            currentInputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
        }
    }

    override fun onCommandExecuted(command: String) {
        if (isCurrentFieldPassword()) {
            Log.w(TAG, "Suppressed OSIRIS command execution in password field.")
            return
        }
        Log.i(TAG, "Executing OSIRIS command directly: $command")
        
        when (val result = coordinator.submitIntent(command, TaskSource.KEYBOARD, this)) {
            is TaskSubmissionResult.Success -> {
                Log.i(TAG, "[+] OSIRIS Task enqueued: ${result.task.id} (${result.task.command})")
                // Feedback in current text field if desired or leave as background execution
            }
            is TaskSubmissionResult.Blocked -> {
                Log.e(TAG, "[X] OSIRIS Task rejected by CIL: ${result.reason}")
            }
        }
    }

    override fun onVoiceToggled() {
        Log.d(TAG, "Toggling voice capture and SCO audio lock...")
        try {
            val intent = Intent(this, BluetoothScoPersistenceService::class.java)
            startService(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Bluetooth SCO service", e)
        }

        voiceInputManager?.let { mgr ->
            if (mgr.isListening) {
                mgr.stopVoiceCapture()
            } else {
                mgr.startVoiceCapture(
                    onStaged = { stagedCmd ->
                        Log.i(TAG, "Voice transcript staged for review: $stagedCmd")
                        if (!isCurrentFieldPassword()) {
                            currentInputConnection?.commitText(stagedCmd, 1)
                        }
                    },
                    onError = { err ->
                        Log.w(TAG, "Voice recognition error: $err")
                    }
                )
            }
        }
    }

    fun captureAndEvaluateIntent(): TaskSubmissionResult? {
        if (isCurrentFieldPassword()) {
            Log.w(TAG, "Suppressed RAM intent capture: active editor is a password field.")
            return null
        }
        val inputConnection = currentInputConnection ?: return null
        
        // SYS-021 Invariant: Capture directly from RAM, bypass ClipboardManager
        val selectedText = inputConnection.getSelectedText(0)?.toString()
        val textToEvaluate = if (selectedText.isNullOrEmpty()) {
            inputConnection.getTextBeforeCursor(2048, 0)?.toString() ?: ""
        } else {
            selectedText
        }

        if (textToEvaluate.isBlank()) {
            Log.d(TAG, "No text in RAM buffer to evaluate.")
            return null
        }

        return coordinator.submitIntent(textToEvaluate, TaskSource.KEYBOARD, this)
    }
}

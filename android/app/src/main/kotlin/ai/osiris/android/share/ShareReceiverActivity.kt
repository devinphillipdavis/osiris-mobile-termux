package ai.osiris.android.share

import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.TaskSource
import ai.osiris.android.task.TaskSubmissionResult
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.widget.Toast

class ShareReceiverActivity : Activity() {

    companion object {
        private const val TAG = "OsirisShareReceiver"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        handleIncomingIntent(intent)
        finish()
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        if (intent != null) {
            handleIncomingIntent(intent)
        }
        finish()
    }

    private fun handleIncomingIntent(intent: Intent) {
        val action = intent.action
        val type = intent.type

        if (Intent.ACTION_SEND == action && type != null) {
            val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT)
            val sharedStream = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableExtra(Intent.EXTRA_STREAM, android.net.Uri::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra<android.net.Uri>(Intent.EXTRA_STREAM)
            }

            val payload = when {
                !sharedText.isNullOrBlank() -> sharedText
                sharedStream != null -> "URI:$sharedStream"
                else -> null
            }

            if (payload != null) {
                // If it doesn't have an OSIRIS prefix, wrap it as a share task for Node Beta
                val commandPayload = if (payload.startsWith("/")) payload else "/dna \"$payload\""
                
                val coordinator = OsirisSessionCoordinator.instance
                when (val result = coordinator.submitIntent(commandPayload, TaskSource.SHARE_SHEET, this)) {
                    is TaskSubmissionResult.Success -> {
                        Log.i(TAG, "Item shared with OSIRIS: ${result.task.id}")
                        Toast.makeText(this, "OSIRIS: Queued to Node Beta [${result.task.command}]", Toast.LENGTH_SHORT).show()
                    }
                    is TaskSubmissionResult.Blocked -> {
                        Log.w(TAG, "Shared item blocked by OSIRIS firewall: ${result.reason}")
                        Toast.makeText(this, "OSIRIS Firewall: ${result.reason}", Toast.LENGTH_LONG).show()
                    }
                }
            }
        }
    }
}

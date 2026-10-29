package ai.osiris.android.notification

import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.TaskSource
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class OsirisNotificationActionReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "OsirisNotifReceiver"
        const val ACTION_RETRY_TASK = "ai.osiris.android.ACTION_RETRY_TASK"
        const val EXTRA_COMMAND = "extra_command"
        const val EXTRA_TASK_ID = "extra_task_id"
    }

    override fun onReceive(context: Context, intent: Intent?) {
        if (intent == null) return
        val action = intent.action
        Log.i(TAG, "Received notification action: $action")

        when (action) {
            ACTION_RETRY_TASK -> {
                val command = intent.getStringExtra(EXTRA_COMMAND)
                if (!command.isNullOrBlank()) {
                    Log.i(TAG, "Retrying command via notification: $command")
                    val coordinator = OsirisSessionCoordinator.instance
                    coordinator.submitIntent(command, TaskSource.REMOTE_RELAY, context)
                }
            }
        }
    }
}

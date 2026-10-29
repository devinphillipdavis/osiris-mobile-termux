package ai.osiris.android.notification

import ai.osiris.android.task.OsirisTask
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat

class OsirisNotificationManager(private val context: Context) {

    companion object {
        const val CHANNEL_ID = "osiris_task_alerts"
        const val CHANNEL_NAME = "OSIRIS Sovereign Alerts"
        private const val NOTIFICATION_ID_BASE = 4200
    }

    init {
        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Real-time task completion and CIL firewall interception alerts from OSIRIS"
                enableVibration(true)
            }
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            manager?.createNotificationChannel(channel)
        }
    }

    fun postTaskCompletedNotification(task: OsirisTask) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager ?: return

        // Deep link or activity intent
        val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val pendingIntent = if (launchIntent != null) {
            PendingIntent.getActivity(
                context,
                task.id.hashCode(),
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        } else null

        val receiptShort = task.receipt?.receiptHash?.take(12) ?: "LOCAL"
        val ledgerIntent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse("osiris://contact")).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val ledgerPendingIntent = PendingIntent.getActivity(
            context,
            task.id.hashCode() + 1,
            ledgerIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("OSIRIS: Task Complete [${task.command}]")
            .setContentText(task.statusMessage ?: "Execution completed on Node Beta.")
            .setStyle(NotificationCompat.BigTextStyle().bigText(
                "Command: ${task.command}\n" +
                "Source: ${task.source}\n" +
                "Status: ${task.status}\n" +
                "Merkle Receipt: $receiptShort...\n" +
                "Result: ${task.statusMessage ?: "Nominal"}"
            ))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .addAction(android.R.drawable.ic_menu_info_details, "Inspect Ledger", ledgerPendingIntent)
            .apply {
                if (pendingIntent != null) {
                    setContentIntent(pendingIntent)
                }
            }
            .build()

        manager.notify(NOTIFICATION_ID_BASE + (task.id.hashCode() % 1000), notification)
    }

    fun postFirewallRejectionAlert(reason: String, payload: String) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager ?: return

        val auditIntent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse("osiris://contact")).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val auditPendingIntent = PendingIntent.getActivity(
            context,
            9991,
            auditIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("OSIRIS Security: Intent Blocked")
            .setContentText(reason)
            .setStyle(NotificationCompat.BigTextStyle().bigText(
                "Reason: $reason\n" +
                "Intercepted Payload: ${payload.take(128)}\n" +
                "Action: Stamped to immutable evidence ledger."
            ))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .addAction(android.R.drawable.ic_menu_info_details, "Inspect Incident Ledger", auditPendingIntent)
            .build()

        manager.notify(NOTIFICATION_ID_BASE + 999, notification)
    }
}

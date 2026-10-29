package ai.osiris.android.contact

import ai.osiris.android.bluetooth.BluetoothScoPersistenceService
import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.TaskSource
import ai.osiris.android.task.TaskSubmissionResult
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import ai.osiris.android.voice.OsirisVoiceInputManager

class OsirisContactActivity : Activity() {

    private val coordinator = OsirisSessionCoordinator.instance
    private var voiceManager: OsirisVoiceInputManager? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        coordinator.attachContext(this)
        voiceManager = OsirisVoiceInputManager(this, coordinator)

        val rootScroll = ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#0A0E17"))
            isFillViewport = true
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 48)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        rootScroll.addView(container)

        // 1. Sovereign Avatar
        val avatar = TextView(this).apply {
            text = "⌘"
            textSize = 40f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#00E5FF"))
            val dimen = 160
            layoutParams = LinearLayout.LayoutParams(dimen, dimen).apply {
                setMargins(0, 16, 0, 16)
            }
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#131C2E"))
                cornerRadius = 80f
                setStroke(2, Color.parseColor("#00E5FF"))
            }
        }
        container.addView(avatar)

        // 2. Contact Name & Badge
        val nameView = TextView(this).apply {
            text = "OSIRIS Sovereign AI"
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        container.addView(nameView)

        val subtitleView = TextView(this).apply {
            text = "Autonomous Workstation Presence · Node Beta"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            gravity = Gravity.CENTER
            setPadding(0, 4, 0, 24)
        }
        container.addView(subtitleView)

        // 3. Quick Action Buttons
        val actionsContainer = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 32)
        }

        val messageBtn = createActionButton("💬 Message", "#0284C7") {
            showCommandInputDialog()
        }
        actionsContainer.addView(messageBtn)

        val callBtn = createActionButton("📞 Call", "#059669") {
            startVoiceCall()
        }
        actionsContainer.addView(callBtn)

        val syncBtn = createActionButton("📇 Sync Contact", "#4F46E5") {
            syncToPhoneContacts()
        }
        actionsContainer.addView(syncBtn)

        container.addView(actionsContainer)

        // 4. Contact Metadata Card
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 20, 24, 20)
            val bg = GradientDrawable().apply {
                setColor(Color.parseColor("#131C2E"))
                cornerRadius = 16f
                setStroke(1, Color.parseColor("#253655"))
            }
            background = bg
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                setMargins(0, 0, 0, 24)
            }
        }

        card.addView(createDetailRow("Direct Voice Endpoint", OsirisContactSyncHelper.CONTACT_PHONE))
        card.addView(createDetailRow("Workstation Relay", OsirisContactSyncHelper.CONTACT_EMAIL))
        card.addView(createDetailRow("Governance Horizon", "300.0s Temporal Lock · 42.0°C Ceiling"))
        card.addView(createDetailRow("Ledger Root", coordinator.ledger.getLedgerRoot().take(24) + "..."))

        container.addView(card)

        // 5. Active Tasks Summary
        val tasksHeader = TextView(this).apply {
            text = "ACTIVE TASKS & EXECUTION QUEUE"
            textSize = 11f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 0, 0, 8)
        }
        container.addView(tasksHeader)

        val active = coordinator.getActiveTasks()
        if (active.isEmpty()) {
            val emptyNotice = TextView(this).apply {
                text = "Zero active tasks. Tap 'Message' to dispatch a command."
                textSize = 12f
                setTextColor(Color.parseColor("#64748B"))
                setPadding(0, 8, 0, 16)
            }
            container.addView(emptyNotice)
        } else {
            for (task in active) {
                val taskView = TextView(this).apply {
                    text = "• [${task.status}] ${task.command} (Receipt: ${task.receipt?.receiptHash?.take(8) ?: "N/A"})"
                    textSize = 12f
                    typeface = Typeface.MONOSPACE
                    setTextColor(Color.parseColor("#F1F5F9"))
                    setPadding(0, 4, 0, 4)
                }
                container.addView(taskView)
            }
        }

        setContentView(rootScroll)
    }

    private fun createActionButton(label: String, colorHex: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 12f
            setTextColor(Color.WHITE)
            isAllCaps = false
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, 110).apply {
                setMargins(6, 0, 6, 0)
            }
            background = GradientDrawable().apply {
                setColor(Color.parseColor(colorHex))
                cornerRadius = 20f
            }
            setOnClickListener { onClick() }
        }
    }

    private fun createDetailRow(label: String, value: String): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 6, 0, 10)
            addView(TextView(context).apply {
                text = label
                textSize = 11f
                setTextColor(Color.parseColor("#64748B"))
            })
            addView(TextView(context).apply {
                text = value
                textSize = 13f
                typeface = Typeface.MONOSPACE
                setTextColor(Color.parseColor("#E2E8F0"))
            })
        }
    }

    private fun showCommandInputDialog(initialText: String = "") {
        val input = EditText(this).apply {
            hint = "e.g. /ignite, /status, /dna <spec>"
            setText(initialText)
            setTextColor(Color.BLACK)
        }
        AlertDialog.Builder(this)
            .setTitle("Dispatch to OSIRIS")
            .setView(input)
            .setPositiveButton("Dispatch") { _, _ ->
                val cmd = input.text.toString().trim()
                if (cmd.isNotEmpty()) {
                    when (val res = coordinator.submitIntent(cmd, TaskSource.CONTACT_CARD, this)) {
                        is TaskSubmissionResult.Success -> {
                            Toast.makeText(this, "Task Dispatched: ${res.task.command}", Toast.LENGTH_SHORT).show()
                            recreate()
                        }
                        is TaskSubmissionResult.Blocked -> {
                            Toast.makeText(this, "Firewall Blocked: ${res.reason}", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
            .setNegativeButton("Cancel") { _, _ ->
                voiceManager?.discardStagedIntent()
            }
            .show()
    }

    private fun startVoiceCall() {
        Toast.makeText(this, "Connecting 16kHz SCO Voice Session...", Toast.LENGTH_SHORT).show()
        val intent = Intent(this, BluetoothScoPersistenceService::class.java)
        startService(intent)

        voiceManager?.let { mgr ->
            if (mgr.isListening) {
                mgr.stopVoiceCapture()
                Toast.makeText(this, "Voice capture cancelled", Toast.LENGTH_SHORT).show()
            } else {
                mgr.startVoiceCapture(
                    onStaged = { cmd ->
                        Toast.makeText(this, "Voice Transcript Staged: $cmd", Toast.LENGTH_SHORT).show()
                        showCommandInputDialog(cmd)
                    },
                    onError = { err ->
                        Toast.makeText(this, "Voice: $err", Toast.LENGTH_SHORT).show()
                    }
                )
            }
        }
    }

    override fun onDestroy() {
        voiceManager?.destroy()
        super.onDestroy()
    }

    private fun syncToPhoneContacts() {
        val synced = OsirisContactSyncHelper.syncContactToProvider(this)
        if (synced) {
            Toast.makeText(this, "OSIRIS Contact Added to Phone!", Toast.LENGTH_SHORT).show()
        } else {
            // Launch standard Contact Insert intent as fallback
            startActivity(OsirisContactSyncHelper.createInsertContactIntent())
        }
    }
}

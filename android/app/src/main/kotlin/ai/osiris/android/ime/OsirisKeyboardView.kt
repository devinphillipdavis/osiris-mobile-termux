package ai.osiris.android.ime

import ai.osiris.android.task.OsirisSessionCoordinator
import ai.osiris.android.task.OsirisTask
import ai.osiris.android.task.TaskStatus
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView

@SuppressLint("ViewConstructor")
class OsirisKeyboardView(
    context: Context,
    private val coordinator: OsirisSessionCoordinator = OsirisSessionCoordinator.instance,
    private val listener: KeyboardActionListener
) : LinearLayout(context) {

    interface KeyboardActionListener {
        fun onCharacterTyped(text: String)
        fun onBackspacePressed()
        fun onEnterPressed()
        fun onCommandExecuted(command: String)
        fun onVoiceToggled()
    }

    private var isShiftActive = false
    private var isSymbolsMode = false

    private val toolbarLayout: LinearLayout
    private val drawerLayout: LinearLayout
    private val keypadLayout: LinearLayout
    private val taskBadgeView: TextView
    private val betaStatusView: TextView

    private val keyButtons = mutableListOf<Button>()

    private val qwertyRow1 = listOf("Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P")
    private val qwertyRow2 = listOf("A", "S", "D", "F", "G", "H", "J", "K", "L")
    private val qwertyRow3 = listOf("Z", "X", "C", "V", "B", "N", "M")

    private val symbolsRow1 = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
    private val symbolsRow2 = listOf("@", "#", "$", "%", "&", "-", "+", "(", ")")
    private val symbolsRow3 = listOf("*", "\"", "'", ":", ";", "!", "?")

    init {
        orientation = VERTICAL
        setBackgroundColor(Color.parseColor("#0A0E17"))
        setPadding(8, 8, 8, 8)

        // 1. OSIRIS Action Bar / Toolbar
        val toolbarScroll = HorizontalScrollView(context).apply {
            isHorizontalScrollBarEnabled = false
            layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
        }
        toolbarLayout = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(4, 4, 4, 8)
        }
        toolbarScroll.addView(toolbarLayout)
        addView(toolbarScroll)

        // 2. Expandable Session Drawer / Active Task Panel
        drawerLayout = LinearLayout(context).apply {
            orientation = VERTICAL
            visibility = GONE
            setBackgroundColor(Color.parseColor("#131C2E"))
            setPadding(16, 12, 16, 12)
            val bg = GradientDrawable().apply {
                setColor(Color.parseColor("#131C2E"))
                cornerRadius = 12f
                setStroke(1, Color.parseColor("#253655"))
            }
            background = bg
        }
        addView(drawerLayout)

        // 3. Virtual Keypad
        keypadLayout = LinearLayout(context).apply {
            orientation = VERTICAL
            layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
        }
        addView(keypadLayout)

        // Create Toolbar Pills
        val osirisPill = createPillButton("⌘ OSIRIS", "#00E5FF", Color.BLACK) {
            toggleDrawer()
        }
        toolbarLayout.addView(osirisPill)

        val ignitePill = createPillButton("/ignite", "#1E293B", Color.parseColor("#94A3B8")) {
            listener.onCommandExecuted("/ignite")
        }
        toolbarLayout.addView(ignitePill)

        val statusPill = createPillButton("/status", "#1E293B", Color.parseColor("#94A3B8")) {
            listener.onCommandExecuted("/status")
        }
        toolbarLayout.addView(statusPill)

        val dnaPill = createPillButton("/dna", "#1E293B", Color.parseColor("#94A3B8")) {
            listener.onCharacterTyped("/dna ")
        }
        toolbarLayout.addView(dnaPill)

        val ledgerPill = createPillButton("/ledger", "#1E293B", Color.parseColor("#94A3B8")) {
            listener.onCommandExecuted("/ledger")
        }
        toolbarLayout.addView(ledgerPill)

        val voicePill = createPillButton("🎤 Voice", "#1E293B", Color.parseColor("#38BDF8")) {
            listener.onVoiceToggled()
        }
        toolbarLayout.addView(voicePill)

        betaStatusView = createStatusBadge("⚡ Node Beta: OK", "#10B981")
        toolbarLayout.addView(betaStatusView)

        taskBadgeView = createStatusBadge("📋 Tasks: 0", "#6366F1")
        taskBadgeView.setOnClickListener { toggleDrawer() }
        toolbarLayout.addView(taskBadgeView)

        // Build Keypad Rows
        buildKeypad()
    }

    private fun createPillButton(text: String, bgColorHex: String, textColor: Int, onClick: () -> Unit): Button {
        return Button(context).apply {
            this.text = text
            textSize = 12f
            typeface = Typeface.MONOSPACE
            setTextColor(textColor)
            isAllCaps = false
            setPadding(24, 8, 24, 8)
            val params = LayoutParams(LayoutParams.WRAP_CONTENT, 100).apply {
                setMargins(6, 4, 6, 4)
            }
            layoutParams = params
            background = GradientDrawable().apply {
                setColor(Color.parseColor(bgColorHex))
                cornerRadius = 24f
            }
            setOnClickListener { onClick() }
        }
    }

    private fun createStatusBadge(text: String, colorHex: String): TextView {
        return TextView(context).apply {
            this.text = text
            textSize = 11f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor(colorHex))
            setPadding(20, 8, 20, 8)
            val params = LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
                setMargins(8, 4, 8, 4)
            }
            layoutParams = params
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#0F172A"))
                cornerRadius = 16f
                setStroke(1, Color.parseColor(colorHex))
            }
        }
    }

    private fun toggleDrawer() {
        if (drawerLayout.visibility == VISIBLE) {
            drawerLayout.visibility = GONE
        } else {
            renderDrawerContent()
            drawerLayout.visibility = VISIBLE
        }
    }

    fun updateTasksView(tasks: List<OsirisTask>) {
        val activeCount = tasks.count { it.status in listOf(TaskStatus.QUEUED, TaskStatus.SUBMITTED_TO_BETA, TaskStatus.RUNNING) }
        taskBadgeView.text = "📋 Tasks: $activeCount"
        if (drawerLayout.visibility == VISIBLE) {
            renderDrawerContent()
        }
    }

    private fun renderDrawerContent() {
        drawerLayout.removeAllViews()

        val headerView = TextView(context).apply {
            text = "OSIRIS ACTIVE SESSION · GOVERNED EVIDENCE"
            textSize = 11f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 0, 0, 8)
        }
        drawerLayout.addView(headerView)

        val activeTasks = coordinator.getActiveTasks()
        if (activeTasks.isEmpty()) {
            val emptyView = TextView(context).apply {
                text = "Zero active tasks. Use /ignite, /dna, or share items to Node Beta."
                textSize = 12f
                setTextColor(Color.parseColor("#64748B"))
                setPadding(0, 4, 0, 8)
            }
            drawerLayout.addView(emptyView)
        } else {
            for (task in activeTasks.take(3)) {
                val card = LinearLayout(context).apply {
                    orientation = VERTICAL
                    setPadding(12, 8, 12, 8)
                    val cardBg = GradientDrawable().apply {
                        setColor(Color.parseColor("#1E293B"))
                        cornerRadius = 8f
                    }
                    background = cardBg
                    val params = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                        setMargins(0, 4, 0, 6)
                    }
                    layoutParams = params
                }

                val title = TextView(context).apply {
                    text = "[${task.status}] ${task.command}"
                    textSize = 12f
                    typeface = Typeface.MONOSPACE
                    setTextColor(Color.parseColor("#F8FAFC"))
                }
                card.addView(title)

                val info = TextView(context).apply {
                    val digestShort = if (task.receipt != null) task.receipt.receiptHash.take(12) else task.id.take(8)
                    text = "Receipt: $digestShort... | Target: ${task.targetDevice}"
                    textSize = 10f
                    setTextColor(Color.parseColor("#94A3B8"))
                }
                card.addView(info)
                drawerLayout.addView(card)
            }
        }
    }

    private fun buildKeypad() {
        keypadLayout.removeAllViews()
        keyButtons.clear()

        val row1Keys = if (isSymbolsMode) symbolsRow1 else qwertyRow1
        val row2Keys = if (isSymbolsMode) symbolsRow2 else qwertyRow2
        val row3Keys = if (isSymbolsMode) symbolsRow3 else qwertyRow3

        // Row 1
        keypadLayout.addView(createKeyRow(row1Keys))
        // Row 2
        keypadLayout.addView(createKeyRow(row2Keys))
        // Row 3 (Shift + Keys + Backspace)
        val row3Layout = LinearLayout(context).apply {
            orientation = HORIZONTAL
            layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
        }
        val shiftBtn = createSpecialKey(if (isShiftActive) "▲" else "△", 1.5f) {
            isShiftActive = !isShiftActive
            buildKeypad()
        }
        row3Layout.addView(shiftBtn)

        for (k in row3Keys) {
            val keyLabel = if (isShiftActive && !isSymbolsMode) k.uppercase() else k.lowercase()
            val btn = createKeyButton(keyLabel, 1.0f)
            row3Layout.addView(btn)
        }

        val backspaceBtn = createSpecialKey("⌫", 1.5f) {
            listener.onBackspacePressed()
        }
        row3Layout.addView(backspaceBtn)
        keypadLayout.addView(row3Layout)

        // Row 4 (Symbols toggle, Slash, Spacebar, Period, Enter)
        val row4Layout = LinearLayout(context).apply {
            orientation = HORIZONTAL
            layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
        }
        val symbolToggleBtn = createSpecialKey(if (isSymbolsMode) "ABC" else "?123", 1.5f) {
            isSymbolsMode = !isSymbolsMode
            buildKeypad()
        }
        row4Layout.addView(symbolToggleBtn)

        val slashBtn = createKeyButton("/", 1.0f)
        row4Layout.addView(slashBtn)

        val spaceBtn = createSpecialKey("SPACE", 4.0f) {
            listener.onCharacterTyped(" ")
        }
        row4Layout.addView(spaceBtn)

        val periodBtn = createKeyButton(".", 1.0f)
        row4Layout.addView(periodBtn)

        val enterBtn = createSpecialKey("↵", 1.5f) {
            listener.onEnterPressed()
        }
        row4Layout.addView(enterBtn)
        keypadLayout.addView(row4Layout)
    }

    private fun createKeyRow(keys: List<String>): LinearLayout {
        return LinearLayout(context).apply {
            orientation = HORIZONTAL
            layoutParams = LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
            for (k in keys) {
                val label = if (isShiftActive && !isSymbolsMode) k.uppercase() else k.lowercase()
                addView(createKeyButton(label, 1.0f))
            }
        }
    }

    private fun createKeyButton(label: String, weight: Float): Button {
        return Button(context).apply {
            text = label
            textSize = 16f
            setTextColor(Color.WHITE)
            isAllCaps = false
            layoutParams = LayoutParams(0, 130, weight).apply {
                setMargins(3, 4, 3, 4)
            }
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#1E293B"))
                cornerRadius = 10f
            }
            setOnClickListener {
                listener.onCharacterTyped(text.toString())
                if (isShiftActive) {
                    isShiftActive = false
                    buildKeypad()
                }
            }
            keyButtons.add(this)
        }
    }

    private fun createSpecialKey(label: String, weight: Float, onClick: () -> Unit): Button {
        return Button(context).apply {
            text = label
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#00E5FF"))
            isAllCaps = false
            layoutParams = LayoutParams(0, 130, weight).apply {
                setMargins(3, 4, 3, 4)
            }
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#0F172A"))
                cornerRadius = 10f
                setStroke(1, Color.parseColor("#334155"))
            }
            setOnClickListener { onClick() }
        }
    }
}

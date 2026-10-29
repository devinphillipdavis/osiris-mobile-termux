package ai.osiris.android.tile

import ai.osiris.android.bridge.HybridNodeBetaBridge
import ai.osiris.android.bridge.NodeBetaConnectionState
import ai.osiris.android.task.OsirisSessionCoordinator
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import androidx.annotation.RequiresApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@RequiresApi(Build.VERSION_CODES.N)
class OsirisQuickTileService : TileService() {

    private val coordinator = OsirisSessionCoordinator.instance

    override fun onStartListening() {
        super.onStartListening()
        updateTileState()
        (coordinator.bridge as? HybridNodeBetaBridge)?.let { bridge ->
            CoroutineScope(Dispatchers.IO).launch {
                bridge.checkLiveHealth()
                withContext(Dispatchers.Main) {
                    updateTileState()
                }
            }
        }
    }

    override fun onClick() {
        super.onClick()
        val current = coordinator.bridge.connectionState.value
        val next = when (current) {
            NodeBetaConnectionState.LOCAL_CONNECTED -> NodeBetaConnectionState.RELAY_CONNECTED
            NodeBetaConnectionState.RELAY_CONNECTED -> NodeBetaConnectionState.LOCAL_CONNECTED
            else -> NodeBetaConnectionState.LOCAL_CONNECTED
        }
        coordinator.bridge.setConnectionMode(next)
        updateTileState()
    }

    private fun updateTileState() {
        val tile = qsTile ?: return
        val conn = coordinator.bridge.connectionState.value
        val activeCount = coordinator.getActiveTasks().size

        tile.state = if (conn != NodeBetaConnectionState.DISCONNECTED) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = "OSIRIS"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when (conn) {
                NodeBetaConnectionState.LOCAL_CONNECTED -> "Local · $activeCount tasks"
                NodeBetaConnectionState.RELAY_CONNECTED -> "Relay · $activeCount tasks"
                else -> "Offline"
            }
        }
        tile.updateTile()
    }
}

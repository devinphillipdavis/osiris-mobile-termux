package ai.osiris.android.substrate

import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class NodeAlphaSubstrateBridgeTest {

    private lateinit var bridge: NodeAlphaSubstrateBridge

    @Before
    fun setUp() {
        bridge = NodeAlphaSubstrateBridge()
    }

    @Test
    fun `thermal violation throws exception`() {
        val ex = assertThrows(ThermalViolationException::class.java) {
            bridge.verifyThermalCeiling(43.0)
        }
        assertTrue(ex.message?.contains("43.0°C") == true)
    }

    @Test
    fun `temporal lock throws exception on timeout`() {
        val ex = assertThrows(RuntimeException::class.java) {
            runBlocking {
                bridge.executeWithTemporalLock(timeoutMs = 50L) {
                    delay(150L)
                }
            }
        }
        assertTrue(ex.message?.contains("Node Alpha temporal horizon") == true)
    }
}

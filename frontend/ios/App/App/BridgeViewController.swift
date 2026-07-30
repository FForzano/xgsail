import Capacitor

/// Local (non-npm) plugins like WatchBridge aren't auto-discovered by
/// Capacitor's runtime plugin scan — they need explicit registration here,
/// the documented override point for that (see WatchBridgePlugin.swift).
class BridgeViewController: CAPBridgeViewController {
    override func capacitorDidLoad() {
        bridge?.registerPluginInstance(WatchBridgePlugin())
    }
}

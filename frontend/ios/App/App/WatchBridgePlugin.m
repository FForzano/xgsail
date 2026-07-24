#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

// Registers the local WatchBridge plugin with Capacitor's Objective-C runtime
// bridge (docs/native-apps.md "Apple Watch companion"). The method list must
// match WatchBridgePlugin.swift's `pluginMethods`.
CAP_PLUGIN(WatchBridgePlugin, "WatchBridge",
    CAP_PLUGIN_METHOD(isSupported, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(isPaired, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(sendContext, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(listPendingSessions, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(ackSession, CAPPluginReturnPromise);
)

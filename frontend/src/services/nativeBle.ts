import * as e1 from "@xgsail-e1/capacitor";
import { BASE } from "@/api/client";

// XGSail wiring for the reusable E1 device library (@xgsail-e1/capacitor,
// whose source lives in the xgsail-e1 repo alongside the firmware that
// implements the same GATT + device-protocol contract). Everything — BLE
// transport *and* the claim/upload orchestration — is in that package; all
// that's XGSail-specific is the two lines below: which backend base URL to
// talk to, and the keystore namespace existing installs already use.
//
// The whole SDK surface is re-exported so existing importers keep importing
// scanForDevices/findByExternalId/readStatus/writeConfig/… (and the
// E1Config/E1Status/ConfigWriteError/… types) from "@/services/nativeBle"
// unchanged.
export * from "@xgsail-e1/capacitor";

// "xgsail_device_key" preserves the storage namespace already-claimed devices
// have their keys under — do not rename without a migration.
const keyStore = e1.secureStorageKeyStore("xgsail_device_key");
const client = e1.createE1Client({ backend: e1.httpBackend({ baseUrl: BASE }), keyStore });

export const claimDevice = client.claim;
export const uploadSessions = client.uploadSessions;

/** Whether this phone holds a stored key for the device (i.e. it was claimed
 * from here) — e1Sync uses this to skip relaying for devices it can't
 * authenticate as. */
export const getStoredDeviceKey = (xgsailDeviceId: string): Promise<string | null> =>
  keyStore.load(xgsailDeviceId);

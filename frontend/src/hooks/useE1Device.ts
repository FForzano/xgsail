import { useEffect, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { devicesService, deviceKeys, isE1Device } from "@/services/devices";
import * as nativeBle from "@/services/nativeBle";
import type {
  CalibrateResult,
  E1Config,
  E1ConfigPatch,
  E1Status,
  RecCommandResult,
} from "@/services/nativeBle";
import type { Device, UUID } from "@/types";

export type E1ConnectionState = "unsupported" | "searching" | "connected" | "unreachable";

const STATUS_POLL_MS = 5000;

/** Bridges a claimed XGSail `Device` row to its live BLE peripheral (the
 * XGSail E1's `status`/`device_config`/`control` characteristics —
 * xgsail-e1's docs/ble-config.md). Resolves the peripheral by
 * `external_id` (nativeBle.findByExternalId — every E1 advertises under
 * the same name, so external_id read off `identity` is the only
 * disambiguator), holds one connection open for as long as this hook is
 * mounted, and exposes status polling + config/command mutations built on
 * top of it.
 *
 * Returns `state: "unsupported"` on web or for any non-E1/non-claimed
 * device — callers use this to skip rendering the E1 panel entirely. */
export function useE1Device(device: Device | undefined) {
  const queryClient = useQueryClient();
  const types = useQuery({ queryKey: deviceKeys.types, queryFn: devicesService.listTypes });

  const eligible = Capacitor.isNativePlatform() && isE1Device(device, types.data);
  const externalId = device?.external_id ?? null;

  const [state, setState] = useState<E1ConnectionState>("unsupported");
  const [bleId, setBleId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!eligible || !externalId) {
      setState("unsupported");
      setBleId(null);
      return;
    }

    let cancelled = false;
    let connectedBleId: string | null = null;
    setState("searching");

    (async () => {
      const found = await nativeBle.findByExternalId(externalId);
      if (cancelled) return;
      if (!found) {
        setState("unreachable");
        return;
      }
      try {
        await nativeBle.connect(found.bleId);
        if (cancelled) {
          await nativeBle.disconnect(found.bleId);
          return;
        }
        connectedBleId = found.bleId;
        setBleId(found.bleId);
        setState("connected");
      } catch {
        if (!cancelled) setState("unreachable");
      }
    })();

    return () => {
      cancelled = true;
      setBleId(null);
      if (connectedBleId) void nativeBle.disconnect(connectedBleId);
    };
  }, [eligible, externalId, attempt]);

  const statusQuery = useQuery<E1Status>({
    queryKey: ["e1", bleId, "status"],
    queryFn: () => nativeBle.readStatus(bleId!),
    enabled: state === "connected" && !!bleId,
    refetchInterval: STATUS_POLL_MS,
    retry: false,
  });

  const configQuery = useQuery<E1Config>({
    queryKey: ["e1", bleId, "config"],
    queryFn: () => nativeBle.readConfig(bleId!),
    enabled: state === "connected" && !!bleId,
    retry: false,
  });

  const writeConfigMutation = useMutation({
    mutationFn: (patch: E1ConfigPatch) => nativeBle.writeConfig(bleId!, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["e1", bleId, "config"] });
    },
  });

  const calibrateMutation = useMutation<CalibrateResult, Error, boolean>({
    mutationFn: (reset) => (reset ? nativeBle.calibrateReset(bleId!) : nativeBle.calibrate(bleId!)),
  });

  const startRecMutation = useMutation<RecCommandResult, Error, { boatId?: UUID; activityId?: UUID } | undefined>({
    mutationFn: (opts) => nativeBle.startRec(bleId!, opts),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["e1", bleId, "status"] });
    },
  });

  const stopRecMutation = useMutation<RecCommandResult, Error, void>({
    mutationFn: () => nativeBle.stopRec(bleId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["e1", bleId, "status"] });
    },
  });

  const retry = () => setAttempt((n) => n + 1);

  return {
    state,
    status: statusQuery.data,
    statusLoading: statusQuery.isLoading,
    config: configQuery.data,
    configLoading: configQuery.isLoading,
    writeConfig: writeConfigMutation,
    calibrate: calibrateMutation,
    startRec: startRecMutation,
    stopRec: stopRecMutation,
    retry,
  };
}

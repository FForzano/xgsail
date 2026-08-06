import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "@/hooks/useToast";

const DEFAULT_INTERVAL_MS = 30_000;

/** Replaces an explicit Save button: the form saves itself when the modal
 * closes (any path — X, backdrop, Esc, Android back all funnel through
 * `Modal`'s one `onClose`), plus a periodic background save so a long
 * editing session isn't only one crash away from losing everything.
 *
 * `canSave`/`isDirty`/`save` are read through a ref on every tick rather than
 * captured once, so the interval doesn't need to restart on every keystroke
 * and `requestClose` always acts on the latest form state. */
export function useAutoSaveOnClose(options: {
  /** Whether the current form is in a state worth persisting at all — e.g. a
   * brand-new, still-empty record shouldn't be created just because the
   * modal closed. */
  canSave: () => boolean;
  /** Whether the current form differs from what's already saved. */
  isDirty: () => boolean;
  save: () => Promise<unknown>;
  /** Actually unmounts the modal (the state setter behind `creating`/
   * `editingSessionNote`/etc.) — called once the close-triggered save (if
   * any) has settled. */
  onClosed: () => void;
  intervalMs?: number;
}): { requestClose: () => void } {
  const { t } = useTranslation();
  const { notify } = useToast();
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => {
    const interval = setInterval(() => {
      const o = optsRef.current;
      if (o.isDirty() && o.canSave()) void o.save();
    }, options.intervalMs ?? DEFAULT_INTERVAL_MS);
    return () => clearInterval(interval);
    // Deliberately not depending on the (ref-read) options: only the interval
    // length should ever restart this timer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.intervalMs]);

  const requestClose = useCallback(() => {
    const o = optsRef.current;
    if (!o.isDirty() || !o.canSave()) {
      o.onClosed();
      return;
    }
    o.save().then(o.onClosed).catch(() => {
      // Kept open on failure — the whole point of auto-save is that closing
      // must never be how you find out the network dropped your note.
      notify(t("common.saveError"), "error");
    });
  }, [notify, t]);

  return { requestClose };
}

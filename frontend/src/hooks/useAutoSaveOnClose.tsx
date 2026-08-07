import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

const DEFAULT_INTERVAL_MS = 30_000;

/** Replaces an explicit Save button: the form saves itself when the modal
 * closes (any path — X, backdrop, Esc, Android back all funnel through
 * `Modal`'s one `onClose`), plus a periodic background save so a long
 * editing session isn't only one crash away from losing everything.
 *
 * Since closing *is* saving, `discard` is the only way back out: it restores
 * the world to how it was when the editor opened.
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
  /** Opt-in "Scarta modifiche" support. Callers that pass it must render both
   * `discardFooter` (as `Modal`'s `footer`) and `discardDialog`. */
  discard?: {
    /** True when the record exists only because an autosave created it
     * during this editing session — discarding deletes it instead of
     * reverting it. */
    destroysRecord: () => boolean;
    run: () => Promise<unknown>;
  };
  intervalMs?: number;
}): {
  requestClose: () => void;
  requestDiscard: () => void;
  discardFooter: ReactNode;
  discardDialog: ReactNode;
} {
  const { t } = useTranslation();
  const { notify } = useToast();
  const optsRef = useRef(options);
  optsRef.current = options;
  const [confirming, setConfirming] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  /** Whether anything reached the server during *this* editing session — a
   * record the user never persisted needs no discard round trip at all.
   * Reset on close, since the hook instance outlives one open/close cycle. */
  const persistedRef = useRef(false);

  const runSave = useCallback(() => {
    return optsRef.current.save().then((result) => {
      persistedRef.current = true;
      return result;
    });
  }, []);

  const close = useCallback(() => {
    persistedRef.current = false;
    optsRef.current.onClosed();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      const o = optsRef.current;
      if (o.isDirty() && o.canSave()) void runSave();
    }, options.intervalMs ?? DEFAULT_INTERVAL_MS);
    return () => clearInterval(interval);
    // Deliberately not depending on the (ref-read) options: only the interval
    // length should ever restart this timer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.intervalMs]);

  const requestClose = useCallback(() => {
    const o = optsRef.current;
    if (!o.isDirty() || !o.canSave()) {
      close();
      return;
    }
    runSave().then(close).catch(() => {
      // Kept open on failure — the whole point of auto-save is that closing
      // must never be how you find out the network dropped your note.
      notify(t("common.saveError"), "error");
    });
  }, [close, notify, runSave, t]);

  const requestDiscard = useCallback(() => {
    const o = optsRef.current;
    // Nothing was typed and nothing was written: there is nothing to undo,
    // so don't make the user confirm a no-op.
    if (!o.discard || (!o.isDirty() && !persistedRef.current)) {
      close();
      return;
    }
    setConfirming(true);
  }, [close]);

  const confirmDiscard = useCallback(() => {
    const discard = optsRef.current.discard;
    if (!discard) return;
    setDiscarding(true);
    discard
      .run()
      .then(() => {
        setConfirming(false);
        close();
      })
      .catch(() => notify(t("common.saveError"), "error"))
      .finally(() => setDiscarding(false));
  }, [close, notify, t]);

  const discardFooter = options.discard ? (
    <div className="sf-form__actions">
      {/* Always enabled: `isDirty` is a plain function, not reactive state, so
          a `disabled` binding would go stale as the user types. */}
      <Button variant="ghost" onClick={requestDiscard}>
        {t("common.discardChanges")}
      </Button>
    </div>
  ) : null;

  const discardDialog =
    confirming && options.discard ? (
      <ConfirmDialog
        title={t("common.discardChanges")}
        message={t(options.discard.destroysRecord() ? "common.discardConfirmNew" : "common.discardConfirm")}
        busy={discarding}
        onConfirm={confirmDiscard}
        onClose={() => setConfirming(false)}
      />
    ) : null;

  return { requestClose, requestDiscard, discardFooter, discardDialog };
}

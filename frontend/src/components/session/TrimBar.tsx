import { useTranslation } from "react-i18next";
import { useTimeState } from "@/stores/timeController";
import { Button } from "@/components/ui/Button";
import { fmtDuration, fmtTime } from "@/utils/format";
import styles from "./TrimBar.module.css";

// Controls shown under the map while trim mode is active: what the current
// selection is in words, the two "set this bound to the playback cursor"
// shortcuts (the only practical way to move a bound a long way on a phone,
// since a press away from a handle on the chart deliberately only seeks),
// and save/cancel. Split out of SessionDetail because it subscribes to the
// playback clock, which ticks every animation frame.
export function TrimBar({
  startMs,
  endMs,
  onStartChange,
  onEndChange,
  onApply,
  onCancel,
  busy,
}: {
  startMs: number;
  endMs: number;
  onStartChange: (ms: number) => void;
  onEndChange: (ms: number) => void;
  onApply: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const { cursor } = useTimeState();

  return (
    <div className={styles.bar}>
      <div className={styles.info}>
        <div className={styles.readout}>
          <span className={styles.bound}>
            <span className={styles.swatchStart} />
            {fmtTime(startMs)}
          </span>
          <span className={styles.bound}>
            <span className={styles.swatchEnd} />
            {fmtTime(endMs)}
          </span>
          <span className="sf-muted">{fmtDuration((endMs - startMs) / 1000)}</span>
        </div>
        <p className="sf-muted">{t("sessions.trimHint")}</p>
      </div>
      <div className={styles.actions}>
        <Button variant="ghost" disabled={busy || cursor >= endMs} onClick={() => onStartChange(cursor)}>
          {t("sessions.trimStartHere")}
        </Button>
        <Button variant="ghost" disabled={busy || cursor <= startMs} onClick={() => onEndChange(cursor)}>
          {t("sessions.trimEndHere")}
        </Button>
        <Button onClick={onApply} disabled={busy}>
          {t("sessions.applyTrim")}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
      </div>
    </div>
  );
}

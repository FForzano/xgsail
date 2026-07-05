import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Modal } from "./Modal";
import { Button } from "./Button";

/** Confirmation gate for destructive actions (delete / revoke / remove). */
export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onClose,
  busy = false,
}: {
  title: ReactNode;
  message: ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Modal title={title} onClose={onClose}>
      <p>{message}</p>
      <div className="sf-form__actions">
        <Button variant="ghost" onClick={onClose} disabled={busy}>
          {t("common.cancel")}
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={busy}>
          {confirmLabel ?? t("common.confirm")}
        </Button>
      </div>
    </Modal>
  );
}

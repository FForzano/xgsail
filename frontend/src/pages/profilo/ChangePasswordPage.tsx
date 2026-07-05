import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { authService } from "@/services/auth";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";

export function ChangePasswordPage() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next !== confirm) {
      setError(t("profile.passwordMismatch"));
      return;
    }
    setBusy(true);
    try {
      // Revokes every other session; this one gets fresh cookies.
      await authService.changePassword(current, next);
      notify(t("profile.passwordChanged"), "success");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sf-grid" style={{ gridTemplateColumns: "minmax(280px, 480px)" }}>
      <Card title={t("profile.changePassword")}>
        <form onSubmit={onSubmit}>
          <InputField
            label={t("profile.currentPassword")}
            id="current"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
          <InputField
            label={t("profile.newPassword")}
            id="next"
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
          <InputField
            label={t("profile.confirmPassword")}
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
          {error && <p className="sf-form__error">{error}</p>}
          <div className="sf-form__actions">
            <Button type="submit" disabled={busy}>
              {t("common.save")}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";

export function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(params.get("redirect") ?? "/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sf-authpage">
      <form className="sf-authcard" onSubmit={onSubmit}>
        <div className="sf-authcard__header">
          <img src="/logo.svg" alt="" className="sf-authcard__logo" />
          <h1 className="sf-authcard__brand">XGSail</h1>
          <p className="sf-authcard__tagline">Next-Gen Sailing Analytics</p>
        </div>
        <h2>{t("auth.loginTitle")}</h2>
        <InputField
          label={t("auth.email")}
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <InputField
          label={t("auth.password")}
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        {error && <p className="sf-form__error">{error}</p>}
        <Button type="submit" disabled={busy}>
          {t("auth.login")}
        </Button>
        <p className="sf-muted">
          {t("auth.noAccount")} <Link to="/register">{t("auth.register")}</Link>
        </p>
      </form>
    </div>
  );
}

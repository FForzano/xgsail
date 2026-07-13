import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { AuthCardHeader } from "@/components/auth/AuthCardHeader";

export function RegisterPage() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    password: "",
    first_name: "",
    last_name: "",
    terms: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: k === "terms" ? e.target.checked : e.target.value }));

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({
        email: form.email,
        password: form.password,
        first_name: form.first_name || undefined,
        last_name: form.last_name || undefined,
        terms_and_conditions: form.terms,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sf-authpage">
      <form className="sf-authcard" onSubmit={onSubmit}>
        <AuthCardHeader />
        <h2>{t("auth.registerTitle")}</h2>
        <InputField
          label={t("profile.firstName")}
          id="first_name"
          value={form.first_name}
          onChange={set("first_name")}
          autoComplete="given-name"
        />
        <InputField
          label={t("profile.lastName")}
          id="last_name"
          value={form.last_name}
          onChange={set("last_name")}
          autoComplete="family-name"
        />
        <InputField
          label={t("auth.email")}
          id="email"
          type="email"
          value={form.email}
          onChange={set("email")}
          autoComplete="email"
          required
        />
        <InputField
          label={t("auth.password")}
          id="password"
          type="password"
          value={form.password}
          onChange={set("password")}
          autoComplete="new-password"
          minLength={8}
          required
        />
        <label className="sf-check">
          <input type="checkbox" checked={form.terms} onChange={set("terms")} required />
          <span>{t("auth.acceptTerms")}</span>
        </label>
        {error && <p className="sf-form__error">{error}</p>}
        <Button type="submit" disabled={busy}>
          {t("auth.register")}
        </Button>
        <p className="sf-muted">
          {t("auth.haveAccount")} <Link to="/login">{t("auth.login")}</Link>
        </p>
      </form>
    </div>
  );
}

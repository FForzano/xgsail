import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { usersService } from "@/services/users";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { userLabel } from "@/utils/format";
import type { UserSummary } from "@/types";

/** Email → user resolution for every invite flow (boat members, club/group
 * invites, session crew). Exact match via GET /users/lookup. */
export function UserPicker({
  onPick,
  busy = false,
  pickLabel,
}: {
  onPick: (user: UserSummary) => void;
  busy?: boolean;
  pickLabel?: string;
}) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [found, setFound] = useState<UserSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const search = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setFound(null);
    setSearching(true);
    try {
      setFound(await usersService.lookup(email.trim()));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? t("gruppi.userNotFound")
          : t("errors.generic"),
      );
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="sf-userpicker">
      <form onSubmit={search}>
        <InputField
          label={t("gruppi.inviteByEmail")}
          id="picker-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <div className="sf-form__actions">
          <Button type="submit" variant="ghost" disabled={searching || !email}>
            {t("common.search")}
          </Button>
        </div>
      </form>
      {error && <p className="sf-form__error">{error}</p>}
      {found && (
        <div className="sf-strip__item">
          <span>
            <strong>{userLabel(found)}</strong>{" "}
            <span className="sf-muted">{found.email}</span>
          </span>
          <Button className="sf-btn--sm" disabled={busy} onClick={() => onPick(found)}>
            {pickLabel ?? t("common.add")}
          </Button>
        </div>
      )}
    </div>
  );
}

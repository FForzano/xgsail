import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { usersService, userKeys } from "@/services/users";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { userLabel } from "@/utils/format";
import type { UserSearchResult, UserSummary } from "@/types";
import styles from "./UserPicker.module.css";

const DEBOUNCE_MS = 300;
const MIN_QUERY = 2;

/** Facebook-style people search for every invite flow (boat members,
 * club/group invites, session crew): type a name/email, pick from a live
 * list. `Combobox` (see BoatPicker) was considered but doesn't fit — its
 * model collapses to a single selected value shown back in the input, while
 * here each row needs its own avatar/email/shared-badge and (for callers
 * that pass `pickLabel`) its own action button, with the list staying open
 * while `busy`. */
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
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const enabled = debounced.length >= MIN_QUERY;
  const results = useQuery({
    queryKey: userKeys.search(debounced),
    queryFn: () => usersService.search(debounced),
    enabled,
  });

  const pick = (user: UserSearchResult) => {
    if (busy) return;
    onPick(user);
  };

  return (
    <div>
      <InputField
        label={t("users.searchPlaceholder")}
        id="picker-query"
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoComplete="off"
      />
      {debounced.length === 1 && <p className="sf-muted">{t("users.minChars")}</p>}
      {enabled && results.isFetching && <Spinner inline />}
      {enabled && !results.isFetching && (
        <ul className="sf-strip">
          {(results.data ?? []).length === 0 && (
            <li className="sf-strip__item sf-strip__item--muted">{t("users.noResults")}</li>
          )}
          {(results.data ?? []).map((user) =>
            pickLabel ? (
              <li key={user.id} className="sf-strip__item">
                <UserRow user={user} />
                <Button className="sf-btn--sm" disabled={busy} onClick={() => pick(user)}>
                  {pickLabel}
                </Button>
              </li>
            ) : (
              <li key={user.id}>
                <button
                  type="button"
                  className={`sf-strip__item ${styles.rowButton}`}
                  disabled={busy}
                  onClick={() => pick(user)}
                >
                  <UserRow user={user} />
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}

function UserRow({ user }: { user: UserSearchResult }) {
  const { t } = useTranslation();
  return (
    <span className="sf-crew-row">
      <Avatar profileImage={user.profile_image} firstName={user.first_name} lastName={user.last_name} size="sm" />
      <span>
        <strong>{userLabel(user)}</strong> <span className="sf-muted">{user.email}</span>
        {user.shared && <span className="sf-muted"> · {t("users.shared")}</span>}
      </span>
    </span>
  );
}

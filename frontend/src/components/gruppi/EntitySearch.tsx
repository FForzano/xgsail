import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { clubsService, clubKeys } from "@/services/clubs";
import { groupsService, groupKeys } from "@/services/groups";
import { smartSearch } from "@/utils/smartSearch";
import { EmptyState } from "@/components/ui/EmptyState";
import styles from "./entitySearch.module.css";

/** Single search box for both clubs and groups (Gruppi section header) —
 * both lists are already fully loaded by ClubsPage/GroupsPage via the same
 * query keys, so this reuses the cache instead of adding a request. Results
 * are grouped by type and only shown while the user is actively typing. */
export function EntitySearch() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: clubsService.list });
  const groups = useQuery({ queryKey: groupKeys.all, queryFn: () => groupsService.list() });

  const trimmed = query.trim();
  if (!trimmed) {
    return (
      <div className={styles.search} data-tour="gruppi-search">
        <Search size={16} className={styles.icon} />
        <input
          className={styles.input}
          type="search"
          placeholder={t("gruppi.searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
    );
  }

  const clubMatches = smartSearch(trimmed, clubs.data ?? [], (c) => [c.name, c.city, c.description]);
  const groupMatches = smartSearch(trimmed, groups.data ?? [], (g) => [g.name, g.description]);
  const noResults = clubMatches.length === 0 && groupMatches.length === 0;

  return (
    <div className={styles.search} data-tour="gruppi-search">
      <div className={styles.bar}>
        <Search size={16} className={styles.icon} />
        <input
          className={styles.input}
          type="search"
          placeholder={t("gruppi.searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
      </div>
      <div className={styles.results}>
        {noResults ? (
          <EmptyState>{t("gruppi.noSearchResults")}</EmptyState>
        ) : (
          <>
            {clubMatches.map((c) => (
              <Link key={c.id} to={`/gruppi/clubs/${c.id}`} className="sf-strip__item">
                <span>
                  <span className="sf-badge">{t("gruppi.clubs")}</span> <strong>{c.name}</strong>{" "}
                  <span className="sf-muted">{c.city ?? ""}</span>
                </span>
              </Link>
            ))}
            {groupMatches.map((g) => (
              <Link key={g.id} to={`/gruppi/gruppi/${g.id}`} className="sf-strip__item">
                <span>
                  <span className="sf-badge">{t("gruppi.groups")}</span> <strong>{g.name}</strong>{" "}
                  <span className="sf-muted">{g.description ?? ""}</span>
                </span>
              </Link>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

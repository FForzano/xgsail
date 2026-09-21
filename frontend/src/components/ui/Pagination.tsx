import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./Button";
import styles from "./Pagination.module.css";

/** Rows per page for the in-memory lists that use `usePagination`. */
export const DEFAULT_PAGE_SIZE = 10;

/** Client-side paging over a list that is already fully in memory (no
 * endpoint here paginates). The page index is clamped on read instead of
 * being corrected by an effect, so a list that shrinks under the caller —
 * deleting the last row of the last page — can never render an empty page. */
export function usePagination<T>(items: T[], pageSize: number = DEFAULT_PAGE_SIZE) {
  const [requestedPage, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(requestedPage, pageCount - 1);
  const start = page * pageSize;
  return { page, setPage, pageCount, pageItems: items.slice(start, start + pageSize) };
}

/** Prev/next pager with a page indicator. Renders nothing for a single page,
 * so a caller can mount it unconditionally next to any paged list. */
export function Pagination({
  page,
  pageCount,
  onPageChange,
  label,
}: {
  /** Zero-based current page. */
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  /** Accessible name for the `<nav>`, when a page has more than one pager. */
  label?: string;
}) {
  const { t } = useTranslation();
  if (pageCount <= 1) return null;

  return (
    <nav className={styles.pagination} aria-label={label ?? t("common.pagination")}>
      <Button
        variant="ghost"
        className="sf-btn--icon-sm"
        disabled={page <= 0}
        aria-label={t("common.previousPage")}
        title={t("common.previousPage")}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft size={16} />
      </Button>
      <span className={styles.indicator} aria-live="polite">
        {t("common.pageOf", { page: page + 1, pageCount })}
      </span>
      <Button
        variant="ghost"
        className="sf-btn--icon-sm"
        disabled={page >= pageCount - 1}
        aria-label={t("common.nextPage")}
        title={t("common.nextPage")}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight size={16} />
      </Button>
    </nav>
  );
}

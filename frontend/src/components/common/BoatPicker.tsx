import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { boatsService, boatKeys } from "@/services/boats";
import { Combobox } from "@/components/ui/Combobox";
import type { Boat, UUID } from "@/types";

const DEBOUNCE_MS = 250;
const MIN_QUERY = 2;

export function boatLabel(boat: Pick<Boat, "name" | "sail_number">): string {
  return boat.sail_number ? `${boat.name} — ${boat.sail_number}` : boat.name;
}

/** Pick a boat out of every boat on the instance.
 *
 * Searches server-side (name / sail number / class) rather than loading the
 * table into a <select>: an organizer entering a regatta is choosing from all
 * boats, not just their own, and that list grows with every user. */
export function BoatPicker({
  id,
  label,
  value,
  onChange,
  exclude,
  disabled,
}: {
  id: string;
  label: string;
  value: UUID | "";
  onChange: (id: UUID | "") => void;
  /** Boats already on the list — hidden so they can't be picked twice. */
  exclude?: UUID[];
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [picked, setPicked] = useState<Boat | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!value) setPicked(null);
  }, [value]);

  const enabled = debounced.length >= MIN_QUERY;
  const results = useQuery({
    queryKey: boatKeys.search(debounced),
    queryFn: () => boatsService.search(debounced),
    enabled,
  });

  const excluded = useMemo(() => new Set(exclude ?? []), [exclude]);
  const options = useMemo(
    () =>
      (results.data ?? [])
        .filter((b) => !excluded.has(b.id))
        .map((b) => ({ id: b.id, label: boatLabel(b) })),
    [results.data, excluded],
  );

  return (
    <Combobox
      id={id}
      label={label}
      options={options}
      query={query}
      onQueryChange={setQuery}
      onPick={(boatId) => {
        setPicked(results.data?.find((b) => b.id === boatId) ?? null);
        onChange(boatId as UUID);
      }}
      selectedLabel={picked ? boatLabel(picked) : undefined}
      emptyMessage={
        !enabled
          ? t("boats.searchHint")
          : results.isFetching
            ? t("common.loading")
            : t("boats.noBoatMatch")
      }
      placeholder={t("boats.searchPlaceholder")}
      disabled={disabled}
    />
  );
}

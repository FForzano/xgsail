import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Combobox } from "@/components/ui/Combobox";
import type { BoatClass, UUID } from "@/types";

const MAX_RESULTS = 30;

function classInfoBits(boatClass: BoatClass, t: (key: string) => string): string[] {
  return [
    boatClass.hull_type && t(`admin.${boatClass.hull_type}`),
    boatClass.crew_size != null && `${t("admin.crewSize")}: ${boatClass.crew_size}`,
    boatClass.rig_type && t(`admin.${boatClass.rig_type}`),
    boatClass.py_rating != null && `PY ${boatClass.py_rating}`,
  ].filter((b): b is string => Boolean(b));
}

/** Type-to-filter combobox for picking a boat class out of a large catalog
 * (a plain <select> is unusable once the RYA catalog is loaded — 300+
 * options). Once a class is picked, collapses to a single read-only card
 * (logo + name + details, all in one block) with an edit icon that reopens
 * the search input — instead of leaving an always-editable field sitting
 * in the form. */
export function ClassPicker({
  label,
  id,
  classes,
  value,
  onChange,
}: {
  label: string;
  id: string;
  classes: BoatClass[];
  value: UUID | "";
  onChange: (id: UUID | "") => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);

  const selected = classes.find((c) => c.id === value) ?? null;

  // Client-side: the catalog is already loaded, so there is nothing to fetch.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pool = q ? classes.filter((c) => c.name.toLowerCase().includes(q)) : classes;
    return pool.slice(0, MAX_RESULTS).map((c) => ({
      id: c.id,
      label: c.name,
      render: (
        <>
          {c.logo ? <img className="sf-avatar sf-avatar--sm" src={c.logo.url} alt="" /> : null}
          <span>{c.name}</span>
        </>
      ),
    }));
  }, [classes, query]);

  if (selected && !editing) {
    const bits = classInfoBits(selected, t);
    return (
      <div className="sf-field">
        <span className="sf-field__label">{label}</span>
        <div className="sf-strip__item sf-strip__item--muted">
          <span style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            {selected.logo && (
              <img className="sf-avatar sf-avatar--sm" src={selected.logo.url} alt="" />
            )}
            <span>
              <strong>{selected.name}</strong>
              {bits.length > 0 && <div className="sf-classinfo__details sf-muted">{bits.join(" · ")}</div>}
            </span>
          </span>
          <Button
            variant="ghost"
            className="sf-btn--sm"
            type="button"
            aria-label={t("common.edit")}
            title={t("common.edit")}
            onClick={() => setEditing(true)}
          >
            ✎
          </Button>
        </div>
      </div>
    );
  }

  return (
    <Combobox
      id={id}
      label={label}
      options={filtered}
      query={query}
      onQueryChange={setQuery}
      onPick={(picked) => {
        onChange(picked as UUID | "");
        setEditing(false);
      }}
      selectedLabel={selected?.name}
      emptyOption={{ label: t("boats.noClass"), value: "" }}
      emptyMessage={t("boats.noClassMatch")}
      autoFocus={editing}
    />
  );
}

/** Read-only summary strip for a selected class — secondary info, not part
 * of the boat's own fields, but useful context (e.g. confirming crew size
 * or PY rating match what the sailor expects). Used outside ClassPicker
 * (e.g. the non-manager read-only boat view). */
export function ClassInfo({ boatClass }: { boatClass: BoatClass }) {
  const { t } = useTranslation();
  const bits = classInfoBits(boatClass, t);

  if (bits.length === 0 && !boatClass.logo) return null;

  return (
    <div className="sf-classinfo">
      {boatClass.logo ? (
        <img className="sf-avatar sf-avatar--sm" src={boatClass.logo.url} alt="" />
      ) : null}
      {bits.length > 0 && <div className="sf-classinfo__details sf-muted">{bits.join(" · ")}</div>}
    </div>
  );
}

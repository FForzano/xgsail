import styles from "./ResultsRow.module.css";

/** A ruled line of labelled figures — the row a results sheet prints for each
 * boat. The session page's totals and each diary entry's figures are this
 * same line; `compact` is the diary's quieter size. */
export function ResultsRow({
  cells,
  compact = false,
}: {
  cells: Array<[label: string, value: string]>;
  compact?: boolean;
}) {
  return (
    <dl className={compact ? `${styles.row} ${styles.compact}` : styles.row}>
      {cells.map(([label, value]) => (
        <div key={label} className={styles.cell}>
          <dt className={styles.label}>{label}</dt>
          <dd className={styles.value}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

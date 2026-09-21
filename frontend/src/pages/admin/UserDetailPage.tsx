import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { adminService, adminKeys } from "@/services/admin";
import { boatsService, boatKeys } from "@/services/boats";
import { Section } from "@/components/ui/Section";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { BackLink } from "@/components/ui/BackLink";
import { Pagination, DEFAULT_PAGE_SIZE } from "@/components/ui/Pagination";
import { StatTile, StatTiles } from "@/components/session/StatTile";
import { sessionStatusBadge } from "@/utils/badges";
import { fmtDateTime, userLabel } from "@/utils/format";
import { ApiError } from "@/api/client";
import type { UUID } from "@/types";
import styles from "./UserDetailPage.module.css";

/** Server-paginated lists here carry no total count, so "is there another
 * page" is inferred from a full page coming back — one page short of the
 * true count, same tradeoff `Pagination`'s callers elsewhere accept. */
function inferPageCount(rowCount: number, page: number, pageSize: number): number {
  return rowCount === pageSize ? page + 2 : page + 1;
}

/** Operator diagnostics for one account: profile, counts, and enough of
 * their boats/activities/sessions to spot what's broken — plus the access
 * log for *this* user, so the fact that operator reads are recorded is
 * visible right where an operator would look. See `backend/routers/admin.py`. */
export function UserDetailPage() {
  const { userId } = useParams<{ userId: UUID }>();
  const { t } = useTranslation();

  const [activitiesPage, setActivitiesPage] = useState(0);
  const [sessionsPage, setSessionsPage] = useState(0);
  const [logPage, setLogPage] = useState(0);

  const detail = useQuery({
    queryKey: adminKeys.userDetail(userId!),
    queryFn: () => adminService.userDetail(userId!),
    enabled: !!userId,
  });

  const boats = useQuery({
    queryKey: adminKeys.userBoats(userId!),
    queryFn: () => adminService.userBoats(userId!),
    enabled: !!userId && !!detail.data,
  });

  const classes = useQuery({
    queryKey: boatKeys.classes(),
    queryFn: () => boatsService.listClasses({ limit: 1000, sort: "name" }),
    staleTime: 60 * 60 * 1000,
    enabled: (boats.data?.length ?? 0) > 0,
  });

  const activities = useQuery({
    queryKey: adminKeys.userActivities(userId!, DEFAULT_PAGE_SIZE, activitiesPage * DEFAULT_PAGE_SIZE),
    queryFn: () =>
      adminService.userActivities(userId!, DEFAULT_PAGE_SIZE, activitiesPage * DEFAULT_PAGE_SIZE),
    enabled: !!userId && !!detail.data,
  });

  const sessions = useQuery({
    queryKey: adminKeys.userSessions(userId!, DEFAULT_PAGE_SIZE, sessionsPage * DEFAULT_PAGE_SIZE),
    queryFn: () =>
      adminService.userSessions(userId!, DEFAULT_PAGE_SIZE, sessionsPage * DEFAULT_PAGE_SIZE),
    enabled: !!userId && !!detail.data,
  });

  const accessLog = useQuery({
    queryKey: adminKeys.accessLog(userId!, DEFAULT_PAGE_SIZE, logPage * DEFAULT_PAGE_SIZE),
    queryFn: () => adminService.accessLog(userId!, DEFAULT_PAGE_SIZE, logPage * DEFAULT_PAGE_SIZE),
    enabled: !!userId && !!detail.data,
  });

  if (!userId || detail.isLoading) return <Spinner full />;

  if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <div className={styles.page}>
        <BackLink to="/admin/users" label={t("admin.userDetail.back")} />
        <EmptyState>{notFound ? t("admin.userDetail.notFound") : t("errors.generic")}</EmptyState>
      </div>
    );
  }
  if (!detail.data) return null;

  const { user, counts } = detail.data;
  const classNameById = new Map((classes.data ?? []).map((c) => [c.id, c.name]));

  return (
    <div className={styles.page}>
      <BackLink to="/admin/users" label={t("admin.userDetail.back")} />

      <Section
        title={userLabel(user)}
        actions={
          <span
            className={
              user.status === "active" ? "sf-badge sf-badge--success" : "sf-badge sf-badge--danger"
            }
          >
            {user.status}
          </span>
        }
      >
        <p className="sf-muted">{t("admin.userDetail.auditNotice")}</p>
        <dl className={styles.meta}>
          <div>
            <dt>{t("auth.email")}</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>{t("admin.superadmin")}</dt>
            <dd>{user.is_superadmin ? "✓" : "—"}</dd>
          </div>
          <div>
            <dt>{t("admin.userDetail.unitSystem")}</dt>
            <dd>
              {user.unit_system === "nautical"
                ? t("admin.userDetail.unitNautical")
                : t("admin.userDetail.unitMetric")}
            </dd>
          </div>
          <div>
            <dt>{t("admin.userDetail.createdAt")}</dt>
            <dd>{user.created_at ? fmtDateTime(user.created_at) : "—"}</dd>
          </div>
        </dl>

        <StatTiles>
          <StatTile label={t("admin.userDetail.countBoats")} value={counts.boats} />
          <StatTile label={t("admin.userDetail.countActivities")} value={counts.activities} />
          <StatTile label={t("admin.userDetail.countSessions")} value={counts.sessions} />
          <StatTile label={t("admin.userDetail.countDevices")} value={counts.devices} />
          <StatTile label={t("admin.userDetail.countClubs")} value={counts.clubs} />
          <StatTile label={t("admin.userDetail.countGroups")} value={counts.groups} />
          <StatTile label={t("admin.userDetail.countRoles")} value={counts.roles} />
        </StatTiles>
      </Section>

      <Section title={t("admin.userDetail.boats")}>
        {boats.isLoading ? (
          <Spinner />
        ) : !boats.data?.length ? (
          <EmptyState>{t("admin.userDetail.noBoats")}</EmptyState>
        ) : (
          <div className="sf-tablewrap">
            <table className="sf-table">
              <thead>
                <tr>
                  <th>{t("common.name")}</th>
                  <th>{t("boats.sailNumber")}</th>
                  <th>{t("admin.userDetail.boatClass")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {boats.data.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <Link to={`/profilo/barche/${b.id}`}>{b.name}</Link>
                      {b.is_guest && (
                        <span className="sf-badge sf-badge--warning" style={{ marginLeft: "0.4rem" }}>
                          {t("admin.userDetail.guestBoat")}
                        </span>
                      )}
                    </td>
                    <td className="sf-muted">{b.sail_number ?? "—"}</td>
                    <td className="sf-muted">
                      {b.boat_class_id ? (classNameById.get(b.boat_class_id) ?? "—") : "—"}
                    </td>
                    <td>
                      <Link to={`/profilo/barche/${b.id}`}>{t("admin.userDetail.open")}</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title={t("admin.userDetail.activities")}>
        {activities.isLoading ? (
          <Spinner />
        ) : !activities.data?.length ? (
          <EmptyState>{t("admin.userDetail.noActivities")}</EmptyState>
        ) : (
          <>
            <div className="sf-tablewrap">
              <table className="sf-table">
                <thead>
                  <tr>
                    <th>{t("common.date")}</th>
                    <th>{t("common.name")}</th>
                    <th>{t("activities.type")}</th>
                    <th>{t("admin.userDetail.visibility")}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {activities.data.map((a) => (
                    <tr key={a.id}>
                      <td>{fmtDateTime(a.started_at)}</td>
                      <td>
                        <Link to={`/diario/activities/${a.id}`}>{a.name ?? "—"}</Link>
                      </td>
                      <td className="sf-muted">{t(`activities.types.${a.type}`)}</td>
                      <td className="sf-muted">{t(`activities.visibility.${a.visibility}`)}</td>
                      <td>
                        <Link to={`/diario/activities/${a.id}`}>{t("admin.userDetail.open")}</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={activitiesPage}
              pageCount={inferPageCount(activities.data.length, activitiesPage, DEFAULT_PAGE_SIZE)}
              onPageChange={setActivitiesPage}
              label={t("admin.userDetail.activities")}
            />
          </>
        )}
      </Section>

      <Section title={t("admin.userDetail.sessions")}>
        {sessions.isLoading ? (
          <Spinner />
        ) : !sessions.data?.length ? (
          <EmptyState>{t("admin.userDetail.noSessions")}</EmptyState>
        ) : (
          <>
            <div className="sf-tablewrap">
              <table className="sf-table">
                <thead>
                  <tr>
                    <th>{t("common.date")}</th>
                    <th>{t("sessions.boat")}</th>
                    <th>{t("common.status")}</th>
                    <th>{t("admin.userDetail.hasNotes")}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.data.map((s) => (
                    <tr key={s.id}>
                      <td>{fmtDateTime(s.started_at)}</td>
                      <td className="sf-muted">{s.boat?.name ?? "—"}</td>
                      <td>
                        <span className={sessionStatusBadge(s.status)}>{s.status}</span>
                      </td>
                      <td className="sf-muted">{s.has_notes ? "✓" : "—"}</td>
                      <td>
                        <Link to={`/diario/activities/${s.activity_id}/barche/${s.id}`}>
                          {t("admin.userDetail.open")}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={sessionsPage}
              pageCount={inferPageCount(sessions.data.length, sessionsPage, DEFAULT_PAGE_SIZE)}
              onPageChange={setSessionsPage}
              label={t("admin.userDetail.sessions")}
            />
          </>
        )}
      </Section>

      <Section title={t("admin.userDetail.accessLog")}>
        <p className="sf-muted">{t("admin.userDetail.accessLogHint")}</p>
        {accessLog.isLoading ? (
          <Spinner />
        ) : !accessLog.data?.length ? (
          <EmptyState>{t("admin.userDetail.noAccessLog")}</EmptyState>
        ) : (
          <>
            <div className="sf-tablewrap">
              <table className="sf-table">
                <thead>
                  <tr>
                    <th>{t("common.date")}</th>
                    <th>{t("admin.userDetail.actor")}</th>
                    <th>{t("admin.userDetail.action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {accessLog.data.map((entry) => (
                    <tr key={entry.id}>
                      <td>{fmtDateTime(entry.created_at)}</td>
                      <td className="sf-muted">
                        {entry.actor ? userLabel(entry.actor) : t("admin.userDetail.deletedUser")}
                      </td>
                      <td className="sf-muted">{t(`admin.userDetail.actions.${entry.action}`)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={logPage}
              pageCount={inferPageCount(accessLog.data.length, logPage, DEFAULT_PAGE_SIZE)}
              onPageChange={setLogPage}
              label={t("admin.userDetail.accessLog")}
            />
          </>
        )}
      </Section>
    </div>
  );
}

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { usersService, userKeys } from "@/services/users";
import { userLabel } from "@/utils/format";

export function UsersPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const users = useQuery({ queryKey: userKeys.all, queryFn: usersService.list });

  const goToUser = (id: string) => navigate(`/admin/users/${id}`);

  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th>{t("common.name")}</th>
            <th>{t("auth.email")}</th>
            <th>{t("common.status")}</th>
            <th>{t("admin.superadmin")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.data?.map((u) => (
            <tr
              key={u.id}
              className="sf-table__row--clickable"
              role="link"
              tabIndex={0}
              onClick={() => goToUser(u.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  goToUser(u.id);
                }
              }}
            >
              <td>{userLabel(u)}</td>
              <td className="sf-muted">{u.email}</td>
              <td>
                <span
                  className={
                    u.status === "active" ? "sf-badge sf-badge--success" : "sf-badge sf-badge--danger"
                  }
                >
                  {u.status}
                </span>
              </td>
              <td>{u.is_superadmin ? "✓" : ""}</td>
              <td className="sf-table__chevron" aria-hidden>
                <svg viewBox="0 0 16 16" width="16" height="16">
                  <path
                    d="M5 2.5 11.5 8 5 13.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

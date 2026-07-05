import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Spinner } from "@/components/ui/Spinner";

/** Login-everywhere gate: the whole app shell lives under this route. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Spinner full />;
  if (status === "anon") {
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }
  return <Outlet />;
}

export function RequireSuperadmin() {
  const { user, status } = useAuth();
  if (status === "loading") return <Spinner full />;
  if (!user?.is_superadmin) return <Navigate to="/" replace />;
  return <Outlet />;
}

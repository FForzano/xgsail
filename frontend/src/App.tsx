import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth, RequireSuperadmin } from "@/components/auth/RequireAuth";
import { LoginPage } from "@/pages/Login";
import { RegisterPage } from "@/pages/Register";
import { NotFoundPage } from "@/pages/NotFound";
import { DiarioLayout } from "@/pages/diario/DiarioLayout";
import { SessionsPage } from "@/pages/diario/SessionsPage";
import { SessionDetailPage } from "@/pages/diario/SessionDetailPage";
import { ImportPage } from "@/pages/diario/ImportPage";
import { ActivitiesPage } from "@/pages/diario/ActivitiesPage";
import { ActivityDetailPage } from "@/pages/diario/ActivityDetailPage";
import { RegattasPage } from "@/pages/diario/RegattasPage";
import { RacePage } from "@/pages/diario/RacePage";
import { GruppiLayout } from "@/pages/gruppi/GruppiLayout";
import { GroupsPage } from "@/pages/gruppi/GroupsPage";
import { GroupDetailPage } from "@/pages/gruppi/GroupDetailPage";
import { ClubsPage } from "@/pages/gruppi/ClubsPage";
import { ClubDetailPage } from "@/pages/gruppi/ClubDetailPage";
import { ProfiloLayout } from "@/pages/profilo/ProfiloLayout";
import { AnagraficaPage } from "@/pages/profilo/AnagraficaPage";
import { ChangePasswordPage } from "@/pages/profilo/ChangePasswordPage";
import { BoatsPage } from "@/pages/profilo/BoatsPage";
import { BoatDetailPage } from "@/pages/profilo/BoatDetailPage";
import { DevicesPage } from "@/pages/profilo/DevicesPage";
import { DeviceDetailPage } from "@/pages/profilo/DeviceDetailPage";
import { AdminPage } from "@/pages/admin/AdminPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Login mandatory everywhere: the entire shell sits behind RequireAuth. */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/diario/sessioni" replace />} />

          <Route path="/diario" element={<DiarioLayout />}>
            <Route index element={<Navigate to="sessioni" replace />} />
            <Route path="sessioni" element={<SessionsPage />} />
            <Route path="sessioni/import" element={<ImportPage />} />
            <Route path="sessioni/:sessionId" element={<SessionDetailPage />} />
            <Route path="activities" element={<ActivitiesPage />} />
            <Route path="activities/:activityId" element={<ActivityDetailPage />} />
            <Route path="regate" element={<RegattasPage />} />
          </Route>
          {/* The race dashboard is full-width, outside the tabbed layout. */}
          <Route path="/diario/regate/race/:raceId" element={<RacePage />} />

          <Route path="/gruppi" element={<GruppiLayout />}>
            <Route index element={<Navigate to="gruppi" replace />} />
            <Route path="gruppi" element={<GroupsPage />} />
            <Route path="gruppi/:groupId" element={<GroupDetailPage />} />
            <Route path="clubs" element={<ClubsPage />} />
            <Route path="clubs/:clubId" element={<ClubDetailPage />} />
          </Route>

          <Route path="/profilo" element={<ProfiloLayout />}>
            <Route index element={<Navigate to="anagrafica" replace />} />
            <Route path="anagrafica" element={<AnagraficaPage />} />
            <Route path="password" element={<ChangePasswordPage />} />
            <Route path="barche" element={<BoatsPage />} />
            <Route path="barche/:boatId" element={<BoatDetailPage />} />
            <Route path="devices" element={<DevicesPage />} />
            <Route path="devices/:deviceId" element={<DeviceDetailPage />} />
          </Route>

          <Route element={<RequireSuperadmin />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

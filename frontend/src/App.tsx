import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth, RequireSuperadmin } from "@/components/auth/RequireAuth";
import { LandingPage } from "@/pages/Landing";
import { LoginPage } from "@/pages/Login";
import { RegisterPage } from "@/pages/Register";
import { NotFoundPage } from "@/pages/NotFound";
import { DiarioLayout } from "@/pages/diario/DiarioLayout";
import { SessionDetailPage } from "@/pages/diario/SessionDetailPage";
import { ImportPage } from "@/pages/diario/ImportPage";
import { ActivitiesPage } from "@/pages/diario/ActivitiesPage";
import { ActivityDetailPage } from "@/pages/diario/ActivityDetailPage";
import { RegattasPage } from "@/pages/diario/RegattasPage";
import { RacePage } from "@/pages/diario/RacePage";
import { RegistraPage } from "@/pages/registra/RegistraPage";
import { GruppiLayout } from "@/pages/gruppi/GruppiLayout";
import { GroupsPage } from "@/pages/gruppi/GroupsPage";
import { GroupDetailLayout, GroupFeedRoute } from "@/pages/gruppi/GroupDetailLayout";
import { GroupOverview } from "@/pages/gruppi/GroupOverview";
import { GroupActivities } from "@/pages/gruppi/GroupActivities";
import { GroupMembers } from "@/pages/gruppi/GroupMembers";
import { ClubsPage } from "@/pages/gruppi/ClubsPage";
import { ClubDetailLayout, ClubDevicesRoute, ClubFeedRoute, ClubRegattasRoute } from "@/pages/gruppi/ClubDetailLayout";
import { ClubOverview } from "@/pages/gruppi/ClubOverview";
import { ClubMembers } from "@/pages/gruppi/ClubMembers";
import { ProfiloLayout } from "@/pages/profilo/ProfiloLayout";
import { AnagraficaPage } from "@/pages/profilo/AnagraficaPage";
import { ChangePasswordPage } from "@/pages/profilo/ChangePasswordPage";
import { BoatsPage } from "@/pages/profilo/BoatsPage";
import { BoatDetailPage } from "@/pages/profilo/BoatDetailPage";
import { DevicesPage } from "@/pages/profilo/DevicesPage";
import { DeviceDetailPage } from "@/pages/profilo/DeviceDetailPage";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { AppSettingsPage } from "@/pages/admin/AppSettingsPage";
import { WindStationsPage } from "@/pages/admin/WindStationsPage";
import { UsersPage } from "@/pages/admin/UsersPage";
import { DeviceTypesPage } from "@/pages/admin/DeviceTypesPage";
import { BoatClassesPage } from "@/pages/admin/BoatClassesPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Login mandatory everywhere else: the app shell sits behind RequireAuth. */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/diario" element={<DiarioLayout />}>
            <Route index element={<Navigate to="activities" replace />} />
            <Route path="activities" element={<ActivitiesPage />} />
            <Route path="activities/import" element={<ImportPage />} />
            <Route path="activities/:activityId" element={<ActivityDetailPage />} />
            <Route path="activities/:activityId/barche/:sessionId" element={<SessionDetailPage />} />
            <Route path="regate" element={<RegattasPage />} />
          </Route>
          {/* The race dashboard is full-width, outside the tabbed layout. */}
          <Route path="/diario/regate/race/:raceId" element={<RacePage />} />

          {/* Native-only — see AppShell's Capacitor.isNativePlatform() gate;
              the route itself is harmless on web (just unreachable). */}
          <Route path="/registra" element={<RegistraPage />} />

          <Route path="/gruppi" element={<GruppiLayout />}>
            <Route index element={<Navigate to="gruppi" replace />} />
            <Route path="gruppi" element={<GroupsPage />} />
            <Route path="gruppi/:groupId" element={<GroupDetailLayout />}>
              <Route index element={<GroupFeedRoute />} />
              <Route path="informazioni" element={<GroupOverview />} />
              <Route path="attivita" element={<GroupActivities />} />
              <Route path="membri" element={<GroupMembers />} />
            </Route>
            <Route path="clubs" element={<ClubsPage />} />
            <Route path="clubs/:clubId" element={<ClubDetailLayout />}>
              <Route index element={<ClubFeedRoute />} />
              <Route path="informazioni" element={<ClubOverview />} />
              <Route path="membri" element={<ClubMembers />} />
              <Route path="regate" element={<ClubRegattasRoute />} />
              <Route path="flotta" element={<ClubDevicesRoute />} />
            </Route>
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
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<Navigate to="settings" replace />} />
              <Route path="settings" element={<AppSettingsPage />} />
              <Route path="wind" element={<WindStationsPage />} />
              <Route path="users" element={<UsersPage />} />
              <Route path="device-types" element={<DeviceTypesPage />} />
              <Route path="boat-classes" element={<BoatClassesPage />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

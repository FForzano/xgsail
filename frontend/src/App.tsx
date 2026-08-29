import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth, RequireLegalAcceptance, RequireSuperadmin } from "@/components/auth/RequireAuth";
import { LandingPage } from "@/pages/Landing";
import { LoginPage } from "@/pages/Login";
import { RegisterPage } from "@/pages/Register";
import { TermsPage } from "@/pages/legal/TermsPage";
import { PrivacyPage } from "@/pages/legal/PrivacyPage";
import { NotFoundPage } from "@/pages/NotFound";
import { DiarioLayout } from "@/pages/diario/DiarioLayout";
import { SessionDetailPage } from "@/pages/diario/SessionDetailPage";
import { ImportPage } from "@/pages/diario/ImportPage";
import { MyDiaryPage } from "@/pages/diario/MyDiaryPage";
import { ClubsDiaryPage } from "@/pages/diario/ClubsDiaryPage";
import { ProgressPage } from "@/pages/diario/ProgressPage";
import { ActivityDetailPage } from "@/pages/diario/ActivityDetailPage";
import { RacePage } from "@/pages/diario/RacePage";
import { RegattaDetailPage } from "@/pages/diario/RegattaDetailPage";
import { RegattaJoinPage } from "@/pages/diario/RegattaJoinPage";
import { RegistraPage } from "@/pages/registra/RegistraPage";
import { GruppiLayout } from "@/pages/gruppi/GruppiLayout";
import { GroupsPage } from "@/pages/gruppi/GroupsPage";
import { GroupDetailLayout, GroupFeedRoute } from "@/pages/gruppi/GroupDetailLayout";
import { GroupOverview } from "@/pages/gruppi/GroupOverview";
import { GroupActivities } from "@/pages/gruppi/GroupActivities";
import { GroupMembers } from "@/pages/gruppi/GroupMembers";
import { ClubsPage } from "@/pages/gruppi/ClubsPage";
import { ClubDetailLayout, ClubDevicesRoute, ClubEventsRoute, ClubFeedRoute } from "@/pages/gruppi/ClubDetailLayout";
import { ClubOverview } from "@/pages/gruppi/ClubOverview";
import { ClubMembers } from "@/pages/gruppi/ClubMembers";
import { ProfiloLayout } from "@/pages/profilo/ProfiloLayout";
import { AnagraficaPage } from "@/pages/profilo/AnagraficaPage";
import { ChangePasswordPage } from "@/pages/profilo/ChangePasswordPage";
import { BoatsPage } from "@/pages/profilo/BoatsPage";
import { BoatDetailPage } from "@/pages/profilo/BoatDetailPage";
import { BoatNotebookPage } from "@/pages/profilo/BoatNotebookPage";
import { NoteTemplatesPage } from "@/pages/profilo/NoteTemplatesPage";
import { DevicesPage } from "@/pages/profilo/DevicesPage";
import { DeviceDetailPage } from "@/pages/profilo/DeviceDetailPage";
import { InfoPage } from "@/pages/profilo/InfoPage";
import { canShowSupportLinks } from "@/config/platform";
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
      {/* Public so anonymous visitors can read them before registering. */}
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />

      {/* Login mandatory everywhere else: the app shell sits behind RequireAuth.
          RequireLegalAcceptance then blocks the app until updated Terms/Privacy
          are (re-)accepted. */}
      <Route element={<RequireAuth />}>
        <Route element={<RequireLegalAcceptance />}>
          <Route element={<AppShell />}>
          <Route path="/diario" element={<DiarioLayout />}>
            <Route index element={<Navigate to="personale" replace />} />
            <Route path="personale" element={<MyDiaryPage />} />
            <Route path="circoli" element={<ClubsDiaryPage />} />
            <Route path="progressi" element={<ProgressPage />} />
            <Route path="activities/import" element={<ImportPage />} />
            <Route path="activities/:activityId" element={<ActivityDetailPage />} />
            <Route path="activities/:activityId/barche/:sessionId" element={<SessionDetailPage />} />
          </Route>
          {/* The race dashboard and its regatta are full-width, outside the tabbed layout. */}
          <Route path="/diario/regate/race/:raceId" element={<RacePage />} />
          <Route path="/diario/regate/regatta/:regattaId" element={<RegattaDetailPage />} />
          {/* Short path: this link gets pasted into the fleet's chat group. */}
          <Route path="/regate/:regattaId/join" element={<RegattaJoinPage />} />

          {/* Everywhere: the exploration map works on web too, only the
              recording controls are native-gated (see RegistraPage). */}
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
              <Route path="eventi" element={<ClubEventsRoute />} />
              <Route path="flotta" element={<ClubDevicesRoute />} />
            </Route>
          </Route>

          <Route path="/profilo" element={<ProfiloLayout />}>
            <Route index element={<Navigate to="anagrafica" replace />} />
            <Route path="anagrafica" element={<AnagraficaPage />} />
            <Route path="password" element={<ChangePasswordPage />} />
            <Route path="barche" element={<BoatsPage />} />
            <Route path="barche/modelli" element={<NoteTemplatesPage />} />
            <Route path="barche/:boatId" element={<BoatDetailPage />} />
            <Route path="barche/:boatId/quaderno" element={<BoatNotebookPage />} />
            <Route path="devices" element={<DevicesPage />} />
            <Route path="devices/:deviceId" element={<DeviceDetailPage />} />
            {/* Store builds use the app stores' own donation systems instead. */}
            {canShowSupportLinks && <Route path="info" element={<InfoPage />} />}
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
      </Route>
    </Routes>
  );
}

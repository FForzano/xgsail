import { useEffect, useState, type FormEvent } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Pencil } from "lucide-react";
import { clubsService, clubKeys } from "@/services/clubs";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useToast } from "@/hooks/useToast";
import { SectionLayout } from "@/components/layout/SectionLayout";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField, TextAreaField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { ImageUploader } from "@/components/common/ImageUploader";
import { BackLink } from "@/components/ui/BackLink";
import { EntityFeed } from "@/components/gruppi/EntityFeed";
import { ClubDevices } from "./ClubDevices";
import { ClubRegattas } from "./ClubRegattas";
import type { Boat, Club, UUID } from "@/types";

export interface ClubContext {
  clubId: UUID;
  club: Club;
  isMember: boolean;
  manages: boolean;
  managesMembers: boolean;
  managesRegattas: boolean;
  managesRoles: boolean;
  managesPosts: boolean;
  stationedBoats: Boat[];
}

export function useClubContext() {
  return useOutletContext<ClubContext>();
}

export function ClubDetailLayout() {
  const { clubId } = useParams<{ clubId: UUID }>();
  const { t } = useTranslation();
  const { can, memberOfClub } = useCapabilities();
  const { notify } = useToast();
  const queryClient = useQueryClient();

  const club = useQuery({
    queryKey: clubKeys.detail(clubId!),
    queryFn: () => clubsService.get(clubId!),
    enabled: !!clubId,
  });
  const isMember = !!clubId && (memberOfClub(clubId) || can("club.manage", clubId));
  const boats = useQuery({ queryKey: boatKeys.all, queryFn: () => boatsService.list() });

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", city: "", website: "" });

  useEffect(() => {
    if (club.data) {
      setForm({
        name: club.data.name ?? "",
        description: club.data.description ?? "",
        city: club.data.city ?? "",
        website: club.data.website ?? "",
      });
    }
  }, [club.data]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: clubKeys.all });
  };

  const save = useMutation({
    mutationFn: () =>
      clubsService.update(clubId!, {
        name: form.name,
        description: form.description || null,
        city: form.city || null,
        website: form.website || null,
      }),
    onSuccess: async () => {
      setEditing(false);
      notify(t("common.saved"), "success");
      await invalidate();
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (club.isLoading || !clubId) return <Spinner />;
  if (!club.data) return null;
  const c = club.data;
  const memberCount = c.members?.filter((m) => m.status === "active").length ?? 0;
  const pendingRequests = c.members?.filter((m) => m.status === "requested").length ?? 0;

  // In-place management (no separate admin page): same URL, extra actions.
  const manages = can("club.manage", clubId);
  const managesMembers = can("user_club.manage", clubId);
  const managesRegattas = can("regatta.manage", clubId);
  const managesRoles = can("user_role.manage_scoped", clubId);
  const managesPosts = can("club_post.manage", clubId);
  const stationedBoats = boats.data?.filter((b) => b.club_id === clubId) ?? [];

  const context: ClubContext = {
    clubId,
    club: c,
    isMember,
    manages,
    managesMembers,
    managesRegattas,
    managesRoles,
    managesPosts,
    stationedBoats,
  };

  return (
    <div className="sf-section__body">
      <BackLink to="/gruppi/clubs" label={t("gruppi.backToClubs")} />
      <Card>
        <div className="sf-entity-header">
          <div className="sf-entity-header__identity">
            {c.logo && <img className="sf-avatar sf-avatar--lg" src={c.logo.url} alt="" />}
            <div>
              <h1 className="sf-entity-header__name">{c.name}</h1>
              <p className="sf-muted sf-entity-header__meta">
                {t("gruppi.memberCount", { count: memberCount })}
              </p>
              {manages && <span className="sf-badge sf-badge--success">{t("gruppi.manageMode")}</span>}
            </div>
          </div>
          {manages && (
            <div className="sf-entity-header__actions">
              <ImageUploader
                create={() => clubsService.uploadLogo(clubId)}
                confirm={(id) => clubsService.confirmLogo(clubId, id)}
                onDone={invalidate}
                crop
                icon={<ImagePlus size={16} />}
                label={t("common.upload")}
              />
              <Button
                variant="ghost"
                className="sf-btn--icon-sm"
                aria-label={t("gruppi.editClub")}
                onClick={() => setEditing(true)}
              >
                <Pencil size={16} />
              </Button>
            </div>
          )}
        </div>
      </Card>

      <SectionLayout
        tabs={[
          ...(isMember ? [{ to: `/gruppi/clubs/${clubId}`, label: t("gruppi.news"), end: true }] : []),
          { to: `/gruppi/clubs/${clubId}/informazioni`, label: t("gruppi.overview") },
          { to: `/gruppi/clubs/${clubId}/regate`, label: t("gruppi.regattas") },
          ...(isMember
            ? [{
                to: `/gruppi/clubs/${clubId}/membri`,
                label: t("gruppi.clubMembers"),
                badge: managesMembers ? pendingRequests : 0,
              }]
            : []),
          ...(manages ? [{ to: `/gruppi/clubs/${clubId}/flotta`, label: t("gruppi.fleetHealth") }] : []),
        ]}
        context={context}
        sticky={false}
      />

      {editing && (
        <Modal title={t("gruppi.editClub")} onClose={() => setEditing(false)}>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <InputField
              label={t("common.name")}
              id="ce-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <TextAreaField
              label={t("common.description")}
              id="ce-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            <div className="sf-form__row">
              <InputField
                label={t("gruppi.city")}
                id="ce-city"
                value={form.city}
                onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
              />
              <InputField
                label={t("gruppi.website")}
                id="ce-web"
                value={form.website}
                onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))}
              />
            </div>
            <div className="sf-form__actions">
              <Button type="submit" disabled={save.isPending}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

/** Route wrappers: ClubRegattas/ClubDevices take `clubId`/`manage` as plain
 * props (used nowhere else), so they don't need to know about the outlet
 * context themselves — these just bridge the two. */
export function ClubRegattasRoute() {
  const { clubId, managesRegattas } = useClubContext();
  return <ClubRegattas clubId={clubId} manage={managesRegattas} />;
}

export function ClubDevicesRoute() {
  const { clubId } = useClubContext();
  return <ClubDevices clubId={clubId} />;
}

export function ClubFeedRoute() {
  const { clubId, managesPosts } = useClubContext();
  return <EntityFeed ownerType="club" ownerId={clubId} canManage={managesPosts} />;
}

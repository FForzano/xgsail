import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { clubsService, clubKeys } from "@/services/clubs";
import { membershipKeys } from "@/components/membership/MembershipStrip";
import { useCapabilities } from "@/hooks/useCapabilities";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { InputField } from "@/components/ui/InputField";
import { RichTextField } from "@/components/ui/RichTextField";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { richTextExcerpt } from "@/utils/richTextExcerpt";
import type { UUID } from "@/types";

const DESCRIPTION_EXCERPT_LENGTH = 100;

export function ClubsPage() {
  const { t } = useTranslation();
  const { memberOfClub, ownsClub } = useCapabilities();
  const { refreshCaps } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", city: "" });
  const [claimClubId, setClaimClubId] = useState<UUID | "">("");

  // Present only when we arrived from a map POI's "create club" action
  // (components/map/PoiLayer.ts / useNauticalLayers.ts) — carries the OSM
  // element to either create a new club from or link to an existing one.
  const osmLink = useMemo(() => {
    const osmRef = searchParams.get("osm");
    if (!osmRef) return null;
    const lat = Number(searchParams.get("osm_lat"));
    const lng = Number(searchParams.get("osm_lng"));
    return {
      osmRef,
      name: searchParams.get("osm_name") ?? "",
      lat: Number.isFinite(lat) ? lat : null,
      lng: Number.isFinite(lng) ? lng : null,
    };
  }, [searchParams]);

  const clubs = useQuery({ queryKey: clubKeys.all, queryFn: clubsService.list });

  // The osm* params only make sense once, to offer the link — once it's made
  // (or the user moves on), clear them so a refresh doesn't re-offer a link
  // that already exists.
  const clearOsmParams = () => navigate("/gruppi/clubs", { replace: true });

  // A 409 here has one specific cause worth naming — the OSM element is
  // already linked to another club — and it is the case the user can act on
  // (they picked the wrong place, or someone else got there first).
  const notifyLinkError = (error: unknown) =>
    notify(
      error instanceof ApiError && error.status === 409
        ? t("gruppi.osmAlreadyLinked")
        : t("errors.generic"),
      "error",
    );

  const create = useMutation({
    mutationFn: () =>
      clubsService.create({
        name: form.name,
        description: form.description || null,
        city: form.city || null,
        ...(osmLink ? { lat: osmLink.lat, lng: osmLink.lng, osm_ref: osmLink.osmRef } : {}),
      }),
    onSuccess: async () => {
      setCreating(false);
      setForm({ name: "", description: "", city: "" });
      await queryClient.invalidateQueries({ queryKey: clubKeys.all });
      await refreshCaps(); // creator got the scoped club_admin role
      if (osmLink) clearOsmParams();
    },
    onError: notifyLinkError,
  });

  // Only clubs the user administers can be offered — claiming grants nothing
  // new, but PATCH /clubs/{id} is manage-gated, so offering one they can't
  // administer would just produce a 403 from the server.
  const manageableClubs = (clubs.data ?? []).filter((c) => ownsClub(c.id));

  const claim = useMutation({
    mutationFn: () => clubsService.update(claimClubId as UUID, { osm_ref: osmLink!.osmRef }),
    onSuccess: async () => {
      setClaimClubId("");
      await queryClient.invalidateQueries({ queryKey: clubKeys.all });
      clearOsmParams();
    },
    onError: notifyLinkError,
  });

  const join = useMutation({
    mutationFn: (clubId: UUID) => clubsService.addMember(clubId),
    onSuccess: async () => {
      notify(t("gruppi.joinRequested"), "success");
      await queryClient.invalidateQueries({ queryKey: membershipKeys.mine });
    },
    onError: () => notify(t("errors.generic"), "error"),
  });

  if (clubs.isLoading) return <Spinner />;

  const isMine = (id: UUID) => memberOfClub(id) || ownsClub(id);
  const active = clubs.data?.filter((c) => c.is_active) ?? [];
  const mine = active.filter((c) => isMine(c.id));
  const discover = active.filter((c) => !isMine(c.id));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  const openCreateFromOsm = () => {
    setForm({ name: osmLink!.name, description: "", city: "" });
    setCreating(true);
  };

  return (
    <>
      <div className="sf-toolbar">
        <h3>{t("gruppi.myClubs")}</h3>
        <Button onClick={() => setCreating(true)}>{t("gruppi.createClub")}</Button>
      </div>

      {osmLink && (
        <Card>
          <p>{t("gruppi.createClubFromOsm")}</p>
          <div className="sf-form__actions">
            <Button onClick={openCreateFromOsm}>{t("gruppi.createClub")}</Button>
            {manageableClubs.length > 0 && (
              <>
                <Select
                  label={t("gruppi.osmClaimLabel")}
                  id="osm-claim-club"
                  value={claimClubId}
                  onChange={(e) => setClaimClubId(e.target.value as UUID)}
                >
                  <option value="">{t("gruppi.osmClaimPlaceholder")}</option>
                  {manageableClubs.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
                <Button disabled={!claimClubId || claim.isPending} onClick={() => claim.mutate()}>
                  {t("gruppi.osmClaimAction")}
                </Button>
              </>
            )}
          </div>
        </Card>
      )}

      {mine.length === 0 ? (
        <EmptyState>{t("gruppi.emptyClubs")}</EmptyState>
      ) : (
        <div className="sf-grid">
          {mine.map((c) => (
            <Link key={c.id} to={`/gruppi/clubs/${c.id}`} className="sf-card">
              {c.logo && <img className="sf-avatar" src={c.logo.url} alt="" />}
              <h3>{c.name}</h3>
              <p className="sf-muted">{c.city ?? richTextExcerpt(c.description, DESCRIPTION_EXCERPT_LENGTH)}</p>
              {ownsClub(c.id) && (
                <span className="sf-badge sf-badge--success">{t("gruppi.manageMode")}</span>
              )}
            </Link>
          ))}
        </div>
      )}

      {discover.length > 0 && (
        <Card title={t("gruppi.discoverClubs")}>
          <div className="sf-strip">
            {discover.map((c) => (
              <div key={c.id} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <Link to={`/gruppi/clubs/${c.id}`}>
                    <strong>{c.name}</strong>
                  </Link>{" "}
                  <span className="sf-muted">{c.city ?? ""}</span>
                </span>
                <Button
                  className="sf-btn--sm"
                  disabled={join.isPending}
                  onClick={() => join.mutate(c.id)}
                >
                  {t("gruppi.join")}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {creating && (
        <Modal
          title={t("gruppi.createClub")}
          onClose={() => setCreating(false)}
          size="wide"
          footer={
            <div className="sf-form__actions">
              <Button type="submit" form="c-create-form" disabled={create.isPending || !form.name}>
                {t("common.create")}
              </Button>
            </div>
          }
        >
          <form id="c-create-form" onSubmit={onSubmit}>
            <InputField
              label={t("common.name")}
              id="c-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
            <RichTextField
              label={t("common.description")}
              id="c-desc"
              value={form.description}
              onChange={(html) => setForm((f) => ({ ...f, description: html }))}
              tier="basic"
            />
            <InputField
              label={t("gruppi.city")}
              id="c-city"
              value={form.city}
              onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
            />
          </form>
        </Modal>
      )}
    </>
  );
}

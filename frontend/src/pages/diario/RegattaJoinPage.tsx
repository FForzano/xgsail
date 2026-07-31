import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery } from "@tanstack/react-query";
import { regattasService, raceKeys } from "@/services/races";
import { boatsService, boatKeys } from "@/services/boats";
import { useToast } from "@/hooks/useToast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { InputField } from "@/components/ui/InputField";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import type { UUID } from "@/types";

/** Redeem a regatta's share code to put one of your own boats on its start
 * list — the self-service half of the entry flow, for sailors the organizer
 * hasn't entered by hand (typically visitors from another club).
 *
 * Entry is immediate, with no organizer approval: this is normally done on the
 * beach on race morning. It only enables tagging recordings with the
 * regatta's races; it is not the official race entry. */
export function RegattaJoinPage() {
  const { regattaId } = useParams<{ regattaId: UUID }>();
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();
  const { notify } = useToast();
  const navigate = useNavigate();

  const [code, setCode] = useState(searchParams.get("code") ?? "");
  const [boatId, setBoatId] = useState<UUID | "">("");

  const regatta = useQuery({
    queryKey: raceKeys.regatta(regattaId!),
    queryFn: () => regattasService.get(regattaId!),
    enabled: !!regattaId,
  });
  // Only boats the sailor owns/administers can be entered, so the picker is
  // their own list rather than a search over every boat.
  const myBoats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });

  useEffect(() => {
    if (myBoats.data?.length === 1) setBoatId(myBoats.data[0].id);
  }, [myBoats.data]);

  const join = useMutation({
    mutationFn: () => regattasService.join(regattaId!, { code: code.trim(), boat_id: boatId as UUID }),
    onSuccess: () => {
      notify(t("regate.joined"), "success");
      navigate(`/diario/regate/regatta/${regattaId}`);
    },
    onError: () => notify(t("regate.joinFailed"), "error"),
  });

  if (regatta.isLoading || !regattaId) return <Spinner />;
  if (!regatta.data) return null;

  return (
    <div className="sf-section__body">
      <Card title={t("regate.joinTitle", { name: regatta.data.name })}>
        <p className="sf-muted">{t("regate.joinIntro")}</p>
        {myBoats.data?.length === 0 ? (
          <EmptyState>{t("regate.joinNeedsBoat")}</EmptyState>
        ) : (
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              if (code.trim() && boatId) join.mutate();
            }}
          >
            <Select
              label={t("race.boat")}
              id="join-boat"
              value={boatId}
              onChange={(e) => setBoatId(e.target.value as UUID)}
            >
              <option value="">…</option>
              {myBoats.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.sail_number ? `${b.name} — ${b.sail_number}` : b.name}
                </option>
              ))}
            </Select>
            <InputField
              label={t("regate.joinCode")}
              id="join-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
            <div className="sf-form__actions">
              <Button type="submit" disabled={join.isPending || !code.trim() || !boatId}>
                {t("regate.joinAction")}
              </Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}

import { useMemo } from "react";
import { useAuth } from "./useAuth";
import type { UUID } from "@/types";

export interface CapabilityHelpers {
  /** RBAC check mirroring the backend: global grant always applies, scoped
   * grants only for the matching club. Superadmin can everything. */
  can: (perm: string, clubId?: UUID) => boolean;
  isSuperadmin: boolean;
  ownsClub: (clubId: UUID) => boolean;
  memberOfClub: (clubId: UUID) => boolean;
  memberOfGroup: (groupId: UUID) => boolean;
  isBoatOwner: (boatId: UUID) => boolean;
  isBoatManager: (boatId: UUID) => boolean; // owner or admin
}

export function useCapabilities(): CapabilityHelpers {
  const { caps } = useAuth();

  return useMemo(() => {
    const sa = caps?.user.is_superadmin ?? false;
    const globalPerms = new Set(caps?.permissions.global ?? []);
    const byClub = caps?.permissions.byClub ?? {};
    const m = caps?.memberships;

    const can = (perm: string, clubId?: UUID) => {
      if (sa) return true;
      if (globalPerms.has(perm)) return true;
      if (clubId && byClub[clubId]?.includes(perm)) return true;
      return false;
    };

    return {
      can,
      isSuperadmin: sa,
      ownsClub: (clubId) => sa || (m?.clubsOwned.includes(clubId) ?? false),
      memberOfClub: (clubId) => m?.clubsMember.includes(clubId) ?? false,
      memberOfGroup: (groupId) => m?.groups.includes(groupId) ?? false,
      isBoatOwner: (boatId) => sa || (m?.boatsOwner.includes(boatId) ?? false),
      isBoatManager: (boatId) =>
        sa || (m?.boatsOwner.includes(boatId) ?? false) || (m?.boatsAdmin.includes(boatId) ?? false),
    };
  }, [caps]);
}

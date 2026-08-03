import { WindStationHintCard } from "@/components/common/WindStationHintCard";
import { useGroupContext } from "./GroupDetailLayout";

export function GroupOverview() {
  const { group, manages } = useGroupContext();

  return (
    <>
      {manages && <WindStationHintCard />}
      <p className="sf-muted">{group.description}</p>
    </>
  );
}

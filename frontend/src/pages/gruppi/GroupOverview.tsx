import { WindStationHintCard } from "@/components/common/WindStationHintCard";
import { RichText } from "@/components/ui/RichText";
import { useGroupContext } from "./GroupDetailLayout";

export function GroupOverview() {
  const { group, manages } = useGroupContext();

  return (
    <>
      {manages && <WindStationHintCard />}
      <RichText html={group.description} tier="basic" className="sf-muted" />
    </>
  );
}

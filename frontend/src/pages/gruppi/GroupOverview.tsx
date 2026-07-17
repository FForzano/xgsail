import { Card } from "@/components/ui/Card";
import { useGroupContext } from "./GroupDetailLayout";

export function GroupOverview() {
  const { group } = useGroupContext();

  return (
    <Card>
      <p className="sf-muted">{group.description}</p>
    </Card>
  );
}

import { Badge } from "@/components/ui/badge";
import { isMockEnabled } from "@/lib/api/mock";

// Shown whenever mock mode is on, so mocked answers are never mistaken for
// real ones in screenshots or the demo (AGENTS.md §2.5).
export function MockBadge() {
  if (!isMockEnabled()) return null;
  return (
    <Badge variant="warning" title="Answers are fake fixtures from lib/api/mock.ts, not the backend">
      MOCK DATA
    </Badge>
  );
}

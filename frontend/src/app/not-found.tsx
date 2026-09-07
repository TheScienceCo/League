import Link from "next/link";

import { EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <EmptyState
      title="Not found"
      action={
        <Link href="/" className="link text-sm">
          Back to search
        </Link>
      }
    >
      That player or match isn’t in this instance. Try searching for a Riot ID.
    </EmptyState>
  );
}

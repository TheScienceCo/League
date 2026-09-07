import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ riotId: string }>;
}): Promise<Metadata> {
  const { riotId } = await params;
  return { title: decodeURIComponent(riotId) };
}

export default function PlayerLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

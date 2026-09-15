import Workspace from "@/components/Workspace";
export default async function ImpactPage({
  params,
}: {
  params: Promise<{ id: string; symbolId: string }>;
}) {
  const { id, symbolId } = await params;
  return <Workspace id={id} initialImpact={symbolId} />;
}

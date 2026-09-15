import Workspace from "@/components/Workspace";
export default async function RepositoryPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <Workspace id={id} />;
}

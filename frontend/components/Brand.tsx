import Link from "next/link";
import { Network } from "lucide-react";
export default function Brand() {
  return (
    <Link href="/" className="brand">
      <span className="brand-mark">
        <Network size={21} />
      </span>
      RepoGraph<span className="brand-label">LOCAL</span>
    </Link>
  );
}

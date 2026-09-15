import Link from "next/link";
export default function Brand() {
  return (
    <Link href="/" className="brand">
      <span className="brand-mark">
        <img src="/regora-mark.svg" alt="" width={32} height={32} />
      </span>
      Regora<span className="brand-label">LOCAL</span>
    </Link>
  );
}

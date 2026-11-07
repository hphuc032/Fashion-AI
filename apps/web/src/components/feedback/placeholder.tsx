import { LockKeyhole, ArrowLeft } from "lucide-react";
import Link from "next/link";
export function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <section className="placeholder">
      <span className="eyebrow">GIAI ĐOẠN TIẾP THEO</span>
      <div className="placeholder-icon">
        <LockKeyhole size={30} />
      </div>
      <h1>{title}</h1>
      <p>{text}</p>
      <Link className="text-link" href="/dashboard">
        <ArrowLeft size={16} /> Về tổng quan hệ thống
      </Link>
    </section>
  );
}

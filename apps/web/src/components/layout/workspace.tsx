"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderClosed,
  Settings2,
  Cpu,
  Menu,
  ArrowUpRight,
  Layers3,
  ShieldCheck,
} from "lucide-react";
import { useWorkspace } from "@/stores/workspace";

const links = [
  { href: "/dashboard", label: "Tổng quan", icon: LayoutDashboard },
  { href: "/projects", label: "Dự án", icon: FolderClosed },
  { href: "/settings", label: "Cài đặt", icon: Settings2 },
];
export function Workspace({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar } = useWorkspace();
  return (
    <div className="workspace">
      <a className="skip-link" href="#main">
        Đến nội dung chính
      </a>
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <Link
          href="/dashboard"
          className="brand"
          aria-label="Fashion AI — Tổng quan"
        >
          <span className="brand-mark">
            <Layers3 size={22} />
          </span>
          <span>
            Fashion<span className="brand-ai">AI</span>
            <small>LOCAL STUDIO</small>
          </span>
        </Link>
        <div className="nav-label">KHÔNG GIAN LÀM VIỆC</div>
        <nav aria-label="Điều hướng chính">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`nav-item ${pathname === href ? "active" : ""}`}
              aria-current={pathname === href ? "page" : undefined}
            >
              <Icon size={18} />
              <span>{label}</span>
              {href !== "/dashboard" && <small>Sắp có</small>}
            </Link>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="small-icon">
            <ShieldCheck size={19} />
          </span>
          <strong>Thiết kế để chạy cục bộ</strong>
          <p>W1 chỉ kiểm tra kết nối. Chưa chọn hoặc mở kho dữ liệu.</p>
          <span className="text-link">
            Nền tảng Web · W1 <ArrowUpRight size={13} />
          </span>
        </div>
        <div className="sidebar-footer">
          <Cpu size={17} />
          <div>
            Máy tính của bạn<small>127.0.0.1 · Local workspace</small>
          </div>
          <span className="tiny-dot" />
        </div>
      </aside>
      <div className="workspace-body">
        <header className="topbar">
          <button
            className="mobile-menu"
            onClick={toggleSidebar}
            aria-label="Mở hoặc đóng điều hướng"
            aria-expanded={sidebarOpen}
          >
            <Menu size={20} />
          </button>
          <span>
            Workspace <span className="breadcrumb-slash">/</span>{" "}
            <strong>
              {links.find((l) => l.href === pathname)?.label ?? "Tổng quan"}
            </strong>
          </span>
          <span className="topbar-badge">
            <ShieldCheck size={14} /> Chỉ trên máy này
          </span>
        </header>
        <main id="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

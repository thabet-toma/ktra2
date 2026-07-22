import React from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowUpLeft, Images, Info, Phone, ShoppingBag } from "lucide-react";
import { LogoIcon } from "../icons/LogoIcon";

const NAV_ITEMS = [
  { to: "/about-us", label: "عن المنصة", icon: Info },
  { to: "/contact", label: "تواصل معنا", icon: Phone },
  { to: "/gallery", label: "المعرض", icon: Images },
];

export const PublicNavbar: React.FC = () => {
  const location = useLocation();

  const linkClass = (path: string) =>
    location.pathname === path
      ? "text-blue-700 bg-blue-50 dark:bg-blue-400/10 dark:text-blue-300"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-white";

  return (
    <nav dir="rtl" className="fixed inset-x-0 top-0 z-50 border-b border-slate-200/70 bg-white/80 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/80">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-5 sm:px-8 lg:px-10">
        <Link to="/" aria-label="العودة إلى الرئيسية" className="group flex shrink-0 items-center gap-3 focus:outline-none focus:ring-4 focus:ring-blue-200 dark:focus:ring-blue-900">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-lg shadow-blue-500/20 transition duration-300 group-hover:-rotate-3 group-hover:scale-105">
            <LogoIcon className="h-6 w-6" />
          </span>
          <span className="hidden sm:block">
            <strong className="block text-lg font-black tracking-[0.18em] text-slate-950 dark:text-white">K.T.R.A</strong>
            <small className="block text-[9px] font-bold text-slate-400">إدارة أعمال متكاملة</small>
          </span>
        </Link>

        <div className="hidden items-center rounded-2xl border border-slate-200/80 bg-slate-50/80 p-1 md:flex dark:border-white/10 dark:bg-white/[0.03]">
          <Link to="/" className={`rounded-xl px-4 py-2.5 text-sm font-bold transition ${linkClass("/")}`}>الرئيسية</Link>
          {NAV_ITEMS.map(({ to, label }) => (
            <Link key={to} to={to} className={`rounded-xl px-4 py-2.5 text-sm font-bold transition ${linkClass(to)}`}>{label}</Link>
          ))}
        </div>

        <Link to="/store" className={`group inline-flex min-h-11 items-center gap-2 rounded-xl border px-3.5 text-sm font-extrabold transition sm:px-4 ${location.pathname === "/store" ? "border-blue-600 bg-blue-600 text-white" : "border-slate-200 bg-white text-slate-700 hover:border-blue-200 hover:text-blue-700 dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:border-blue-400/30 dark:hover:text-blue-300"}`}>
          <ShoppingBag className="h-4 w-4" />
          <span>المتجر</span>
          <ArrowUpLeft className="hidden h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5 group-hover:-translate-y-0.5 sm:block" />
        </Link>
      </div>
    </nav>
  );
};

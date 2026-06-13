export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="url(#g)" strokeWidth="1.4" />
        <circle cx="12" cy="12" r="2.2" fill="#7c5cff" />
        <circle cx="6.5" cy="8" r="1.3" fill="#22d3ee" />
        <circle cx="17" cy="9" r="1.3" fill="#a78bff" />
        <circle cx="15.5" cy="17" r="1.3" fill="#34d399" />
        <path d="M12 12L6.5 8M12 12L17 9M12 12l3.5 5" stroke="#ffffff" strokeOpacity="0.35" strokeWidth="1" />
        <defs>
          <linearGradient id="g" x1="3" y1="3" x2="21" y2="21" gradientUnits="userSpaceOnUse">
            <stop stopColor="#7c5cff" />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-neutral-100">isitme</span>
    </span>
  );
}

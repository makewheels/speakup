// SpeakUp · shared components & icons
// Components are exported to window at the bottom (Babel scope rule).

const { useState, useEffect, useRef, useMemo } = React;

// ─────────────────────────────────────────────────────────────
// ICONS — minimal stroke icons, no emoji
// ─────────────────────────────────────────────────────────────
function Icon({ name, size = 20, color = "currentColor", stroke = 1.6 }) {
  const p = { width: size, height: size, viewBox: "0 0 24 24", fill: "none",
              stroke: color, strokeWidth: stroke, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (name) {
    case "mic":      return <svg {...p}><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>;
    case "stop":     return <svg {...p}><rect x="6" y="6" width="12" height="12" rx="2"/></svg>;
    case "play":     return <svg {...p}><path d="M6 4l14 8-14 8z" fill={color} stroke="none"/></svg>;
    case "home":     return <svg {...p}><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z"/></svg>;
    case "book":     return <svg {...p}><path d="M4 4h12a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z"/><path d="M4 17a3 3 0 0 1 3-3h12"/></svg>;
    case "user":     return <svg {...p}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>;
    case "back":     return <svg {...p}><path d="M15 6l-6 6 6 6"/></svg>;
    case "next":     return <svg {...p}><path d="M9 6l6 6-6 6"/></svg>;
    case "down":     return <svg {...p}><path d="M6 9l6 6 6-6"/></svg>;
    case "up":       return <svg {...p}><path d="M6 15l6-6 6 6"/></svg>;
    case "x":        return <svg {...p}><path d="M6 6l12 12M18 6l-12 12"/></svg>;
    case "check":    return <svg {...p}><path d="M4 12l5 5L20 6"/></svg>;
    case "save":     return <svg {...p}><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>;
    case "saved":    return <svg {...p}><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" fill={color} stroke={color}/></svg>;
    case "refresh":  return <svg {...p}><path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 4v4h-4M21 12a9 9 0 0 1-15 6.7L3 16M3 20v-4h4"/></svg>;
    case "more":     return <svg {...p}><circle cx="6" cy="12" r="1.2" fill={color}/><circle cx="12" cy="12" r="1.2" fill={color}/><circle cx="18" cy="12" r="1.2" fill={color}/></svg>;
    case "spark":    return <svg {...p}><path d="M12 3v6M12 15v6M3 12h6M15 12h6M5.6 5.6l4.2 4.2M14.2 14.2l4.2 4.2M5.6 18.4l4.2-4.2M14.2 9.8l4.2-4.2"/></svg>;
    case "image":    return <svg {...p}><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-5-5-9 8"/></svg>;
    case "chart":    return <svg {...p}><path d="M3 21V8M9 21V4M15 21v-9M21 21v-5"/></svg>;
    case "warn":     return <svg {...p}><path d="M12 4l10 17H2z"/><path d="M12 10v5M12 18v.5"/></svg>;
    case "wave":     return <svg viewBox="0 0 24 24" width={size} height={size}><g fill={color}>
                       <rect x="2" y="10" width="2" height="4" rx="1"/>
                       <rect x="6" y="7" width="2" height="10" rx="1"/>
                       <rect x="10" y="4" width="2" height="16" rx="1"/>
                       <rect x="14" y="8" width="2" height="8" rx="1"/>
                       <rect x="18" y="10" width="2" height="4" rx="1"/>
                       <rect x="22" y="11" width="2" height="2" rx="1"/>
                     </g></svg>;
    default:         return null;
  }
}

// ─────────────────────────────────────────────────────────────
// STATIC iOS-style status bar (we're inside a frame already, this
// is a simple imitation row inside .su-screen)
// ─────────────────────────────────────────────────────────────
function StatusBar({ dark = false, time = "9:41" }) {
  const c = dark ? "#fff" : "#000";
  return (
    <div className="su-status" style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "16px 24px 8px",
    }}>
      <span style={{ fontFamily: "-apple-system, system-ui", fontWeight: 600, fontSize: 15, color: c }}>{time}</span>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <svg width="16" height="11" viewBox="0 0 16 11"><g fill={c}>
          <rect x="0"  y="7" width="2.6" height="4" rx=".6"/>
          <rect x="4"  y="5" width="2.6" height="6" rx=".6"/>
          <rect x="8"  y="3" width="2.6" height="8" rx=".6"/>
          <rect x="12" y="0" width="2.6" height="11" rx=".6"/>
        </g></svg>
        <svg width="24" height="11" viewBox="0 0 24 11">
          <rect x="0.5" y="0.5" width="21" height="10" rx="3" stroke={c} strokeOpacity="0.4" fill="none"/>
          <rect x="2" y="2" width="18" height="7" rx="1.5" fill={c}/>
          <path d="M22 4v3c.6-.2 1-.7 1-1.5S22.6 4.2 22 4z" fill={c} fillOpacity="0.5"/>
        </svg>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// BOTTOM tab bar (3 tabs per spec 4.8)
// ─────────────────────────────────────────────────────────────
function TabBar({ active, dueCount = 0 }) {
  const tabs = [
    { key: "practice", label: "练习",   icon: "home" },
    { key: "mistakes", label: "错题本", icon: "book", badge: dueCount },
    { key: "me",       label: "我的",   icon: "user" },
  ];
  return (
    <nav className="su-tabbar">
      {tabs.map(t => (
        <div key={t.key} className={`su-tab ${active === t.key ? "active" : ""}`}>
          <Icon name={t.icon} size={22} stroke={active === t.key ? 1.9 : 1.5} />
          <span>{t.label}</span>
          {t.badge > 0 && <span className="badge">{t.badge}</span>}
        </div>
      ))}
    </nav>
  );
}

// ─────────────────────────────────────────────────────────────
// IMAGE placeholder
// ─────────────────────────────────────────────────────────────
function ImagePh({ caption = "scene photo", loading = false, height, square = true }) {
  return (
    <div className={"su-img" + (loading ? " loading" : "")}
         style={{ aspectRatio: square ? "1 / 1" : "auto", height }}>
      {!loading && <div className="caption">{caption}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// NAV header (for non-tab-root screens)
// ─────────────────────────────────────────────────────────────
function NavBar({ title, back, right, sub }) {
  return (
    <header className="su-nav">
      <div className="su-nav-side">
        {back && <Icon name="back" size={22} />}
      </div>
      <div style={{ textAlign: "center" }}>
        <h1>{title}</h1>
        {sub && <div style={{ fontFamily: "var(--ff-mono)", fontSize: 10, color: "var(--ink-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginTop: 2 }}>{sub}</div>}
      </div>
      <div className="su-nav-side right">
        {right}
      </div>
    </header>
  );
}

// Frame wrapper — uses IOSDevice from ios-frame, scaled to 375
function Phone({ children, label }) {
  // The ios-frame component sizes from props. We pass 375x812.
  return <IOSDevice width={375} height={812} dark={false}>{children}</IOSDevice>;
}

Object.assign(window, {
  Icon, StatusBar, TabBar, ImagePh, NavBar, Phone,
});

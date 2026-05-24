export default function Icon({ name, size = 20, color = "currentColor", stroke = 1.6 }) {
  const p = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: color,
    strokeWidth: stroke,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
  switch (name) {
    case "mic":
      return (
        <svg {...p}>
          <rect x="9" y="3" width="6" height="12" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      );
    case "stop":
      return (
        <svg {...p}>
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      );
    case "home":
      return (
        <svg {...p}>
          <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z" />
        </svg>
      );
    case "book":
      return (
        <svg {...p}>
          <path d="M4 4h12a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z" />
          <path d="M4 17a3 3 0 0 1 3-3h12" />
        </svg>
      );
    case "user":
      return (
        <svg {...p}>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21a8 8 0 0 1 16 0" />
        </svg>
      );
    case "back":
      return (
        <svg {...p}>
          <path d="M15 6l-6 6 6 6" />
        </svg>
      );
    case "next":
      return (
        <svg {...p}>
          <path d="M9 6l6 6-6 6" />
        </svg>
      );
    case "refresh":
      return (
        <svg {...p}>
          <path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 4v4h-4M21 12a9 9 0 0 1-15 6.7L3 16M3 20v-4h4" />
        </svg>
      );
    case "check":
      return (
        <svg {...p}>
          <path d="M4 12l5 5L20 6" />
        </svg>
      );
    case "save":
      return (
        <svg {...p}>
          <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
        </svg>
      );
    case "spark":
      return (
        <svg {...p}>
          <path d="M12 3v6M12 15v6M3 12h6M15 12h6M5.6 5.6l4.2 4.2M14.2 14.2l4.2 4.2M5.6 18.4l4.2-4.2M14.2 9.8l4.2-4.2" />
        </svg>
      );
    case "warn":
      return (
        <svg {...p}>
          <path d="M12 4l10 17H2z" />
          <path d="M12 10v5M12 18v.5" />
        </svg>
      );
    case "trash":
      return (
        <svg {...p}>
          <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />
        </svg>
      );
    default:
      return null;
  }
}

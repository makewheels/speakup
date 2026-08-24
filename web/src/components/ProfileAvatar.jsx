import { useState } from "react";

export default function ProfileAvatar({ user, alt = "", size = 56, className = "" }) {
  const [failedUrl, setFailedUrl] = useState("");
  const avatarUrl = user?.avatarUrl || "";

  const initial = user?.nickname?.charAt(0)?.toUpperCase() || "U";
  const classes = `profile-avatar${className ? ` ${className}` : ""}`;

  return (
    <span className={classes} style={{ "--profile-avatar-size": `${size}px` }}>
      {avatarUrl && failedUrl !== avatarUrl ? (
        <img src={avatarUrl} alt={alt} onError={() => setFailedUrl(avatarUrl)} />
      ) : (
        <span aria-hidden="true">{initial}</span>
      )}
    </span>
  );
}

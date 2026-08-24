import { useEffect, useRef, useState } from "react";

const VIEWPORT_SIZE = 280;
const OUTPUT_SIZE = 1024;

function clampOffset(offset, natural, scale) {
  const maxX = Math.max(0, (natural.width * scale - VIEWPORT_SIZE) / 2);
  const maxY = Math.max(0, (natural.height * scale - VIEWPORT_SIZE) / 2);
  return {
    x: Math.max(-maxX, Math.min(maxX, offset.x)),
    y: Math.max(-maxY, Math.min(maxY, offset.y)),
  };
}

function croppedFile(image, natural, scale, offset) {
  const sourceSize = VIEWPORT_SIZE / scale;
  const sourceX = (natural.width - sourceSize) / 2 - offset.x / scale;
  const sourceY = (natural.height - sourceSize) / 2 - offset.y / scale;
  const canvas = document.createElement("canvas");
  canvas.width = OUTPUT_SIZE;
  canvas.height = OUTPUT_SIZE;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("Canvas unavailable"));
  context.fillStyle = "#fff";
  context.fillRect(0, 0, OUTPUT_SIZE, OUTPUT_SIZE);
  context.drawImage(
    image,
    sourceX,
    sourceY,
    sourceSize,
    sourceSize,
    0,
    0,
    OUTPUT_SIZE,
    OUTPUT_SIZE,
  );
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) reject(new Error("Unable to crop image"));
      else resolve(new File([blob], "avatar.jpg", { type: "image/jpeg" }));
    }, "image/jpeg", 0.9);
  });
}

export default function AvatarCropDialog({ error = "", file, onCancel, onConfirm, t }) {
  const imageRef = useRef(null);
  const dragRef = useRef(null);
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [busy, setBusy] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const baseScale = natural.width > 0
    ? Math.max(VIEWPORT_SIZE / natural.width, VIEWPORT_SIZE / natural.height)
    : 1;
  const scale = baseScale * zoom;
  const displayWidth = natural.width * scale;
  const displayHeight = natural.height * scale;

  useEffect(() => {
    const reader = new FileReader();
    reader.onload = () => setSourceUrl(String(reader.result || ""));
    reader.readAsDataURL(file);
    return () => reader.readyState === FileReader.LOADING && reader.abort();
  }, [file]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [busy, onCancel]);

  const beginDrag = (event) => {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, offset };
  };
  const moveDrag = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setOffset(clampOffset({
      x: drag.offset.x + event.clientX - drag.x,
      y: drag.offset.y + event.clientY - drag.y,
    }, natural, scale));
  };
  const changeZoom = (event) => {
    const nextZoom = Number(event.target.value);
    setZoom(nextZoom);
    setOffset((current) => clampOffset(current, natural, baseScale * nextZoom));
  };
  const confirm = async () => {
    if (!imageRef.current || !natural.width || busy) return;
    setBusy(true);
    try {
      await onConfirm(await croppedFile(imageRef.current, natural, scale, offset));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="avatar-crop-backdrop" role="presentation">
      <div className="avatar-crop-dialog" role="dialog" aria-modal="true" aria-labelledby="avatar-crop-title">
        <div className="avatar-crop-head">
          <h2 id="avatar-crop-title">{t("profile.cropAvatar")}</h2>
          <p>{t("profile.cropAvatarHint")}</p>
        </div>
        <div
          className="avatar-crop-viewport"
          onPointerDown={beginDrag}
          onPointerMove={moveDrag}
          onPointerUp={() => { dragRef.current = null; }}
          onPointerCancel={() => { dragRef.current = null; }}
        >
          {sourceUrl && (
            <img
              ref={imageRef}
              src={sourceUrl}
              alt={t("profile.cropPreview")}
              draggable="false"
              onLoad={(event) => setNatural({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })}
              style={{
                height: `${displayHeight}px`,
                left: `${(VIEWPORT_SIZE - displayWidth) / 2 + offset.x}px`,
                top: `${(VIEWPORT_SIZE - displayHeight) / 2 + offset.y}px`,
                width: `${displayWidth}px`,
              }}
            />
          )}
          <span className="avatar-crop-ring" aria-hidden="true" />
        </div>
        <label className="avatar-crop-zoom">
          <span>{t("profile.zoomAvatar")}</span>
          <input type="range" min="1" max="3" step="0.01" value={zoom} onChange={changeZoom} />
        </label>
        {error && <p className="avatar-crop-error" role="alert">{error}</p>}
        <div className="avatar-crop-actions">
          <button type="button" className="profile-editor-action-quiet" onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </button>
          <button type="button" className="profile-editor-action-primary" onClick={confirm} disabled={busy || !natural.width}>
            {busy ? t("profile.avatarSaving") : t("profile.saveAvatar")}
          </button>
        </div>
      </div>
    </div>
  );
}

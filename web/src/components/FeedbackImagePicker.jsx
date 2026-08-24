import { useEffect, useId, useMemo, useRef, useState } from "react";

import { useT } from "../i18n/useI18n.js";

const MAX_IMAGES = 9;
const MAX_IMAGE_BYTES = 30 * 1024 * 1024;

export default function FeedbackImagePicker({
  disabled = false,
  existingImages = [],
  files,
  onChange = () => {},
}) {
  const t = useT();
  const inputId = useId();
  const inputRef = useRef(null);
  const [error, setError] = useState("");

  const previews = useMemo(() => files.map((file) => ({
      file,
      url: typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : "",
    })), [files]);

  useEffect(() => (
    () => previews.forEach(({ url }) => { if (url) URL.revokeObjectURL(url); })
  ), [previews]);

  const addFiles = (event) => {
    const selected = Array.from(event.target.files || []);
    event.target.value = "";
    const oversized = selected.find((file) => file.size > MAX_IMAGE_BYTES);
    if (oversized) {
      setError(t("feedback.imageTooLarge"));
      return;
    }
    const available = MAX_IMAGES - existingImages.length - files.length;
    if (selected.length > available) {
      setError(t("feedback.imageLimit", { n: MAX_IMAGES }));
      return;
    }
    setError("");
    onChange([...files, ...selected]);
  };

  const removeFile = (index) => {
    setError("");
    onChange(files.filter((_, fileIndex) => fileIndex !== index));
  };

  return (
    <div className="feedback-images">
      {!disabled && (
        <>
          <input
            ref={inputRef}
            id={inputId}
            className="feedback-image-input"
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif"
            multiple
            onChange={addFiles}
          />
          <button
            className="feedback-image-add"
            type="button"
            onClick={() => inputRef.current?.click()}
          >
            {t("feedback.addImages")}
          </button>
          <span className="feedback-image-hint">{t("feedback.imageHint")}</span>
        </>
      )}
      {(existingImages.length > 0 || previews.length > 0) && (
        <div className="feedback-image-grid">
          {existingImages.map((image) => (
            <figure key={image.id || image.key} className="feedback-image-item is-saved">
              {image.url && <img src={image.url} alt={image.fileName || t("feedback.uploadedImage")} />}
              <figcaption>{image.fileName || t("feedback.uploadedImage")}</figcaption>
            </figure>
          ))}
          {previews.map(({ file, url }, index) => (
            <figure key={`${file.name}-${file.size}-${file.lastModified}`} className="feedback-image-item">
              {url && <img src={url} alt={file.name} />}
              <figcaption>{file.name}</figcaption>
              <button type="button" onClick={() => removeFile(index)} aria-label={t("feedback.removeImage", { name: file.name })}>×</button>
            </figure>
          ))}
        </div>
      )}
      {error && <p className="fb-bar-err" role="alert">{error}</p>}
    </div>
  );
}

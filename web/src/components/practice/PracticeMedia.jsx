import { useState } from "react";

export default function PracticeMedia({ imageUrl = "", videoUrl = "", className = "su-img" }) {
  const [failedImageUrl, setFailedImageUrl] = useState("");
  const [failedVideoUrl, setFailedVideoUrl] = useState("");
  const [loadedVideoUrl, setLoadedVideoUrl] = useState("");
  const showImage = imageUrl && failedImageUrl !== imageUrl;
  const showVideo = videoUrl && failedVideoUrl !== videoUrl;
  const loading = showVideo && loadedVideoUrl !== videoUrl;

  if (showVideo) {
    return (
      <div className={className}>
        <video
          src={videoUrl}
          poster={showImage ? imageUrl : undefined}
          aria-label="scene video"
          muted
          autoPlay
          controls
          playsInline
          onLoadedMetadata={() => setLoadedVideoUrl(videoUrl)}
          onError={() => setFailedVideoUrl(videoUrl)}
        />
        {loading && <div className="media-loading">Loading video...</div>}
      </div>
    );
  }

  if (!showImage) return null;

  return (
    <div className={className}>
      <img src={imageUrl} alt="scene" onError={() => setFailedImageUrl(imageUrl)} />
    </div>
  );
}

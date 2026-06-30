import { useState } from "react";

export default function PracticeMedia({ imageUrl = "", videoUrl = "", className = "su-img" }) {
  const [failedVideoUrl, setFailedVideoUrl] = useState("");
  const [loadedVideoUrl, setLoadedVideoUrl] = useState("");
  const showVideo = videoUrl && failedVideoUrl !== videoUrl;
  const loading = showVideo && loadedVideoUrl !== videoUrl;

  if (showVideo) {
    return (
      <div className={className}>
        <video
          src={videoUrl}
          poster={imageUrl || undefined}
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

  return (
    <div className={className}>
      {imageUrl && <img src={imageUrl} alt="scene" />}
    </div>
  );
}

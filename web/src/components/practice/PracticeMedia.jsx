import { useState } from "react";

export default function PracticeMedia({ imageUrl = "", videoUrl = "", className = "su-img" }) {
  const [failedVideoUrl, setFailedVideoUrl] = useState("");
  const showVideo = videoUrl && failedVideoUrl !== videoUrl;

  if (showVideo) {
    return (
      <div className={className}>
        <video
          src={videoUrl}
          poster={imageUrl || undefined}
          aria-label="scene video"
          muted
          autoPlay
          loop
          playsInline
          onError={() => setFailedVideoUrl(videoUrl)}
        />
      </div>
    );
  }

  return (
    <div className={className}>
      {imageUrl && <img src={imageUrl} alt="scene" />}
    </div>
  );
}

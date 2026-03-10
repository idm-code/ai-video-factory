import React, { useRef } from 'react';

export default function ClipPreview({ url, isImage, autoPlay, onEnded }) {
  const videoRef = useRef(null);

  React.useEffect(() => {
    if (!isImage && videoRef.current) {
      if (autoPlay) {
        videoRef.current.currentTime = 0;
        videoRef.current.play().catch(() => {});
      } else {
        videoRef.current.pause();
      }
    }
  }, [autoPlay, url, isImage]);

  if (!url) return null;

  if (isImage) {
    return (
      <img
        src={url}
        alt="preview"
        style={{ flex: 1, width: '100%', minHeight: 0, objectFit: 'contain', background: '#0e1118', display: 'block' }}
        onError={(e) => { e.target.style.display = 'none'; }}
      />
    );
  }

  return (
    <video
      ref={videoRef}
      key={url}
      src={url}
      controls
      onEnded={onEnded}
      style={{ flex: 1, width: '100%', minHeight: 0, background: '#000', display: 'block' }}
    />
  );
}

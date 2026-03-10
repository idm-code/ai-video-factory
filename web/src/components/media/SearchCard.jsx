import React, { useRef, useState } from 'react';
import { C, S } from '../../constants/theme';

export const dragState = { fromId: null };

export default function SearchCard({ item, onAdd, adding }) {
  const isVid = item.media_type !== 'image';
  const clickedRef = useRef(false);
  const [videoError, setVideoError] = useState(false);

  // Pixabay bloquea el streaming directo; si falla o no hay preview fiable, usar thumb
  const showVideoPlayer = isVid && !videoError && !!item.preview_url;

  return (
    <div
      draggable
      onDragStart={(e) => {
        dragState.fromId = null;
        e.dataTransfer.effectAllowed = 'copy';
        try { e.dataTransfer.setData('application/x-search-item', JSON.stringify(item)); } catch {}
      }}
      style={{
        background: C.panel2,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        overflow: 'hidden',
        opacity: adding ? 0.6 : 1,
      }}
    >
      {showVideoPlayer ? (
        <video
          muted
          preload="metadata"
          src={item.preview_url}
          onError={() => setVideoError(true)}
          style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block', pointerEvents: 'none' }}
        />
      ) : (
        <img
          src={item.thumb_url || item.preview_url || ''}
          alt={item.provider}
          style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block' }}
          onError={(e) => { e.target.style.background = '#1a1e27'; e.target.src = ''; }}
        />
      )}

      <div style={{ padding: '5px 7px' }}>
        <div style={{ fontSize: 10, color: C.muted }}>
          {item.provider} · {item.media_type} · {Number(item.duration || 0).toFixed(1)}s
        </div>
        <button
          disabled={adding}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (adding || clickedRef.current) return;
            clickedRef.current = true;
            onAdd(item).finally(() => { clickedRef.current = false; });
          }}
          style={{
            ...S.btnAccent,
            width: '100%',
            marginTop: 4,
            padding: '3px',
            fontSize: 11,
            opacity: adding ? 0.5 : 1,
            pointerEvents: adding ? 'none' : 'auto',
          }}
        >
          {adding ? '...' : '+ Timeline'}
        </button>
      </div>
    </div>
  );
}

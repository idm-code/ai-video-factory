import React from 'react';
import { C, S, fmtTime } from '../../constants/theme';
import { dragState } from '../media/SearchCard';

function TinyBtn({ children, onClick, title, danger }) {
  return (
    <button
      title={title}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      style={{
        background: 'none', border: 'none', cursor: 'pointer', padding: '0 3px', fontSize: 11,
        color: danger ? C.danger : C.muted, lineHeight: 1,
      }}
    >
      {children}
    </button>
  );
}

export default function TimelineClip({ clip, idx, selected, totalEnabledSecs, onSelect, onRemove, onToggle, onMoveLeft, onMoveRight, onReorder }) {
  const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(clip.path || '');
  const disabled = clip.enabled === false;
  const pct = totalEnabledSecs > 0 ? (Number(clip.duration || 4) / totalEnabledSecs) * 100 : 10;

  function handleDragStart(e) {
    dragState.fromId = clip.id;
    e.dataTransfer.setData('text/plain', clip.id);
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDrop(e) {
    e.preventDefault();
    const fromId = dragState.fromId;
    if (fromId && fromId !== clip.id) {
      onReorder(fromId, clip.id);
    }
    dragState.fromId = null;
  }

  function handleDragOver(e) {
    if (dragState.fromId) e.preventDefault();
  }

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onClick={(e) => onSelect(clip.id, e.shiftKey || e.ctrlKey || e.metaKey)}
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        width: `${Math.max(pct, 5)}%`,
        minWidth: 54,
        height: 48,
        background: selected ? '#1e3a5f' : disabled ? '#1a1c21' : '#1e2736',
        border: `1px solid ${selected ? C.accent : disabled ? '#2a2d36' : C.border}`,
        borderRadius: 4,
        cursor: 'pointer',
        overflow: 'hidden',
        flexShrink: 0,
        position: 'relative',
        transition: 'background 0.1s, border-color 0.1s',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {/* waveform decoration */}
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 10, display: 'flex', alignItems: 'flex-end', gap: 1, padding: '0 2px', opacity: 0.3 }}>
        {Array.from({ length: Math.min(24, Math.max(4, Math.floor(pct * 0.6))) }, (_, i) => (
          <div key={i} style={{ flex: 1, background: isImage ? '#e7d84f' : C.accent, borderRadius: 1, height: `${20 + Math.sin(i * 2.3 + idx) * 50 + 30}%` }} />
        ))}
      </div>
      <div style={{ padding: '3px 4px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', position: 'relative', zIndex: 1 }}>
        <span style={{ fontSize: 9, color: disabled ? C.muted : '#c8d4ea', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
          {isImage ? '🖼' : '🎬'} {clip.name}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 9, color: C.muted }}>{fmtTime(clip.duration || 0)}</span>
          <div style={{ display: 'flex', gap: 0 }}>
            <TinyBtn title="Mover izq" onClick={onMoveLeft}>‹</TinyBtn>
            <TinyBtn title="Mover der" onClick={onMoveRight}>›</TinyBtn>
            <TinyBtn title={disabled ? 'Activar' : 'Desactivar'} onClick={onToggle}>●</TinyBtn>
            <TinyBtn title="Eliminar" onClick={onRemove} danger>×</TinyBtn>
          </div>
        </div>
      </div>
    </div>
  );
}

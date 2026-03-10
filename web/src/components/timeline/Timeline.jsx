import React from 'react';
import { C, S, fmtTime } from '../../constants/theme';
import TimelineClip from './TimelineClip';
import { dragState } from '../media/SearchCard';

function TrackLabel({ label }) {
  return (
    <div style={{ width: 28, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: C.muted, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
      {label}
    </div>
  );
}

export default function Timeline({
  clips, totalSecs, enabledSecs, selectedIds, hasAudio, hasSubs,
  onSelect, onRemove, onToggle, onMoveLeft, onMoveRight, onReorder, onClear, onDropFromLibrary,
  audioName, subsName,
}) {
  function handleTrackDrop(e) {
    e.preventDefault();
    // Si viene de librería
    if (!dragState.fromId) {
      const raw = e.dataTransfer.getData('application/x-search-item');
      if (raw) {
        try { onDropFromLibrary(JSON.parse(raw)); } catch { }
      }
    }
    dragState.fromId = null;
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = dragState.fromId ? 'move' : 'copy';
  }

  return (
    <div style={S.timeline}>
      {/* Stats row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 8px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <span style={{ fontSize: 10, color: C.muted }}>
          {clips.length} clips · {fmtTime(totalSecs)} total · {fmtTime(enabledSecs)} activo
        </span>
        <div style={{ flex: 1 }} />
        {clips.length > 0 && (
          <button onClick={onClear} style={{ ...S.btn, padding: '2px 8px', fontSize: 10, color: C.danger, borderColor: C.danger }}>
            🗑 Limpiar
          </button>
        )}
      </div>

      {/* V1 track */}
      <div style={{ display: 'flex', alignItems: 'center', minHeight: 60, borderBottom: `1px solid ${C.border}` }}>
        <TrackLabel label="V1" />
        <div
          onDrop={handleTrackDrop}
          onDragOver={handleDragOver}
          style={{ flex: 1, display: 'flex', gap: 3, alignItems: 'center', padding: '4px 6px', minHeight: 56, overflowX: 'auto' }}
        >
          {clips.length === 0
            ? <span style={{ fontSize: 11, color: C.muted }}>Arrastra clips aquí o usa + Timeline</span>
            : clips.map((c, i) => (
              <TimelineClip
                key={c.id}
                clip={c}
                idx={i}
                selected={selectedIds.has(c.id)}
                totalEnabledSecs={enabledSecs || totalSecs || 1}
                onSelect={onSelect}
                onRemove={() => onRemove(c.id)}
                onToggle={() => onToggle(c.id)}
                onMoveLeft={() => onMoveLeft(c.id)}
                onMoveRight={() => onMoveRight(c.id)}
                onReorder={onReorder}
              />
            ))
          }
        </div>
      </div>

      {/* A1 track */}
      <div style={{ display: 'flex', alignItems: 'center', height: 36, borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <TrackLabel label="A1" />
        <div style={{ flex: 1, padding: '0 8px', display: 'flex', alignItems: 'center' }}>
          {hasAudio
            ? <div style={{ background: '#1a2e1a', border: `1px solid ${C.ok}`, borderRadius: 4, padding: '2px 8px', fontSize: 10, color: C.ok }}>
                ♪ {audioName || 'voice.mp3'}
              </div>
            : <span style={{ fontSize: 10, color: C.muted }}>Sin audio · Generar arriba</span>}
        </div>
      </div>

      {/* S1 track */}
      <div style={{ display: 'flex', alignItems: 'center', height: 36, flexShrink: 0 }}>
        <TrackLabel label="S1" />
        <div style={{ flex: 1, padding: '0 8px', display: 'flex', alignItems: 'center' }}>
          {hasSubs
            ? <div style={{ background: '#2a2a16', border: '1px solid #e7d84f', borderRadius: 4, padding: '2px 8px', fontSize: 10, color: '#e7d84f' }}>
                ◉ {subsName || 'subtitles.srt'}
              </div>
            : <span style={{ fontSize: 10, color: C.muted }}>Sin subtítulos · Generar arriba</span>}
        </div>
      </div>
    </div>
  );
}

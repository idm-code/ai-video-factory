import React, { useMemo, useState } from 'react';
import { C, S, fmtTime } from '../../constants/theme';
import TimelineClip from './TimelineClip';
import { dragState } from '../media/SearchCard';

function TrackLabel({ label }) {
  return <div style={S.trackLabel}>{label}</div>;
}

function fmtSignedDelta(seconds) {
  const sign = seconds > 0 ? '+' : seconds < 0 ? '-' : '±';
  return `${sign}${fmtTime(Math.abs(seconds || 0))}`;
}

export default function Timeline({
  clips, totalSecs, enabledSecs, selectedIds, hasAudio, hasSubs,
  onSelect, onRemove, onToggle, onMoveLeft, onMoveRight, onReorder, onClear, onDropFromLibrary,
  audioName, subsName, audioPath, audioOffsetSeconds, onAudioOffsetChange, audioRev,
}) {
  const [audioSeconds, setAudioSeconds] = useState(0);
  const audioUrl = useMemo(
    () => audioPath
      ? `/api/clip?path=${encodeURIComponent(audioPath)}&rev=${encodeURIComponent(audioRev || '')}`
      : '',
    [audioPath, audioRev]
  );
  const delta = Number(audioSeconds || 0) - Number(enabledSecs || 0);

  function handleTrackDrop(e) {
    e.preventDefault();
    if (!dragState.fromId) {
      const raw = e.dataTransfer.getData('application/x-search-item');
      if (raw) {
        try { onDropFromLibrary(JSON.parse(raw)); } catch {}
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
              ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'stretch', minHeight: 66, borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <TrackLabel label="A1" />
        <div style={{ flex: 1, padding: '6px 8px', display: 'grid', gap: 6 }}>
          {hasAudio && audioUrl ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <audio
                  key={audioUrl}
                  controls
                  preload="metadata"
                  src={audioUrl}
                  onLoadedMetadata={(e) => {
                    const d = Number(e.currentTarget.duration || 0);
                    setAudioSeconds(Number.isFinite(d) ? d : 0);
                  }}
                  style={{ width: '100%', maxWidth: 420, height: 30 }}
                />
                <div style={{ background: '#1a2e1a', border: `1px solid ${C.ok}`, borderRadius: 4, padding: '2px 8px', fontSize: 10, color: C.ok }}>
                  ♪ {audioName || 'voice.mp3'}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, color: C.muted }}>Timeline: {fmtTime(enabledSecs)}</span>
                <span style={{ fontSize: 10, color: C.muted }}>Audio: {fmtTime(audioSeconds)}</span>
                <span style={{ fontSize: 10, color: Math.abs(delta) > 2 ? C.danger : C.ok }}>
                  Delta: {fmtSignedDelta(delta)}
                </span>
                <label style={{ fontSize: 10, color: C.muted }}>
                  Offset audio (s)
                  <input
                    type="number"
                    step="0.1"
                    value={audioOffsetSeconds ?? 0}
                    onChange={(e) => onAudioOffsetChange(Number(e.target.value || 0))}
                    style={{ ...S.input, width: 76, marginLeft: 6 }}
                  />
                </label>
              </div>
            </>
          ) : (
            <span style={{ fontSize: 10, color: C.muted }}>Sin audio · Generar arriba</span>
          )}
        </div>
      </div>

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

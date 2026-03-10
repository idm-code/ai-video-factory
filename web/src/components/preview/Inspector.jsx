import React from 'react';
import { C, S, fmtTime } from '../../constants/theme';

export default function Inspector({ clip, onUpdate }) {
  if (!clip) return null;
  return (
    <div style={{ padding: '8px 12px', background: '#13161c', borderTop: '1px solid #252b38', flexShrink: 0 }}>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        Inspector: {clip.name}
      </div>
      <div style={{ display: 'flex', gap: 12 }}>
        <label style={{ fontSize: 11, color: C.muted }}>
          Duración (s)
          <input
            type="number" min="1" max="600" step="0.5"
            value={clip.duration ?? 4}
            onChange={(e) => onUpdate(clip.id, { duration: Number(e.target.value) })}
            style={{ ...S.input, width: 70, marginLeft: 6 }}
          />
        </label>
        <label style={{ fontSize: 11, color: C.muted }}>
          Inicio (s)
          <input
            type="number" min="0" step="0.5"
            value={clip.start ?? 0}
            onChange={(e) => onUpdate(clip.id, { start: Number(e.target.value) })}
            style={{ ...S.input, width: 70, marginLeft: 6 }}
          />
        </label>
        <span style={{ fontSize: 10, color: C.muted, alignSelf: 'center' }}>
          {fmtTime(clip.duration || 0)}
        </span>
      </div>
    </div>
  );
}

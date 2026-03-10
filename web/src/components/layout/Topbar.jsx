import React from 'react';
import { C, S } from '../../constants/theme';

export default function Topbar({ busy, canRender, hasAudio, hasSubs, status, onSave, onGenAudio, onGenSubs, onRender }) {
  return (
    <div style={S.topbar}>
      <span style={{ fontWeight: 700, fontSize: 13, color: C.accent, marginRight: 8 }}>▶ AI Video Editor</span>
      <button style={S.btn} onClick={onSave} disabled={busy}>Guardar</button>
      <button style={S.btn} onClick={onGenAudio} disabled={busy}>Generar audio</button>
      <button style={S.btn} onClick={onGenSubs} disabled={busy}>Generar subs</button>
      {canRender && (
        <button style={S.btnOk} onClick={onRender} disabled={busy}>
          🎬 Render video
        </button>
      )}
      <div style={{ flex: 1 }} />
      {hasAudio && <span style={{ fontSize: 11, color: C.ok }}>♪ Audio</span>}
      {hasSubs && <span style={{ fontSize: 11, color: '#e7d84f' }}>◉ Subs</span>}
      <span style={{
        fontSize: 12,
        color: status.type === 'ok' ? C.ok : status.type === 'err' ? C.danger : C.muted,
        marginLeft: 8,
      }}>
        {status.msg}
      </span>
    </div>
  );
}

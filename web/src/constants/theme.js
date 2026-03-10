export const C = {
  bg: '#0d0f12', panel: '#13161c', panel2: '#1a1e27', border: '#252b38',
  accent: '#2ea8ff', ok: '#19c37d', danger: '#ff5b6b', text: '#e7ecf5',
  muted: '#6b7a94', trackBg: '#0f1218', clipGrad1: '#1e3a5f', clipGrad2: '#1a3352',
};

export const S = {
  app: { display: 'grid', gridTemplateColumns: '280px 1fr', gridTemplateRows: '42px 1fr 200px', height: '100vh', background: C.bg, color: C.text, fontFamily: 'Inter,Segoe UI,Arial,sans-serif', fontSize: 13, overflow: 'hidden' },
  topbar: { gridColumn: '1/-1', background: C.panel, borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px' },
  sidebar: { background: C.panel, borderRight: `1px solid ${C.border}`, overflowY: 'auto', display: 'flex', flexDirection: 'column' },
  main: { background: C.bg, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  timeline: { gridColumn: '1/-1', background: C.trackBg, borderTop: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  btn: { background: C.panel2, border: `1px solid ${C.border}`, color: C.text, borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap' },
  btnAccent: { background: C.accent, border: 'none', color: '#fff', borderRadius: 6, padding: '5px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 600 },
  btnOk: { background: C.ok, border: 'none', color: '#fff', borderRadius: 6, padding: '5px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  btnDanger: { background: 'transparent', border: `1px solid ${C.danger}`, color: C.danger, borderRadius: 6, padding: '5px 10px', cursor: 'pointer', fontSize: 12 },
  input: { background: '#0d0f12', border: `1px solid ${C.border}`, color: C.text, borderRadius: 6, padding: '5px 8px', fontSize: 12, width: '100%', outline: 'none', boxSizing: 'border-box' },
  label: { fontSize: 11, color: C.muted, marginBottom: 3, display: 'block' },
  section: { borderBottom: `1px solid ${C.border}`, padding: '10px 12px' },
  sectionTitle: { fontSize: 10, color: C.muted, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 },
  trackRow: { display: 'flex', alignItems: 'stretch', borderBottom: `1px solid ${C.border}`, height: 54, flexShrink: 0 },
  trackLabel: { width: 44, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: C.muted, fontWeight: 700, background: C.panel, borderRight: `1px solid ${C.border}` },
  trackLane: { flex: 1, overflowX: 'auto', display: 'flex', alignItems: 'center', gap: 3, padding: '4px 8px' },
};

export function fmtTime(s) {
  s = Math.max(0, Number(s || 0));
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

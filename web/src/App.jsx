import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getTimeline, saveTimeline, searchMedia, importMediaToTimeline, generateAudio, generateSubtitles } from './api';

const C = {
  bg: '#0d0f12', panel: '#13161c', panel2: '#1a1e27', border: '#252b38',
  accent: '#2ea8ff', ok: '#19c37d', danger: '#ff5b6b', text: '#e7ecf5',
  muted: '#6b7a94', trackBg: '#0f1218', clipGrad1: '#1e3a5f', clipGrad2: '#1a3352',
  clipSelected: '#2ea8ff',
};

const S = {
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

function fmtTime(s) {
  s = Math.max(0, Number(s || 0));
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function TinyBtn({ onClick, children, color, title }) {
  return (
    <button onClick={onClick} title={title} style={{ background: 'rgba(255,255,255,0.08)', border: 'none', color: color || C.muted, borderRadius: 3, width: 16, height: 16, cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0, lineHeight: 1, flexShrink: 0 }}>
      {children}
    </button>
  );
}

// ── Drag reorder dentro del timeline ──
const dragState = { fromId: null };

function TimelineClip({ clip, index, selected, onSelect, onRemove, onToggle, onMoveLeft, onMoveRight, totalDuration, onDropReorder }) {
  const pct = Math.max(4, (Number(clip.duration || 4) / Math.max(totalDuration, 1)) * 100);
  const isDisabled = clip.enabled === false;
  const w = Math.max(90, pct * 7);

  return (
    <div
      draggable
      onDragStart={(e) => { dragState.fromId = clip.id; e.dataTransfer.effectAllowed = 'move'; }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (dragState.fromId && dragState.fromId !== clip.id) { onDropReorder(dragState.fromId, clip.id); dragState.fromId = null; } }}
      onClick={(e) => onSelect(clip.id, e.ctrlKey || e.metaKey)}
      title={clip.name}
      style={{
        flexShrink: 0, width: `${w}px`, height: 42,
        background: selected ? 'linear-gradient(135deg,#1a4a7f,#153a6a)' : `linear-gradient(135deg,${C.clipGrad1},${C.clipGrad2})`,
        border: `1px solid ${selected ? C.accent : isDisabled ? C.border : '#2a4a6e'}`,
        borderRadius: 6, display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        padding: '3px 6px', cursor: 'grab', opacity: isDisabled ? 0.4 : 1,
        position: 'relative', userSelect: 'none', overflow: 'hidden',
      }}
    >
      <div style={{ position: 'absolute', inset: 0, opacity: 0.1, pointerEvents: 'none' }}>
        {[...Array(Math.min(16, Math.ceil(w / 6)))].map((_, i) => (
          <div key={i} style={{ position: 'absolute', left: `${(i / 16) * 100}%`, bottom: 0, width: 2, height: `${14 + Math.sin(i * 1.9) * 10}px`, background: C.accent, borderRadius: 1 }} />
        ))}
      </div>
      <div style={{ fontSize: 10, color: selected ? C.accent : C.text, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', zIndex: 1 }}>
        {clip.name || `clip_${index + 1}`}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 1 }}>
        <span style={{ fontSize: 9, color: C.muted }}>{Number(clip.duration || 0).toFixed(1)}s</span>
        <div style={{ display: 'flex', gap: 2 }} onClick={(e) => e.stopPropagation()}>
          <TinyBtn onClick={() => onMoveLeft(clip.id)} title="Mover izq">‹</TinyBtn>
          <TinyBtn onClick={() => onMoveRight(clip.id)} title="Mover der">›</TinyBtn>
          <TinyBtn onClick={() => onToggle(clip.id)} color={isDisabled ? C.ok : C.muted} title={isDisabled ? 'Habilitar' : 'Deshabilitar'}>{isDisabled ? '●' : '○'}</TinyBtn>
          <TinyBtn onClick={() => onRemove(clip.id)} color={C.danger} title="Eliminar">×</TinyBtn>
        </div>
      </div>
    </div>
  );
}

function SearchCard({ item, onAdd, adding }) {
  const isVid = item.media_type !== 'image';
  const clickedRef = useRef(false);
  return (
    <div
      draggable
      onDragStart={(e) => {
        dragState.fromId = null; // reset timeline drag
        e.dataTransfer.effectAllowed = 'copy';
        try { e.dataTransfer.setData('application/x-search-item', JSON.stringify(item)); } catch {}
      }}
      style={{ background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden', opacity: adding ? 0.6 : 1 }}
    >
      {isVid
        ? <video muted preload="metadata" src={item.preview_url}
            style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block', pointerEvents: 'none' }} />
        : <img src={item.thumb_url || item.preview_url} alt=""
            style={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', display: 'block', pointerEvents: 'none' }} />
      }
      <div style={{ padding: '5px 7px' }}>
        <div style={{ fontSize: 10, color: C.muted }}>{item.provider} · {Number(item.duration || 0).toFixed(1)}s</div>
        <button
          disabled={adding}
          onClick={(e) => {
            e.preventDefault(); e.stopPropagation();
            if (adding || clickedRef.current) return;
            clickedRef.current = true;
            onAdd(item).finally(() => { clickedRef.current = false; });
          }}
          style={{ ...S.btnAccent, width: '100%', marginTop: 4, padding: '3px', fontSize: 11, opacity: adding ? 0.5 : 1, pointerEvents: adding ? 'none' : 'auto' }}
        >
          {adding ? '...' : '+ Timeline'}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  // ── State ──
  const [timeline, setTimeline] = useState({ clips: [], script_text: '', target_minutes: 8, voice_path: '', srt_path: '' });
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searchPage, setSearchPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [status, setStatus] = useState({ msg: 'Listo', type: '' });
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [addingId, setAddingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const addingRef = useRef(null);
  const loaderRef = useRef(null);

  const toast = (msg, type = '') => setStatus({ msg, type });

  // ── Reload completo desde servidor ──
  async function reload() {
    const data = await getTimeline();
    // Normalizar: el servidor puede devolver clips con clave "clip_path" en vez de "path"
    const clips = (data.clips || []).map((c) => ({
      ...c,
      path: c.path || c.clip_path || '',
    }));
    setTimeline({ ...data, clips });
  }

  useEffect(() => { reload().catch((e) => toast(`Error: ${e.message}`, 'err')); }, []);

  // ── Computed ──
  const totalSecs = useMemo(() => (timeline.clips || []).reduce((a, c) => a + Number(c.duration || 0), 0), [timeline.clips]);
  const enabledSecs = useMemo(() => (timeline.clips || []).filter((c) => c.enabled !== false).reduce((a, c) => a + Number(c.duration || 0), 0), [timeline.clips]);
  const hasAudio = !!(timeline.voice_path || timeline.audio?.name);
  const hasSubs = !!(timeline.srt_path || timeline.subtitles?.name);
  const canRender = (timeline.clips || []).length > 0 && hasAudio && hasSubs;

  const previewUrl = useMemo(() => {
    if (selectedIds.size !== 1) return null;
    const clip = (timeline.clips || []).find((c) => c.id === [...selectedIds][0]);
    if (!clip?.path) return null;
    return `/api/clip?path=${encodeURIComponent(clip.path)}`;
  }, [selectedIds, timeline.clips]);

  // ── Search ──
  const searchTimerRef = useRef(null);
  const [searchType, setSearchType] = useState('video');
  const [searchProviders, setSearchProviders] = useState('pexels,pixabay');
  const [searchOrientation, setSearchOrientation] = useState('any');

  function triggerSearch(value, page = 1) {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(async () => {
      const q2 = (value || '').trim();
      if (!q2 || q2.length < 2) return;
      const perPage = Number(document.getElementById('perPageSelect')?.value || 16);
      toast('Buscando...');
      try {
        const data = await searchMedia({
          q: q2,
          type: searchType,
          providers: searchProviders,
          page,
          per_page: perPage,
          orientation: searchOrientation,
          min_duration: 0,
          max_duration: 0,
        });
        const items = data.items || [];
        setResults((prev) => page === 1 ? items : [...prev, ...items]);
        setHasMore(data.has_more ?? items.length >= perPage);
        setSearchPage(page);
        toast(`${page === 1 ? items.length : 'más'} resultados`);
      } catch (e) { toast(`Error búsqueda: ${e.message}`, 'err'); }
    }, page === 1 ? 400 : 0);
  }

  // Auto-search con debounce
  useEffect(() => {
    if (q.trim().length > 2) triggerSearch(q, 1);
  }, [q]);

  // Infinite scroll con IntersectionObserver
  useEffect(() => {
    if (!loaderRef.current) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !busy) {
        triggerSearch(q, searchPage + 1);
      }
    }, { threshold: 0.1 });
    obs.observe(loaderRef.current);
    return () => obs.disconnect();
  }, [hasMore, searchPage, q, busy]);

  // ── Add clip: mutex global ──
  async function onAdd(item) {
    const key = `${item.provider}-${item.id}`;
    if (addingRef.current) return;
    addingRef.current = key;
    setAddingId(key);
    toast('Importando clip...');
    try {
      const data = await importMediaToTimeline(item);
      const clip = data?.clip;
      if (!clip) throw new Error('Sin clip en respuesta');
      setTimeline((t) => ({
        ...t,
        clips: [...(t.clips || []), {
          id: clip.id,
          name: clip.name,
          path: clip.path || clip.clip_path || '',
          start: Number(clip.start || 0),
          duration: Math.max(1, Number(clip.duration || 4)),
          enabled: clip.enabled !== false,
        }],
      }));
      toast('Clip añadido ✓', 'ok');
    } catch (e) { toast(`Error: ${e.message}`, 'err'); }
    finally { addingRef.current = null; setAddingId(null); }
  }

  // ── Timeline ops ──
  function selectClip(id, multi) {
    setSelectedIds((prev) => {
      const next = new Set(multi ? prev : []);
      if (prev.has(id) && !multi) next.delete(id); else next.add(id);
      return next;
    });
  }

  function removeClip(id) {
    setTimeline((t) => ({ ...t, clips: (t.clips || []).filter((c) => c.id !== id) }));
    setSelectedIds((prev) => { const n = new Set(prev); n.delete(id); return n; });
  }

  function toggleClip(id) {
    setTimeline((t) => ({ ...t, clips: (t.clips || []).map((c) => c.id === id ? { ...c, enabled: c.enabled === false } : c) }));
  }

  function moveClip(id, dir) {
    setTimeline((t) => {
      const clips = [...(t.clips || [])];
      const i = clips.findIndex((c) => c.id === id);
      if (i < 0) return t;
      const j = i + dir;
      if (j < 0 || j >= clips.length) return t;
      [clips[i], clips[j]] = [clips[j], clips[i]];
      return { ...t, clips };
    });
  }

  // Drag reorder dentro del timeline
  function reorderClips(fromId, toId) {
    setTimeline((t) => {
      const clips = [...(t.clips || [])];
      const from = clips.findIndex((c) => c.id === fromId);
      const to = clips.findIndex((c) => c.id === toId);
      if (from < 0 || to < 0) return t;
      const [item] = clips.splice(from, 1);
      clips.splice(to, 0, item);
      return { ...t, clips };
    });
  }

  // ── Save: envía clips actuales al servidor ──
  async function onSave() {
    setBusy(true); toast('Guardando...');
    try {
      await saveTimeline({ clips: timeline.clips || [], script_text: timeline.script_text || '' });
      toast('Guardado ✓', 'ok');
    } catch (e) { toast(`Error: ${e.message}`, 'err'); }
    finally { setBusy(false); }
  }

  // ── Generar audio: guarda primero, luego genera, luego recarga ──
  async function onGenAudio() {
    setBusy(true); toast('Guardando y generando audio...');
    try {
      // 1. Persistir clips actuales
      await saveTimeline({ clips: timeline.clips || [], script_text: timeline.script_text || '' });
      // 2. Generar audio
      await generateAudio({ topic: q.trim() || timeline.topic || 'video', script_text: timeline.script_text || '', tts_provider: 'gtts', voice: 'en', speech_rate: '+0%' });
      // 3. Recargar para obtener voice_path/srt_path actualizados
      await reload();
      toast('Audio listo ✓', 'ok');
    } catch (e) { toast(`Error audio: ${e.message}`, 'err'); }
    finally { setBusy(false); }
  }

  // ── Generar subtítulos: guarda primero, luego genera, luego recarga ──
  async function onGenSubs() {
    setBusy(true); toast('Guardando y generando subtítulos...');
    try {
      await saveTimeline({ clips: timeline.clips || [], script_text: timeline.script_text || '' });
      await generateSubtitles({ script_text: timeline.script_text || '' });
      await reload();
      toast('Subtítulos listos ✓', 'ok');
    } catch (e) { toast(`Error subs: ${e.message}`, 'err'); }
    finally { setBusy(false); }
  }

  // ── Render final ──
  async function onRender() {
    setBusy(true); toast('Guardando y renderizando...');
    try {
      await saveTimeline({ clips: timeline.clips || [], script_text: timeline.script_text || '' });
      const res = await fetch('/api/render', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      if (!res.ok) { const txt = await res.text(); throw new Error(txt); }
      await reload();
      toast('¡Render completado ✓!', 'ok');
    } catch (e) { toast(`Error render: ${e.message}`, 'err'); }
    finally { setBusy(false); }
  }

  const selectedClip = selectedIds.size === 1 ? (timeline.clips || []).find((c) => c.id === [...selectedIds][0]) : null;

  return (
    <div style={S.app}>

      {/* ── Topbar ── */}
      <div style={S.topbar}>
        <span style={{ fontWeight: 700, fontSize: 13, color: C.accent, marginRight: 8 }}>▶ AI Video Editor</span>
        <button style={S.btn} onClick={onSave} disabled={busy}>Guardar</button>
        <button style={S.btn} onClick={onGenAudio} disabled={busy}>Generar audio</button>
        <button style={S.btn} onClick={onGenSubs} disabled={busy}>Generar subs</button>
        {/* ── BOTÓN RENDER: solo visible cuando hay clips + audio + subs ── */}
        {canRender && (
          <button style={S.btnOk} onClick={onRender} disabled={busy}>
            🎬 Render video
          </button>
        )}
        <div style={{ flex: 1 }} />
        {hasAudio && <span style={{ fontSize: 11, color: C.ok }}>♪ Audio</span>}
        {hasSubs && <span style={{ fontSize: 11, color: '#e7d84f' }}>◉ Subs</span>}
        <span style={{ fontSize: 12, color: status.type === 'ok' ? C.ok : status.type === 'err' ? C.danger : C.muted, marginLeft: 8 }}>
          {status.msg}
        </span>
      </div>

      {/* ── Sidebar ── */}
      <div style={S.sidebar}>
        <div style={S.section}>
          <div style={S.sectionTitle}>Script</div>
          <textarea
            value={timeline.script_text || ''}
            onChange={(e) => setTimeline((t) => ({ ...t, script_text: e.target.value }))}
            placeholder="Escribe o genera el guion..."
            style={{ ...S.input, minHeight: 90, resize: 'vertical', fontFamily: 'ui-monospace,monospace', fontSize: 11, lineHeight: 1.5 }}
          />
        </div>

        <div style={S.section}>
          <div style={S.sectionTitle}>Buscar media</div>

          {/* Barra de búsqueda */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && triggerSearch(q, 1)}
              placeholder="Buscar clips..."
              style={S.input}
            />
            <button style={S.btnAccent} onClick={() => triggerSearch(q, 1)}>↵</button>
          </div>

          {/* Filtros en grid 2x2 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
            <div>
              <label style={S.label}>Tipo</label>
              <select
                value={searchType}
                onChange={(e) => setSearchType(e.target.value)}
                style={{ ...S.input, padding: '4px 6px' }}
              >
                <option value="video">Video</option>
                <option value="image">Imagen</option>
              </select>
            </div>
            <div>
              <label style={S.label}>Fuente</label>
              <select
                value={searchProviders}
                onChange={(e) => setSearchProviders(e.target.value)}
                style={{ ...S.input, padding: '4px 6px' }}
              >
                <option value="pexels,pixabay">Pexels + Pixabay</option>
                <option value="pexels">Solo Pexels</option>
                <option value="pixabay">Solo Pixabay</option>
              </select>
            </div>
            <div>
              <label style={S.label}>Orientación</label>
              <select
                value={searchOrientation}
                onChange={(e) => setSearchOrientation(e.target.value)}
                style={{ ...S.input, padding: '4px 6px' }}
              >
                <option value="any">Cualquiera</option>
                <option value="landscape">Horizontal</option>
                <option value="portrait">Vertical</option>
                <option value="square">Cuadrada</option>
              </select>
            </div>
            <div>
              <label style={S.label}>Resultados/pág</label>
              <select
                onChange={(e) => {/* se usa en triggerSearch via per_page */}}
                style={{ ...S.input, padding: '4px 6px' }}
                defaultValue="16"
                id="perPageSelect"
              >
                <option value="8">8</option>
                <option value="16">16</option>
                <option value="32">32</option>
              </select>
            </div>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {results.map((r) => (
              <SearchCard
                key={`${r.provider}-${r.id}`}
                item={r}
                onAdd={onAdd}
                adding={addingId === `${r.provider}-${r.id}`}
              />
            ))}
          </div>
          {/* Trigger infinite scroll */}
          <div ref={loaderRef} style={{ height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {hasMore && <span style={{ color: C.muted, fontSize: 11 }}>Cargando más...</span>}
            {!hasMore && results.length === 0 && <span style={{ color: C.muted, fontSize: 11 }}>Busca clips para añadir</span>}
          </div>
        </div>
      </div>

      {/* ── Main: Preview + Inspector ── */}
      <div style={S.main}>
        {previewUrl
          ? <video key={previewUrl} src={previewUrl} controls style={{ width: '100%', flex: 1, minHeight: 0, background: '#000', display: 'block' }} />
          : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.muted, fontSize: 13 }}>
              {(timeline.clips || []).length === 0 ? 'Añade clips desde el panel izquierdo' : 'Selecciona un clip para previsualizarlo'}
            </div>
        }

        {selectedClip && (
          <div style={{ background: C.panel, borderTop: `1px solid ${C.border}`, padding: '8px 16px', flexShrink: 0 }}>
            <div style={{ ...S.sectionTitle, marginBottom: 6 }}>Inspector · {selectedClip.name}</div>
            <div style={S.grid2}>
              <div>
                <label style={S.label}>Duración (s)</label>
                <input type="number" min={1} step={0.1} style={S.input}
                  value={Number(selectedClip.duration || 4).toFixed(1)}
                  onChange={(e) => setTimeline((t) => ({ ...t, clips: t.clips.map((c) => c.id === selectedClip.id ? { ...c, duration: Math.max(1, Number(e.target.value)) } : c) }))} />
              </div>
              <div>
                <label style={S.label}>Inicio (s)</label>
                <input type="number" min={0} step={0.1} style={S.input}
                  value={Number(selectedClip.start || 0).toFixed(1)}
                  onChange={(e) => setTimeline((t) => ({ ...t, clips: t.clips.map((c) => c.id === selectedClip.id ? { ...c, start: Math.max(0, Number(e.target.value)) } : c) }))} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Timeline ── */}
      <div style={S.timeline}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 10px', borderBottom: `1px solid ${C.border}`, background: C.panel, flexShrink: 0 }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, letterSpacing: '0.08em' }}>TIMELINE</span>
          <span style={{ fontSize: 11, color: C.muted }}>
            {(timeline.clips || []).length} clips · {totalSecs.toFixed(1)}s ({fmtTime(totalSecs)}) · habilitados: {enabledSecs.toFixed(1)}s ({fmtTime(enabledSecs)})
          </span>
          <div style={{ flex: 1 }} />
          <button style={S.btnDanger} onClick={() => { setTimeline((t) => ({ ...t, clips: [] })); setSelectedIds(new Set()); }}>Vaciar</button>
        </div>

        {/* V1: acepta drops desde biblioteca Y reordena internamente */}
        <div style={S.trackRow}>
          <div style={S.trackLabel}>V1</div>
          <div
            style={S.trackLane}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              // Drop desde biblioteca (SearchCard)
              try {
                const raw = e.dataTransfer.getData('application/x-search-item');
                if (raw) { onAdd(JSON.parse(raw)); return; }
              } catch {}
              // Drop reorder (aterrizó en el lane vacío, no en un clip)
              dragState.fromId = null;
            }}
          >
            {(timeline.clips || []).length === 0
              ? <span style={{ color: C.muted, fontSize: 11 }}>Arrastra clips aquí o usa "+ Timeline"</span>
              : (timeline.clips || []).map((clip, i) => (
                  <TimelineClip
                    key={clip.id || i}
                    clip={clip}
                    index={i}
                    selected={selectedIds.has(clip.id)}
                    onSelect={selectClip}
                    onRemove={removeClip}
                    onToggle={toggleClip}
                    onMoveLeft={(id) => moveClip(id, -1)}
                    onMoveRight={(id) => moveClip(id, 1)}
                    totalDuration={totalSecs}
                    onDropReorder={reorderClips}
                  />
                ))
            }
          </div>
        </div>

        {/* A1 */}
        <div style={S.trackRow}>
          <div style={S.trackLabel}>A1</div>
          <div style={S.trackLane}>
            {hasAudio
              ? <div style={{ height: 34, minWidth: 120, background: 'linear-gradient(135deg,#1a3a2a,#152e22)', border: `1px solid #2a5a3a`, borderRadius: 6, padding: '4px 10px', fontSize: 11, color: C.ok, display: 'flex', alignItems: 'center', gap: 6 }}>
                  ♪ {timeline.audio?.name || 'voice.mp3'}
                </div>
              : <span style={{ color: C.muted, fontSize: 11 }}>Sin audio — pulsa "Generar audio"</span>
            }
          </div>
        </div>

        {/* S1 */}
        <div style={{ ...S.trackRow, borderBottom: 'none' }}>
          <div style={S.trackLabel}>S1</div>
          <div style={S.trackLane}>
            {hasSubs
              ? <div style={{ height: 34, minWidth: 120, background: 'linear-gradient(135deg,#2a2a1a,#222212)', border: `1px solid #5a5a2a`, borderRadius: 6, padding: '4px 10px', fontSize: 11, color: '#e7d84f', display: 'flex', alignItems: 'center', gap: 6 }}>
                  ◉ {timeline.subtitles?.name || 'subtitles.srt'}
                </div>
              : <span style={{ color: C.muted, fontSize: 11 }}>Sin subtítulos — pulsa "Generar subs"</span>
            }
          </div>
        </div>
      </div>
    </div>
  );
}

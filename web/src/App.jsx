import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { generateAudio, generateSubtitles, importMediaToTimeline, renderFinal } from './api';
import { S } from './constants/theme';
import { useTimeline } from './hooks/useTimeline';
import { useSearch } from './hooks/useSearch';
import { useTimelinePlayer } from './hooks/useTimelinePlayer';
import Topbar from './components/layout/Topbar';
import Sidebar from './components/layout/Sidebar';
import ClipPreview from './components/preview/ClipPreview';
import Inspector from './components/preview/Inspector';
import Timeline from './components/timeline/Timeline';

export default function App() {
  const [status, setStatus] = useState({ msg: 'Listo', type: '' });
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [addingId, setAddingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const addingRef = useRef(null);
  const toast = useCallback((msg, type = '') => setStatus({ msg, type }), []);

  const tl = useTimeline(toast);
  const search = useSearch(toast);
  const player = useTimelinePlayer(tl.enabledClips, (id) => setSelectedIds(new Set([id])));

  useEffect(() => { tl.reload(); }, []);

  const selectedClip = useMemo(() =>
    selectedIds.size === 1 ? (tl.timeline.clips || []).find((c) => c.id === [...selectedIds][0]) : null,
    [selectedIds, tl.timeline.clips]);

  const previewUrl = useMemo(() => {
    if (!selectedClip?.path) return null;
    return `/api/clip?path=${encodeURIComponent(selectedClip.path)}`;
  }, [selectedClip]);

  const previewIsImage = useMemo(() =>
    /\.(jpg|jpeg|png|gif|webp)$/i.test(selectedClip?.path || ''), [selectedClip]);

  function selectClip(id, multi) {
    setSelectedIds((prev) => {
      const next = new Set(multi ? prev : []);
      if (prev.has(id) && !multi) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function onAdd(item) {
    const key = `${item.provider}-${item.id}`;
    if (addingRef.current) return;
    addingRef.current = key; setAddingId(key); toast('Importando clip...');
    try {
      const data = await importMediaToTimeline(item);
      if (!data?.clip) throw new Error('Sin clip en respuesta');
      tl.addClip(data.clip); toast('Clip añadido ✓', 'ok');
    } catch (e) { toast(`Error: ${e.message}`, 'err'); }
    finally { addingRef.current = null; setAddingId(null); }
  }

  async function onSave() {
    setBusy(true); toast('Guardando...');
    try { await tl.save(); toast('Guardado ✓', 'ok'); }
    catch (e) { toast(`Error: ${e.message}`, 'err'); }
    finally { setBusy(false); }
  }

  async function onGenAudio() {
    setBusy(true);
    toast('Generando audio...');
    try {
      await tl.save();
      await generateAudio({
        topic: search.q.trim() || tl.timeline.topic || 'video',
        script_text: tl.timeline.script_text || '',
        voice: 'en',
        voice_speed: Number(tl.timeline.voice_speed || 1.0),
      });
      await tl.reload();
      toast('Audio listo ✓', 'ok');
    } catch (e) {
      toast(`Error audio: ${e.message}`, 'err');
    } finally {
      setBusy(false);
    }
  }

  async function onGenSubs() {
    setBusy(true); toast('Generando subtítulos...');
    try {
      await tl.save();
      await generateSubtitles({ script_text: tl.timeline.script_text || '' });
      await tl.reload(); toast('Subtítulos listos ✓', 'ok');
    } catch (e) { toast(`Error subs: ${e.message}`, 'err'); }
    finally { setBusy(false); }
  }

  async function onRender() {
    setBusy(true);
    toast('Renderizando...');
    try {
      await tl.save();
      await renderFinal();
      await tl.reload();
      toast('¡Render completado ✓!', 'ok');
    } catch (e) {
      toast(`Error render: ${e.message}`, 'err');
    } finally {
      setBusy(false);
    }
  }

  const [clipboardCount, setClipboardCount] = useState(0);
  const clipboardRef = useRef([]);

  const makeClipId = useCallback(
    () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : `clip_${Date.now()}_${Math.random().toString(16).slice(2)}`),
    []
  );

  const copyClips = useCallback((mode = 'selected') => {
    const all = tl.timeline.clips || [];
    const source = mode === 'all' ? all : all.filter((c) => selectedIds.has(c.id));
    if (!source.length) {
      toast(mode === 'all' ? 'No hay clips para copiar' : 'Selecciona al menos un clip', 'err');
      return;
    }
    clipboardRef.current = source.map((c) => ({
      name: c.name,
      path: c.path || c.clip_path || '',
      start: Number(c.start || 0),
      duration: Math.max(1, Number(c.duration || 4)),
      enabled: c.enabled !== false,
    }));
    setClipboardCount(clipboardRef.current.length);
    toast(`${clipboardRef.current.length} clip(s) copiados ✓`, 'ok');
  }, [tl.timeline.clips, selectedIds, toast]);

  const pasteClips = useCallback(() => {
    const payload = clipboardRef.current || [];
    if (!payload.length) {
      toast('Portapapeles vacío', 'err');
      return;
    }

    const selectedNow = new Set(selectedIds);
    let insertedIds = [];

    tl.setTimeline((t) => {
      const clips = [...(t.clips || [])];
      const selectedIndexes = clips
        .map((c, i) => (selectedNow.has(c.id) ? i : -1))
        .filter((i) => i >= 0);
      const insertAt = selectedIndexes.length ? Math.max(...selectedIndexes) + 1 : clips.length;

      const clones = payload.map((c) => ({ ...c, id: makeClipId() }));
      insertedIds = clones.map((c) => c.id);

      return {
        ...t,
        clips: [...clips.slice(0, insertAt), ...clones, ...clips.slice(insertAt)],
      };
    });

    setSelectedIds(new Set(insertedIds));
    toast(`${payload.length} clip(s) pegados ✓`, 'ok');
  }, [selectedIds, tl, makeClipId, toast]);

  useEffect(() => {
    function isEditableTarget(el) {
      const tag = (el?.tagName || '').toLowerCase();
      return tag === 'input' || tag === 'textarea' || el?.isContentEditable;
    }

    function onKeyDown(e) {
      if (!(e.ctrlKey || e.metaKey) || isEditableTarget(e.target)) return;
      const key = String(e.key || '').toLowerCase();
      if (key === 'c') {
        e.preventDefault();
        copyClips('selected');
      } else if (key === 'v') {
        e.preventDefault();
        pasteClips();
      } else if (key === 'a' && e.shiftKey) {
        // Ctrl/Cmd+Shift+A => copiar todos
        e.preventDefault();
        copyClips('all');
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [copyClips, pasteClips]);

  return (
    <div style={S.app}>
      <Topbar
        busy={busy} canRender={tl.canRender} hasAudio={tl.hasAudio} hasSubs={tl.hasSubs}
        status={status} onSave={onSave} onGenAudio={onGenAudio} onGenSubs={onGenSubs} onRender={onRender}
        voiceSpeed={tl.timeline.voice_speed || 1.0}
        onVoiceSpeedChange={tl.setVoiceSpeed}
      />
      <Sidebar
        scriptText={tl.timeline.script_text}
        onScriptChange={tl.setScriptText}
        searchProps={search}
        results={search.results}
        loaderRef={search.loaderRef}
        hasMore={search.hasMore}
        addingId={addingId}
        onAdd={onAdd}
      />
      <div style={S.main}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', background: '#13161c', borderBottom: '1px solid #252b38', flexShrink: 0 }}>
          {player.playing
            ? <button style={{ ...S.btnDanger, padding: '3px 12px' }} onClick={player.stop}>⏹ Detener</button>
            : <button style={{ ...S.btnAccent, padding: '3px 12px' }} onClick={player.start} disabled={tl.enabledClips.length === 0}>▶ Reproducir timeline</button>}
          {player.playing && (
            <span style={{ fontSize: 11, color: '#6b7a94' }}>
              Clip {player.currentIdx + 1}/{tl.enabledClips.length} · {tl.enabledClips[player.currentIdx]?.name}
            </span>
          )}
        </div>
        {previewUrl
          ? <ClipPreview url={previewUrl} isImage={previewIsImage} autoPlay={player.playing} onEnded={player.playing ? player.advance : undefined} />
          : <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7a94', fontSize: 13 }}>
              {(tl.timeline.clips || []).length === 0 ? 'Añade clips desde el panel izquierdo' : 'Selecciona un clip para previsualizarlo'}
            </div>}
        <Inspector clip={selectedClip} onUpdate={tl.updateClip} />
      </div>
      <Timeline
        clips={tl.timeline.clips || []}
        totalSecs={tl.totalSecs}
        enabledSecs={tl.enabledSecs}
        selectedIds={selectedIds}
        hasAudio={tl.hasAudio}
        hasSubs={tl.hasSubs}
        onSelect={selectClip}
        onRemove={(id) => { tl.removeClip(id); setSelectedIds((p) => { const n = new Set(p); n.delete(id); return n; }); }}
        onToggle={tl.toggleClip}
        onMoveLeft={(id) => tl.moveClip(id, -1)}
        onMoveRight={(id) => tl.moveClip(id, 1)}
        onReorder={tl.reorderClips}
        onClear={() => { tl.clearClips(); setSelectedIds(new Set()); }}
        onDropFromLibrary={onAdd}
        audioName={tl.timeline.audio?.name}
        subsName={tl.timeline.subtitles?.name}
        audioPath={tl.timeline.voice_path}
        audioOffsetSeconds={tl.timeline.audio_offset_seconds || 0}
        onAudioOffsetChange={tl.setAudioOffset}
        selectedCount={selectedIds.size}
        canPaste={clipboardCount > 0}
        onCopySelected={() => copyClips('selected')}
        onCopyAll={() => copyClips('all')}
        onPaste={pasteClips}
      />
    </div>
  );
}

import { useState, useMemo, useCallback } from 'react';
import { getTimeline, saveTimeline } from '../api';

const EMPTY_TIMELINE = {
  clips: [], script_text: '', target_minutes: 8, voice_path: '', srt_path: '',
};

export function useTimeline(toast) {
  const [timeline, setTimeline] = useState(EMPTY_TIMELINE);

  const reload = useCallback(async () => {
    try {
      const data = await getTimeline();
      const clips = (data.clips || []).map((c) => ({ ...c, path: c.path || c.clip_path || '' }));
      setTimeline({ ...data, clips });
    } catch (e) {
      toast(`Error cargando: ${e.message}`, 'err');
    }
  }, [toast]);

  const save = useCallback(async () => {
    await saveTimeline({
      clips: timeline.clips || [],
      script_text: timeline.script_text || '',
    });
  }, [timeline]);

  const addClip = useCallback((clip) => {
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
  }, []);

  const removeClip = useCallback((id) => {
    setTimeline((t) => ({ ...t, clips: (t.clips || []).filter((c) => c.id !== id) }));
  }, []);

  const toggleClip = useCallback((id) => {
    setTimeline((t) => ({
      ...t,
      clips: (t.clips || []).map((c) => c.id === id ? { ...c, enabled: c.enabled === false } : c),
    }));
  }, []);

  const moveClip = useCallback((id, dir) => {
    setTimeline((t) => {
      const clips = [...(t.clips || [])];
      const i = clips.findIndex((c) => c.id === id);
      if (i < 0) return t;
      const j = i + dir;
      if (j < 0 || j >= clips.length) return t;
      [clips[i], clips[j]] = [clips[j], clips[i]];
      return { ...t, clips };
    });
  }, []);

  const reorderClips = useCallback((fromId, toId) => {
    setTimeline((t) => {
      const clips = [...(t.clips || [])];
      const from = clips.findIndex((c) => c.id === fromId);
      const to = clips.findIndex((c) => c.id === toId);
      if (from < 0 || to < 0) return t;
      const [item] = clips.splice(from, 1);
      clips.splice(to, 0, item);
      return { ...t, clips };
    });
  }, []);

  const updateClip = useCallback((id, changes) => {
    setTimeline((t) => ({
      ...t,
      clips: (t.clips || []).map((c) => c.id === id ? { ...c, ...changes } : c),
    }));
  }, []);

  const clearClips = useCallback(() => {
    setTimeline((t) => ({ ...t, clips: [] }));
  }, []);

  const setScriptText = useCallback((text) => {
    setTimeline((t) => ({ ...t, script_text: text }));
  }, []);

  const totalSecs = useMemo(() =>
    (timeline.clips || []).reduce((a, c) => a + Number(c.duration || 0), 0),
    [timeline.clips]
  );
  const enabledSecs = useMemo(() =>
    (timeline.clips || []).filter((c) => c.enabled !== false).reduce((a, c) => a + Number(c.duration || 0), 0),
    [timeline.clips]
  );
  const enabledClips = useMemo(() =>
    (timeline.clips || []).filter((c) => c.enabled !== false),
    [timeline.clips]
  );
  const hasAudio = !!(timeline.voice_path || timeline.audio?.name);
  const hasSubs = !!(timeline.srt_path || timeline.subtitles?.name);
  const canRender = (timeline.clips || []).length > 0 && hasAudio && hasSubs;

  return {
    timeline, setTimeline,
    reload, save,
    addClip, removeClip, toggleClip, moveClip, reorderClips, updateClip, clearClips,
    setScriptText,
    totalSecs, enabledSecs, enabledClips,
    hasAudio, hasSubs, canRender,
  };
}

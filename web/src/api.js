const jsonHeaders = { 'Content-Type': 'application/json' };

async function parse(res) {
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTimeline() {
  const res = await fetch(`/api/timeline?_ts=${Date.now()}`, { cache: 'no-store' });
  return parse(res);
}

export async function saveTimeline(payload) {
  const res = await fetch('/api/timeline', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return parse(res);
}

export async function searchMedia(params) {
  const query = new URLSearchParams(params);
  const res = await fetch(`/api/media/search?${query.toString()}`);
  return parse(res);
}

export async function importMediaToTimeline(item) {
  const res = await fetch('/api/media/import', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      item,
      add_to_timeline: true,
      image_seconds: 6,
    }),
  });
  return parse(res);
}

export async function generateAudio(payload) {
  const res = await fetch('/api/audio/generate', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return parse(res);
}

export async function generateSubtitles(payload) {
  const res = await fetch('/api/subtitles/generate', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return parse(res);
}

export async function generateScript(payload) {
  const res = await fetch('/api/script/generate', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return parse(res);
}

export async function generateProject(payload) {
  const res = await fetch('/api/project/generate', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return parse(res);
}

export async function renderFinal() {
  const res = await fetch('/api/render', {
    method: 'POST',
  });
  return parse(res);
}

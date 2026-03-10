import { useRef, useState, useEffect, useCallback } from 'react';
import { searchMedia } from '../api';

export function useSearch(toast) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searchPage, setSearchPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [searchType, setSearchType] = useState('video');
  const [searchProviders, setSearchProviders] = useState('pexels,pixabay');
  const [searchOrientation, setSearchOrientation] = useState('any');
  const [perPage, setPerPage] = useState(16);
  const [busy, setBusy] = useState(false);
  const loaderRef = useRef(null);
  const searchTimerRef = useRef(null);

  const triggerSearch = useCallback((value, page = 1) => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(async () => {
      const q2 = (value || '').trim();
      if (!q2 || q2.length < 2) return;
      setBusy(true);
      toast('Buscando...');
      try {
        const data = await searchMedia({
          q: q2, type: searchType, providers: searchProviders,
          page, per_page: perPage, orientation: searchOrientation,
          min_duration: 0, max_duration: 0,
        });
        const items = data.items || [];
        setResults((prev) => page === 1 ? items : [...prev, ...items]);
        setHasMore(data.has_more ?? items.length >= perPage);
        setSearchPage(page);
        toast(`${page === 1 ? items.length : 'más'} resultados`);
      } catch (e) {
        toast(`Error búsqueda: ${e.message}`, 'err');
      } finally {
        setBusy(false);
      }
    }, page === 1 ? 400 : 0);
  }, [searchType, searchProviders, searchOrientation, perPage, toast]);

  // Re-buscar al cambiar filtros o query
  useEffect(() => {
    if (q.trim().length > 2) triggerSearch(q, 1);
  }, [q, searchType, searchProviders, searchOrientation]);

  // Infinite scroll
  useEffect(() => {
    if (!loaderRef.current) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore && !busy) {
        triggerSearch(q, searchPage + 1);
      }
    }, { threshold: 0.1 });
    obs.observe(loaderRef.current);
    return () => obs.disconnect();
  }, [hasMore, searchPage, q, busy, triggerSearch]);

  return {
    q, setQ,
    results,
    searchPage, hasMore,
    searchType, setSearchType,
    searchProviders, setSearchProviders,
    searchOrientation, setSearchOrientation,
    perPage, setPerPage,
    loaderRef,
    triggerSearch,
    searchBusy: busy,
  };
}

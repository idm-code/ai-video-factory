import React from 'react';
import { C, S } from '../../constants/theme';
import SearchFilters from '../media/SearchFilters';
import SearchCard from '../media/SearchCard';

export default function Sidebar({ scriptText, onScriptChange, searchProps, results, loaderRef, hasMore, addingId, onAdd }) {
  const { q, setQ, triggerSearch, searchType, setSearchType, searchProviders, setSearchProviders, searchOrientation, setSearchOrientation, perPage, setPerPage } = searchProps;

  return (
    <div style={S.sidebar}>
      {/* Script */}
      <div style={{ padding: '6px 8px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ fontSize: 10, color: C.muted, marginBottom: 3, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>Script</div>
        <textarea
          value={scriptText || ''}
          onChange={(e) => onScriptChange(e.target.value)}
          placeholder="Escribe el script del vídeo aquí..."
          rows={4}
          style={{ ...S.input, width: '100%', resize: 'vertical', fontSize: 11, fontFamily: 'inherit' }}
        />
      </div>

      {/* Search */}
      <div style={{ padding: '6px 8px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ fontSize: 10, color: C.muted, marginBottom: 3, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>Buscar media</div>
        <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
          <input
            value={q}
            onChange={(e) => { setQ(e.target.value); triggerSearch(e.target.value, 1); }}
            placeholder="Buscar vídeos / imágenes..."
            style={{ ...S.input, flex: 1 }}
            onKeyDown={(e) => e.key === 'Enter' && triggerSearch(q, 1)}
          />
          <button style={S.btn} onClick={() => triggerSearch(q, 1)}>▶</button>
        </div>
        <SearchFilters
          searchType={searchType} setSearchType={setSearchType}
          searchProviders={searchProviders} setSearchProviders={setSearchProviders}
          searchOrientation={searchOrientation} setSearchOrientation={setSearchOrientation}
          perPage={perPage} setPerPage={setPerPage}
        />
      </div>

      {/* Results */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {results.map((item) => (
            <SearchCard
              key={`${item.provider}-${item.id}`}
              item={item}
              addingId={addingId}
              onAdd={onAdd}
            />
          ))}
        </div>
        {hasMore && (
          <div ref={loaderRef} style={{ textAlign: 'center', padding: 8, fontSize: 11, color: C.muted }}>
            Cargando más...
          </div>
        )}
        {results.length === 0 && (
          <div style={{ textAlign: 'center', padding: 20, fontSize: 11, color: C.muted }}>
            Busca vídeos o imágenes arriba
          </div>
        )}
      </div>
    </div>
  );
}

import React from 'react';
import { S } from '../../constants/theme';

const sel = (val, onChange, opts) => (
  <select value={val} onChange={(e) => onChange(e.target.value)} style={S.select}>
    {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
  </select>
);

export default function SearchFilters({ searchType, setSearchType, searchProviders, setSearchProviders, searchOrientation, setSearchOrientation, perPage, setPerPage }) {
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', padding: '4px 2px' }}>
      {sel(searchType, setSearchType, [['video', 'Video'], ['image', 'Imagen']])}
      {sel(searchProviders, setSearchProviders, [
        ['pexels,pixabay', 'Pexels+Pixabay'],
        ['pexels', 'Solo Pexels'],
        ['pixabay', 'Solo Pixabay'],
      ])}
      {sel(searchOrientation, setSearchOrientation, [
        ['any', 'Orientación'],
        ['landscape', 'Landscape'],
        ['portrait', 'Portrait'],
        ['square', 'Cuadrado'],
      ])}
      {sel(perPage, (v) => setPerPage(Number(v)), [
        [8, '8/pág'], [16, '16/pág'], [32, '32/pág'],
      ])}
    </div>
  );
}

import React from 'react';

export default function Catalog({
  catalog,
  newCanonical,
  setNewCanonical,
  newAliases,
  setNewAliases,
  editingId,
  editCanonical,
  setEditCanonical,
  editAliases,
  setEditAliases,
  suggestions,
  loadingSuggestions,
  onLoadSuggestions,
  onAcceptSuggestion,
  onIgnoreSuggestion,
  onAddCatalogItem,
  onImportBaseCatalog,
  onSaveBaseCatalog,
  onDeleteCatalogItem,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  baseCatalogs = ["Материа Медика (По умолчанию)"],
  selectedBaseCatalog = "Материа Медика (По умолчанию)",
  onSelectBaseCatalog
}) {
  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Title block */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h3 style={{ fontSize: '1.45rem', fontFamily: 'var(--font-display)' }}>Каталог сопоставления препаратов</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '4px' }}>
            Канонические названия лекарств и их возможные варианты написания (синонимы) в прайсах дистрибьюторов.
          </p>
        </div>
      </div>

      {/* Toolbar row with uniform height, width, and spacing */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        flexWrap: 'wrap', 
        gap: '12px',
        padding: '16px',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid var(--border-light)',
        borderRadius: '12px'
      }}>
        {/* Left: Add Form */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
          <input 
            type="text" 
            placeholder="Препарат (напр. Эргоферон)" 
            value={newCanonical}
            onChange={(e) => setNewCanonical(e.target.value)}
            style={{ 
              width: '240px', 
              height: '42px',
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              background: 'rgba(255, 255, 255, 0.05)',
              color: '#fff',
              fontSize: '0.9rem',
              outline: 'none'
            }}
          />
          <input 
            type="text" 
            placeholder="Синонимы (через запятую)" 
            value={newAliases}
            onChange={(e) => setNewAliases(e.target.value)}
            style={{ 
              width: '280px', 
              height: '42px',
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              background: 'rgba(255, 255, 255, 0.05)',
              color: '#fff',
              fontSize: '0.9rem',
              outline: 'none'
            }}
          />
          <button 
            className="btn btn-primary"
            onClick={onAddCatalogItem}
            style={{ 
              width: '240px',
              height: '42px', 
              whiteSpace: 'nowrap', 
              flexShrink: 0 
            }}
          >
            ➕ Добавить
          </button>
        </div>

        {/* Right: Base Catalogs Actions - Uniform size */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value={selectedBaseCatalog}
            onChange={(e) => onSelectBaseCatalog(e.target.value)}
            style={{
              height: '42px',
              width: '240px',
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              background: 'rgba(255, 255, 255, 0.05)',
              color: '#fff',
              fontSize: '0.9rem',
              outline: 'none',
              cursor: 'pointer',
              flexShrink: 0
            }}
          >
            {baseCatalogs.map((name, idx) => (
              <option key={idx} value={name} style={{ background: '#12131a', color: '#fff' }}>
                {name}
              </option>
            ))}
          </select>
          <button 
            className="btn btn-secondary"
            style={{ 
              height: '42px',
              width: '240px',
              background: 'linear-gradient(135deg, var(--accent-secondary) 0%, #7c3aed 100%)', 
              color: '#fff', 
              border: 'none',
              whiteSpace: 'nowrap',
              flexShrink: 0
            }}
            onClick={onImportBaseCatalog}
            title="Импортировать выбранный базовый каталог"
          >
            📥 Импорт
          </button>
          <button 
            className="btn btn-secondary"
            style={{ 
              height: '42px',
              width: '240px',
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)', 
              color: '#fff', 
              border: 'none',
              whiteSpace: 'nowrap',
              flexShrink: 0
            }}
            onClick={onSaveBaseCatalog}
            title="Сохранить текущие синонимы и канонические названия как новые базовые"
          >
            💾 Сохранить как базовый
          </button>
        </div>
      </div>

      {/* Suggestions Box */}
      <div style={{ 
        border: '1px solid rgba(129, 140, 248, 0.2)', 
        background: 'rgba(129, 140, 248, 0.02)', 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '12px',
        padding: '16px',
        borderRadius: '12px',
        marginTop: '8px',
        marginBottom: '16px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h4 style={{ margin: 0, color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.95rem' }}>
            💡 Автоматические предложения синонимов (из загруженных прайсов)
          </h4>
          <button 
            className="btn btn-secondary" 
            style={{ padding: '6px 12px', fontSize: '0.8rem' }} 
            onClick={onLoadSuggestions} 
            disabled={loadingSuggestions}
          >
            {loadingSuggestions ? '🔄 Анализ...' : '🔄 Анализировать прайсы'}
          </button>
        </div>

        {loadingSuggestions ? (
          <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            ⏳ Анализируем прайс-листы и сопоставляем с каталогом, пожалуйста подождите...
          </div>
        ) : suggestions.length > 0 ? (
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', 
            gap: '12px',
            maxHeight: '220px',
            overflowY: 'auto',
            padding: '4px'
          }}>
            {suggestions.map((s, idx) => (
              <div key={idx} style={{ 
                background: 'rgba(255, 255, 255, 0.02)', 
                border: '1px solid var(--border-light)', 
                borderRadius: '8px', 
                padding: '10px 12px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: '8px'
              }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <span style={{ fontWeight: '600', color: 'var(--text-primary)', fontSize: '0.9rem' }}>
                      {s.suggested_alias}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--accent-secondary)', fontWeight: '600' }}>
                      {s.confidence_score}%
                    </span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    Препарат: <strong style={{ color: '#fff' }}>{s.canonical_name}</strong>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                  <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: '0.75rem' }} onClick={() => onAcceptSuggestion(s)}>
                    ✅ Добавить
                  </button>
                  <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '0.75rem', borderColor: 'transparent' }} onClick={() => onIgnoreSuggestion(s.suggested_alias)}>
                    ❌ Скрыть
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Нет новых предложений синонимов. Загрузите файлы прайсов и нажмите «Анализировать прайсы» выше.
          </div>
        )}
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th style={{ width: '30%' }}>Каноническое название препарата</th>
              <th>Синонимы и варианты написания в прайс-листах</th>
              <th style={{ width: '180px' }}>Действия</th>
            </tr>
          </thead>
          <tbody>
            {catalog.map(item => {
              const isEditing = editingId === item.id;
              return (
                <tr key={item.id}>
                  {isEditing ? (
                    <>
                      <td>
                        <input
                          type="text"
                          value={editCanonical}
                          onChange={(e) => setEditCanonical(e.target.value)}
                          style={{ padding: '6px 10px', fontSize: '0.9rem' }}
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={editAliases}
                          onChange={(e) => setEditAliases(e.target.value)}
                          style={{ padding: '6px 10px', fontSize: '0.9rem' }}
                          placeholder="Синонимы через запятую"
                        />
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            className="btn btn-primary"
                            style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                            onClick={() => onSaveEdit(item.id)}
                          >
                            💾 Сохр.
                          </button>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                            onClick={onCancelEdit}
                          >
                            ❌ Отм.
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td style={{ fontWeight: '600', color: '#fff' }}>{item.canonical}</td>
                      <td>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                          {item.aliases.map((alias, idx) => (
                            <span 
                              key={idx} 
                              style={{ 
                                backgroundColor: 'rgba(255,255,255,0.05)', 
                                border: '1px solid rgba(255,255,255,0.1)', 
                                borderRadius: '4px', 
                                padding: '2px 8px', 
                                fontSize: '0.8rem',
                                color: 'var(--text-secondary)'
                              }}
                            >
                              {alias}
                            </span>
                          ))}
                          {item.aliases.length === 0 && (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic' }}>Нет синонимов</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                            onClick={() => onStartEdit(item)}
                          >
                            ✏️ Изменить
                          </button>
                          <button 
                            className="btn btn-danger" 
                            style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                            onClick={() => onDeleteCatalogItem(item.id)}
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
            {catalog.length === 0 && (
              <tr>
                <td colSpan="3" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                  Каталог пуст. Добавьте лекарства сверху.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

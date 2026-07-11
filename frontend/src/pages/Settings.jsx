import React from 'react';

export default function Settings({
  columns,
  producers,
  newProducer,
  setNewProducer,
  useCatalogMatching,
  legacyPriorityRules,
  clearInputsAfterProcessing,
  onAddCandidate,
  onRemoveCandidate,
  onAddProducer,
  onRemoveProducer,
  onToggleCatalogMatching,
  onToggleLegacyRules,
  onToggleClearInputs
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '24px' }}>
      {/* Column Candidates */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <h3>Кандидаты названий колонок в Excel</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          Поиск табличных данных в прайсах происходит автоматически по совпадению названий заголовков из следующих списков.
        </p>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {Object.keys(columns).map(columnKey => (
            <div key={columnKey} style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: '16px', alignItems: 'center' }}>
              <label style={{ fontWeight: '500', fontSize: '0.9rem', textTransform: 'capitalize' }}>
                {columnKey
                  .replace('_candidates', '')
                  .replace('key', 'ID/Артикул')
                  .replace('name', 'Наименование')
                  .replace('price', 'Цена')
                  .replace('stock', 'Наличие')
                  .replace('producer', 'Производитель')}:
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                {columns[columnKey].map((candidate, idx) => (
                  <span 
                    key={idx} 
                    style={{ 
                      backgroundColor: 'rgba(129, 140, 248, 0.08)', 
                      border: '1px solid rgba(129, 140, 248, 0.3)', 
                      borderRadius: '6px', 
                      padding: '4px 10px', 
                      fontSize: '0.8rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
                  >
                    {candidate}
                    <span 
                      style={{ cursor: 'pointer', color: 'var(--accent-error)', fontWeight: 'bold' }}
                      onClick={() => onRemoveCandidate(columnKey, idx)}
                    >
                      ×
                    </span>
                  </span>
                ))}
                
                <input 
                  type="text" 
                  placeholder="+ Добавить"
                  style={{ width: '110px', padding: '4px 8px', fontSize: '0.8rem' }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.target.value.trim()) {
                      onAddCandidate(columnKey, e.target.value.trim());
                      e.target.value = '';
                    }
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Producers & General Toggles */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Producers Filter */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h3>Фильтр производителей</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
            Только препараты этих производителей будут перенесены в итоговые отчеты.
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {producers.map((prod, idx) => (
              <span 
                key={idx} 
                style={{ 
                  backgroundColor: 'rgba(192, 132, 252, 0.08)', 
                  border: '1px solid rgba(192, 132, 252, 0.3)', 
                  borderRadius: '6px', 
                  padding: '4px 10px', 
                  fontSize: '0.8rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                {prod}
                <span 
                  style={{ cursor: 'pointer', color: 'var(--accent-error)', fontWeight: 'bold' }}
                  onClick={() => onRemoveProducer(idx)}
                >
                  ×
                </span>
              </span>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <input 
              type="text" 
              placeholder="Напр. БХФЗ" 
              value={newProducer}
              onChange={(e) => setNewProducer(e.target.value)}
              style={{ padding: '8px 12px' }}
            />
            <button 
              className="btn btn-secondary"
              onClick={onAddProducer}
            >
              Добавить
            </button>
          </div>
        </div>

        {/* Consolidation Options */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h3>Опции консолидации</h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '0.9rem' }}>
              <input 
                type="checkbox" 
                checked={useCatalogMatching}
                onChange={(e) => onToggleCatalogMatching(e.target.checked)}
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <div>
                <div style={{ fontWeight: '500' }}>Сопоставлять с каталогом</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Приводит названия лекарств к каноническому виду</div>
              </div>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '0.9rem', marginTop: '4px' }}>
              <input 
                type="checkbox" 
                checked={legacyPriorityRules}
                onChange={(e) => onToggleLegacyRules(e.target.checked)}
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <div>
                <div style={{ fontWeight: '500' }}>Приоритет ручного ввода</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Использовать старые правила подтягивания остатков</div>
              </div>
            </label>

            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '0.9rem', marginTop: '4px' }}>
              <input 
                type="checkbox" 
                checked={clearInputsAfterProcessing}
                onChange={(e) => onToggleClearInputs(e.target.checked)}
                style={{ width: '18px', height: '18px', cursor: 'pointer' }}
              />
              <div>
                <div style={{ fontWeight: '500' }}>Очищать прайсы после обработки</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Автоматически удалять исходные прайс-листы Excel после выполнения задач</div>
              </div>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

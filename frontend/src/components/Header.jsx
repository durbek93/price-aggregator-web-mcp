import React from 'react';

export default function Header({ telegramUser, onLogout }) {
  return (
    <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
      <div>
        <h1>Сводный Прайс</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '4px' }}>
          Веб-панель консолидации прайс-листов дистрибьюторов
        </p>
      </div>
      
      {/* User Badge / Telegram Link status */}
      {telegramUser && (
        <div className="glass-panel" style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: '12px', borderRadius: '12px' }}>
          <span style={{ fontSize: '1.5rem' }}>{telegramUser.avatar}</span>
          <div style={{ textAlign: 'left' }}>
            <div style={{ fontWeight: '600', fontSize: '0.9rem', color: '#fff' }}>
              {telegramUser.firstName}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--accent-success)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-success)' }}></span>
              t.me/{telegramUser.username}
            </div>
          </div>
          <button 
            onClick={onLogout}
            style={{ border: 'none', background: 'none', color: 'var(--accent-error)', cursor: 'pointer', padding: '0 4px', fontSize: '1.1rem' }}
            title="Выйти"
          >
            🚪
          </button>
        </div>
      )}
    </header>
  );
}

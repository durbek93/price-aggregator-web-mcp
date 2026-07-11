import React from 'react';

export default function Auth({ onVerifyToken }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', padding: '24px' }}>
      <div className="glass-panel animate-fade-in" style={{ maxWidth: '480px', width: '100%', textAlign: 'center', padding: '40px' }}>
        <div style={{ fontSize: '3.5rem', marginBottom: '20px' }}>🤖</div>
        <h2 style={{ marginBottom: '12px', fontSize: '1.8rem', fontFamily: 'var(--font-display)' }}>Вход в Price Aggregator</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginBottom: '24px', lineHeight: '1.6' }}>
          Доступ к веб-панели управления консолидацией прайс-листов защищен.
          <br /><br />
          Пожалуйста, перейдите в наш Telegram-бот и отправьте команду <b>/start</b> или <b>/link</b>, чтобы получить ссылку для автоматического входа.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <button 
            className="btn btn-primary" 
            onClick={() => alert("Перейдите в ваш Telegram и откройте бот консолидатора прайсов.")}
            style={{ padding: '12px' }}
          >
            💬 Откройте ваш Telegram-бот
          </button>
          <button 
            className="btn btn-secondary" 
            onClick={() => {
              const mockToken = prompt("Введите JWT токен входа из логов / Telegram-бота:");
              if (mockToken) {
                onVerifyToken(mockToken);
              }
            }}
          >
            🔑 Ввести токен входа вручную
          </button>
        </div>
      </div>
    </div>
  );
}

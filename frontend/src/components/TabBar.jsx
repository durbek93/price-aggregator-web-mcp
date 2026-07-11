import React from 'react';

export default function TabBar({ activeTab, setActiveTab, priceFilesCount, runningTask }) {
  return (
    <div className="tab-bar">
      <div className={`tab-item ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
        📁 Панель управления ({priceFilesCount})
      </div>
      <div className={`tab-item ${activeTab === 'catalog' ? 'active' : ''}`} onClick={() => setActiveTab('catalog')}>
        💊 Каталог препаратов
      </div>
      <div className={`tab-item ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>
        ⚙️ Настройки колонок
      </div>
      <div className={`tab-item ${activeTab === 'tasks' ? 'active' : ''}`} onClick={() => setActiveTab('tasks')}>
        🤖 Очередь задач {runningTask && <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-secondary)', marginLeft: '4px' }}></span>}
      </div>
    </div>
  );
}

import React, { useRef } from 'react';

export default function Dashboard({
  priceFiles,
  runningTask,
  dragActive,
  uploadingFiles,
  onDrag,
  onDrop,
  onFileUpload,
  onStartPipeline,
  onClearAllFiles,
  onDeleteFile,
  onUpdateFilePreset
}) {
  const fileInputRef = useRef(null);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
      {/* Upload Section */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <h3 style={{ marginBottom: '8px' }}>Загрузка файлов прайсов</h3>
        
        <div 
          className={`upload-zone ${dragActive ? 'active' : ''}`}
          onDragEnter={onDrag}
          onDragOver={onDrag}
          onDragLeave={onDrag}
          onDrop={onDrop}
          onClick={() => fileInputRef.current && fileInputRef.current.click()}
        >
          <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>📊</div>
          <p style={{ fontWeight: '500', marginBottom: '4px' }}>Перетащите файлы прайсов Excel сюда или нажмите для выбора</p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Поддерживаются .xlsx, .xls файлы</p>
          <input 
            type="file" 
            ref={fileInputRef}
            id="file-upload-input" 
            style={{ display: 'none' }} 
            multiple 
            onChange={(e) => {
              if (e.target.files) {
                for (let i = 0; i < e.target.files.length; i++) {
                  onFileUpload(e.target.files[i]);
                }
              }
            }}
          />
        </div>

        {/* Uploading Files Progress */}
        {Object.keys(uploadingFiles).length > 0 && (
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '12px', 
            padding: '16px', 
            background: 'rgba(255, 255, 255, 0.02)', 
            border: '1px solid var(--border-light)', 
            borderRadius: '12px',
            marginTop: '4px'
          }}>
            <div style={{ fontSize: '0.9rem', fontWeight: '600', color: 'var(--text-primary)' }}>
              Загрузка файлов...
            </div>
            {Object.entries(uploadingFiles).map(([filename, progress]) => (
              <div key={filename} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem' }}>
                  <span style={{ 
                    color: 'var(--text-secondary)', 
                    textOverflow: 'ellipsis', 
                    overflow: 'hidden', 
                    whiteSpace: 'nowrap', 
                    maxWidth: '75%',
                    fontWeight: '500'
                  }}>
                    📄 {filename}
                  </span>
                  <span style={{ color: 'var(--accent-primary)', fontWeight: '600' }}>
                    {progress}%
                  </span>
                </div>
                <div style={{ width: '100%', height: '6px', backgroundColor: 'var(--bg-primary)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div 
                    style={{ 
                      width: `${progress}%`, 
                      height: '100%', 
                      background: 'linear-gradient(90deg, var(--accent-primary) 0%, var(--accent-secondary) 100%)', 
                      borderRadius: '3px',
                      transition: 'width 0.15s ease-out' 
                    }} 
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Actions Box */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '8px' }}>
          <button className="btn btn-primary" onClick={() => onStartPipeline('Сводный прайс')} disabled={!!runningTask}>
            🚀 Сводный прайс (гориз.)
          </button>
          <button className="btn btn-primary" onClick={() => onStartPipeline('Сводный прайс (верт.)')} disabled={!!runningTask}>
            📈 Сводный прайс (верт.)
          </button>
          <button className="btn btn-secondary" onClick={() => onStartPipeline('Анализ ассортимента')} disabled={!!runningTask}>
            🔍 Ассортимент
          </button>
          <button className="btn btn-secondary" onClick={() => onStartPipeline('Подсветка минимальных цен')} disabled={!!runningTask}>
            💡 Подсветить дешевые
          </button>
          <button className="btn btn-secondary" onClick={() => onStartPipeline('Анализ лучших поставщиков')} disabled={!!runningTask}>
            🏢 Лучшие поставщики
          </button>
        </div>
      </div>

      {/* Uploaded Files Table */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
          <h3 style={{ margin: 0 }}>Загруженные прайс-листы ({priceFiles.length})</h3>
          {priceFiles.length > 0 && (
            <button 
              className="btn btn-danger" 
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
              onClick={onClearAllFiles}
            >
              🧹 Очистить все
            </button>
          )}
        </div>
        <div className="table-container" style={{ maxHeight: '310px', overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Название файла</th>
                <th>Шаблон парсера</th>
                <th>Размер</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {priceFiles.map(file => (
                <tr key={file.id}>
                  <td style={{ fontWeight: '500' }}>
                    <div>{file.display_name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{file.filename} • {new Date(file.uploaded_at).toLocaleDateString('ru-RU')}</div>
                  </td>
                  <td>
                    <select 
                      value={file.read_preset || ''}
                      onChange={(e) => onUpdateFilePreset(file.id, e.target.value)}
                      style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                    >
                      <option value="">Авто-поиск</option>
                      <option value="khoji_akbar">Хожи Акбар (12-я стр)</option>
                      <option value="grand_farm">Гранд Фарм (поиск)</option>
                    </select>
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>
                    {(file.file_size / 1024).toFixed(0)} KB
                  </td>
                  <td>
                    <button 
                      className="btn btn-danger" 
                      style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                      onClick={() => onDeleteFile(file.id)}
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
              {priceFiles.length === 0 && (
                <tr>
                  <td colSpan="4" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    Файлы не загружены. Перетащите их или отправьте в Telegram-бот.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

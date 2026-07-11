import React from 'react';
import { formatTime } from '../utils/helpers';

export default function Tasks({
  runningTask,
  elapsedTime,
  taskProgress,
  taskLogs,
  tasks,
  onCancelTask,
  onDeleteTask,
  onClearFailedTasks,
  onDownloadReportFile
}) {
  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Active task loader */}
      {runningTask ? (
        <div style={{ border: '1px solid var(--accent-primary)', padding: '20px', borderRadius: '12px', background: 'rgba(129, 140, 248, 0.03)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '1.2rem', animation: 'spin 2s linear infinite', display: 'inline-block' }}>⚙️</span>
              <strong style={{ fontSize: '1.05rem', color: '#fff' }}>Выполняется задача: {runningTask.type}</strong>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginRight: '4px' }}>⏱️ {formatTime(elapsedTime)}</span>
              <span style={{ fontWeight: '600', color: 'var(--accent-primary)' }}>{taskProgress}%</span>
              <button 
                onClick={() => onCancelTask(runningTask.id)}
                className="btn btn-danger"
                style={{ padding: '4px 10px', fontSize: '0.75rem', margin: 0 }}
              >
                🛑 Остановить
              </button>
            </div>
          </div>
          
          {/* Progress bar */}
          <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--bg-primary)', borderRadius: '4px', overflow: 'hidden', marginBottom: '20px' }}>
            <div style={{ width: `${taskProgress}%`, height: '100%', backgroundColor: 'var(--accent-primary)', transition: 'width 0.3s ease' }}></div>
          </div>

          {/* Console Logs */}
          <div style={{ 
            backgroundColor: '#050608', 
            fontFamily: 'monospace', 
            fontSize: '0.8rem', 
            padding: '16px', 
            borderRadius: '8px', 
            maxHeight: '200px', 
            overflowY: 'auto',
            border: '1px solid var(--border-light)',
            color: 'var(--accent-success)'
          }}>
            {taskLogs.map((log, idx) => (
              <div key={idx} style={{ marginBottom: '6px', borderLeft: '2px solid rgba(52, 211, 153, 0.3)', paddingLeft: '8px' }}>
                [INFO] {log}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '12px', border: '1px dashed var(--border-medium)', borderRadius: '12px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Активных задач в очереди нет. Вы можете запустить сборку во вкладке «Панель управления».
        </div>
      )}

      {/* Task History */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0 }}>История выполненных отчетов</h3>
          {tasks.some(t => t.status === 'failed') && (
            <button 
              className="btn btn-danger" 
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
              onClick={onClearFailedTasks}
            >
              🧹 Очистить ошибки
            </button>
          )}
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Название задачи</th>
                <th>Дата создания</th>
                <th>Статус выполнения</th>
                <th>Файл отчета</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(task => (
                <tr key={task.id}>
                  <td style={{ fontWeight: '600', color: '#fff' }}>{task.type}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{task.date}</td>
                  <td>
                    <span 
                      onClick={() => {
                        if (task.status === 'failed') {
                          const errorLogs = (task.progressMessage || 'Описание ошибки отсутствует.')
                            .split(' ||| ')
                            .join('\n');
                          alert(`Детали ошибки:\n\n${errorLogs}`);
                        }
                      }}
                      style={{ 
                        color: task.status === 'completed' ? 'var(--accent-success)' : task.status === 'failed' ? 'var(--accent-error)' : 'var(--accent-warning)',
                        backgroundColor: task.status === 'completed' ? 'rgba(52, 211, 153, 0.1)' : task.status === 'failed' ? 'rgba(248, 113, 113, 0.1)' : 'rgba(251, 191, 36, 0.1)',
                        border: `1px solid ${task.status === 'completed' ? 'rgba(52, 211, 153, 0.3)' : task.status === 'failed' ? 'rgba(248, 113, 113, 0.3)' : 'rgba(251, 191, 36, 0.3)'}`,
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        cursor: task.status === 'failed' ? 'pointer' : 'default'
                      }}
                      title={task.status === 'failed' ? 'Нажмите, чтобы увидеть подробности ошибки' : ''}
                    >
                      {task.status === 'completed' ? 'Завершено' : task.status === 'failed' ? 'Ошибка ℹ️' : 'Выполняется'}
                    </span>
                  </td>
                  <td>
                    {task.status === 'completed' && task.resultFile ? (
                      <a 
                        href="#" 
                        onClick={(e) => { e.preventDefault(); onDownloadReportFile(task.resultFile); }}
                        style={{ color: 'var(--accent-primary)', textDecoration: 'none', fontWeight: '500', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                      >
                        📥 {task.resultFile}
                      </a>
                    ) : task.status === 'failed' ? (
                      <span 
                        onClick={() => {
                          const errorLogs = (task.progressMessage || 'Описание ошибки отсутствует.')
                            .split(' ||| ')
                            .join('\n');
                          alert(`Детали ошибки:\n\n${errorLogs}`);
                        }}
                        style={{ color: 'var(--accent-error)', fontSize: '0.85rem', cursor: 'pointer', textDecoration: 'underline dotted' }}
                        title="Нажмите, чтобы увидеть подробности ошибки"
                      >
                        Ошибка генерации ℹ️
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Генерируется...</span>
                    )}
                  </td>
                  <td>
                    {task.status !== 'running' && task.status !== 'pending' && (
                      <button
                        onClick={() => onDeleteTask(task.id)}
                        className="btn btn-danger"
                        style={{ padding: '4px 8px', fontSize: '0.75rem', margin: 0 }}
                        title="Удалить задачу и файл отчета"
                      >
                        🗑️ Удалить
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

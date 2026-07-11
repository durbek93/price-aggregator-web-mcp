import { useState, useEffect } from 'react';
import Header from './components/Header';
import TabBar from './components/TabBar';
import Auth from './pages/Auth';
import Dashboard from './pages/Dashboard';
import Catalog from './pages/Catalog';
import Settings from './pages/Settings';
import Tasks from './pages/Tasks';
import { parseProgressFromLogs } from './utils/helpers';
import { api } from './utils/api';


// Pre-populated default settings as fallback
const DEFAULT_COLUMNS = {
  key_candidates: ['Артикул', 'Код', 'SKU', 'ID', 'PartNumber'],
  name_candidates: ['Наименование', 'Наименование товара', 'Товар', 'Название'],
  price_candidates: ['Цена с НДС', 'Цена', 'Цена переч', 'Отп. Цена', 'Price'],
  stock_candidates: ['Остаток', 'Наличие', 'Stock', 'Количество'],
  producer_candidates: ['Производитель', 'Бренд', 'Manufacturer']
};

const DEFAULT_PRODUCERS = ['Материа Медика', 'Материя Медика', 'Materia Medica', 'Материа Медика Холдинг'];

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [telegramUser, setTelegramUser] = useState(null);

  // Settings State
  const [columns, setColumns] = useState(DEFAULT_COLUMNS);
  const [producers, setProducers] = useState(DEFAULT_PRODUCERS);
  const [newProducer, setNewProducer] = useState('');
  const [useCatalogMatching, setUseCatalogMatching] = useState(false);
  const [legacyPriorityRules, setLegacyPriorityRules] = useState(false);
  const [clearInputsAfterProcessing, setClearInputsAfterProcessing] = useState(true);

  // Catalog State
  const [catalog, setCatalog] = useState([]);
  const [newCanonical, setNewCanonical] = useState('');
  const [newAliases, setNewAliases] = useState('');

  // Catalog Editing State
  const [editingId, setEditingId] = useState(null);
  const [editCanonical, setEditCanonical] = useState('');
  const [editAliases, setEditAliases] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [baseCatalogs, setBaseCatalogs] = useState(["Материа Медика (По умолчанию)"]);
  const [selectedBaseCatalog, setSelectedBaseCatalog] = useState("Материа Медика (По умолчанию)");

  // Files State
  const [priceFiles, setPriceFiles] = useState([]);

  // Tasks State
  const [tasks, setTasks] = useState([]);
  const [runningTask, setRunningTask] = useState(null);
  const [taskProgress, setTaskProgress] = useState(0);
  const [taskLogs, setTaskLogs] = useState([]);
  const [elapsedTime, setElapsedTime] = useState(0);

  // Drag and Drop
  const [dragActive, setDragActive] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState({});

  // Authentication Flow
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');

    if (urlToken) {
      setLoading(true);
      api.auth.verify(urlToken)
        .then(data => {
          localStorage.setItem('token', data.token);
          setToken(data.token);
          setTelegramUser({
            username: data.user.username || 'unknown',
            firstName: data.user.first_name || 'Пользователь',
            avatar: '🤖'
          });
          window.history.replaceState({}, document.title, window.location.pathname);
        })
        .catch(err => {
          console.error(err);
          alert('Ошибка ссылки входа. Пожалуйста, запросите новую ссылку в боте.');
        })
        .finally(() => setLoading(false));
    } else if (token) {
      setLoading(true);
      api.auth.me(token)
        .then(data => {
          setTelegramUser({
            username: data.username || 'unknown',
            firstName: data.first_name || 'Пользователь',
            avatar: '🤖'
          });
          setLoading(false);
        })
        .catch(err => {
          console.error(err);
          localStorage.removeItem('token');
          setToken(null);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [token]);

  // Load Data function
  const loadData = () => {
    if (!token) return;

    // Fetch settings
    api.settings.getSettings(token)
      .then(data => {
        setColumns(data.columns);
        setProducers(data.producers);
        setUseCatalogMatching(data.use_catalog_matching);
        setLegacyPriorityRules(data.legacy_priority_rules);
        setClearInputsAfterProcessing(data.clear_inputs_after_processing);
      })
      .catch(err => console.error('Error fetching settings:', err));

    // Fetch catalog
    api.catalog.getItems(token)
      .then(data => setCatalog(data))
      .catch(err => console.error('Error fetching catalog:', err));

    // Fetch input files
    api.files.getFiles(token)
      .then(data => setPriceFiles(data))
      .catch(err => console.error('Error fetching files:', err));

    // Fetch base catalogs
    api.catalog.getBaseCatalogs(token)
      .then(data => setBaseCatalogs(data))
      .catch(err => console.error('Error fetching base catalogs:', err));

    // Fetch tasks
    api.tasks.getTasks(token)
      .then(data => {
        const mappedTasks = data.map(t => ({
          id: t.id,
          type: t.task_type === 'svodny_horizontal' ? 'Сводный прайс' :
            t.task_type === 'svodny_vertical' ? 'Сводный прайс (верт.)' :
              t.task_type === 'assortment' ? 'Анализ ассортимента' :
                t.task_type === 'cheapest' ? 'Подсветка минимальных цен' :
                  t.task_type === 'best_suppliers' ? 'Анализ лучших поставщиков' : t.task_type,
          status: t.status,
          date: new Date(t.created_at).toLocaleString('ru-RU'),
          progressMessage: t.progress_message,
          progress: t.status === 'completed' ? 100 : t.status === 'failed' ? 0 : 50,
          log: t.progress_message || 'В очереди...',
          resultFile: t.result_file_path ? t.result_file_path.split('/').pop() : null
        }));
        setTasks(mappedTasks);

        // Check if there is an active running task
        const activeTask = data.find(t => t.status === 'running' || t.status === 'pending');
        if (activeTask) {
          setRunningTask({
            id: activeTask.id,
            type: activeTask.task_type === 'svodny_horizontal' ? 'Сводный прайс' :
              activeTask.task_type === 'svodny_vertical' ? 'Сводный прайс (верт.)' :
                activeTask.task_type === 'assortment' ? 'Анализ ассортимента' :
                  activeTask.task_type === 'cheapest' ? 'Подсветка минимальных цен' :
                    activeTask.task_type === 'best_suppliers' ? 'Анализ лучших поставщиков' : activeTask.task_type,
            status: activeTask.status
          });
          const parsed = parseProgressFromLogs(activeTask.progress_message);
          setTaskProgress(parsed !== null ? parsed : (activeTask.status === 'pending' ? 10 : 60));
          if (activeTask.progress_message) {
            setTaskLogs(activeTask.progress_message.split(' ||| '));
          } else {
            setTaskLogs(['Выполнение задачи...']);
          }
        } else {
          setRunningTask(null);
        }
      })
      .catch(err => console.error('Error fetching tasks:', err));
  };

  useEffect(() => {
    if (token) {
      loadData();
    }
  }, [token]);

  // Load suggestions when Catalog tab is active
  useEffect(() => {
    if (activeTab === 'catalog' && token) {
      loadSuggestions();
    }
  }, [activeTab, token]);

  const loadSuggestions = () => {
    if (!token) return;
    setLoadingSuggestions(true);
    api.catalog.getSuggestions(token)
      .then(data => {
        setSuggestions(Array.isArray(data) ? data : []);
        setLoadingSuggestions(false);
      })
      .catch(err => {
        console.error(err);
        setLoadingSuggestions(false);
      });
  };

  const acceptSuggestion = (suggestion) => {
    if (!token) return;
    const item = catalog.find(c => c.id === suggestion.canonical_id);
    if (!item) return;

    const updatedAliases = [...item.aliases];
    if (!updatedAliases.includes(suggestion.suggested_alias)) {
      updatedAliases.push(suggestion.suggested_alias);
    }

    api.catalog.updateItem(token, item.id, item.canonical, updatedAliases)
      .then(() => {
        setSuggestions(prev => prev.filter(s => s.suggested_alias !== suggestion.suggested_alias));
        loadData();
      })
      .catch(err => console.error(err));
  };

  const ignoreSuggestion = (suggestedAlias) => {
    setSuggestions(prev => prev.filter(s => s.suggested_alias !== suggestedAlias));
  };

  const clearFailedTasks = () => {
    if (!token) return;
    if (!confirm('Очистить все задачи с ошибками из истории?')) return;

    api.tasks.clearErrors(token)
      .then(() => {
        loadData();
      })
      .catch(err => console.error(err));
  };

  // Task execution polling
  useEffect(() => {
    if (!runningTask || !token) return;

    const interval = setInterval(() => {
      api.tasks.getTaskStatus(token, runningTask.id)
        .then(data => {
          setTaskLogs(prev => {
            const nextLogs = [...prev];
            if (data.progress_message) {
              const parts = data.progress_message.split(' ||| ');
              parts.forEach(part => {
                if (part && !nextLogs.includes(part)) {
                  nextLogs.push(part);
                }
              });
            }
            return nextLogs;
          });

          if (data.status === 'completed') {
            setTaskProgress(100);
            clearInterval(interval);
            setRunningTask(null);
            loadData();
          } else if (data.status === 'failed') {
            clearInterval(interval);
            setRunningTask(null);
            loadData();
            alert(`Ошибка выполнения задачи: ${data.progress_message}`);
          } else {
            const parsed = parseProgressFromLogs(data.progress_message);
            if (parsed !== null) {
              setTaskProgress(parsed);
            } else {
              setTaskProgress(prev => Math.min(prev + 5, 95));
            }
          }
        })
        .catch(err => console.error(err));
    }, 2000);

    return () => clearInterval(interval);
  }, [runningTask, token]);

  // Live elapsed timer for active task
  useEffect(() => {
    if (!runningTask) {
      setElapsedTime(0);
      return;
    }
    const timer = setInterval(() => {
      setElapsedTime(prev => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [runningTask]);

  // Settings Save function
  const saveSettings = (updatedColumns, updatedProducers, useCatalog, legacyRules, clearInputs) => {
    if (!token) return;

    api.settings.saveSettings(token, updatedColumns, updatedProducers, useCatalog, legacyRules, clearInputs)
      .catch(err => console.error('Error saving settings:', err));
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && token) {
      for (let i = 0; i < e.dataTransfer.files.length; i++) {
        uploadFileToServer(e.dataTransfer.files[i]);
      }
    }
  };

  const uploadFileToServer = (file) => {
    const fileName = file.name;

    setUploadingFiles(prev => ({
      ...prev,
      [fileName]: 0
    }));

    const formData = new FormData();
    formData.append('file', file);
    formData.append('read_preset', '');

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        const percentComplete = Math.round((event.loaded / event.total) * 100);
        setUploadingFiles(prev => ({
          ...prev,
          [fileName]: percentComplete
        }));
      }
    });

    xhr.addEventListener('load', () => {
      setUploadingFiles(prev => {
        const next = { ...prev };
        delete next[fileName];
        return next;
      });

      if (xhr.status >= 200 && xhr.status < 300) {
        loadData();
      } else {
        alert(`Ошибка загрузки файла ${fileName}. Допускаются только таблицы Excel (.xlsx, .xls).`);
      }
    });

    xhr.addEventListener('error', () => {
      setUploadingFiles(prev => {
        const next = { ...prev };
        delete next[fileName];
        return next;
      });
      alert(`Сетевая ошибка при загрузке файла ${fileName}.`);
    });

    xhr.open('POST', '/api/files/upload');
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.send(formData);
  };

  const deleteFile = (fileId) => {
    if (!token) return;
    if (!confirm('Удалить этот файл с сервера?')) return;

    api.files.deleteFile(token, fileId)
      .then(() => {
        loadData();
      })
      .catch(err => console.error(err));
  };

  const clearAllFiles = () => {
    if (!token) return;
    if (!confirm('Удалить все загруженные прайс-листы с сервера?')) return;

    api.files.clearAll(token)
      .then(() => {
        loadData();
      })
      .catch(err => console.error(err));
  };

  const updateFilePreset = (fileId, preset) => {
    if (!token) return;

    api.files.updatePreset(token, fileId, preset)
      .then(() => {
        loadData();
      })
      .catch(err => console.error(err));
  };

  const startPipeline = (type) => {
    if (runningTask || !token) return;

    let task_type = 'svodny_horizontal';
    if (type === 'Сводный прайс') task_type = 'svodny_horizontal';
    else if (type === 'Сводный прайс (верт.)') task_type = 'svodny_vertical';
    else if (type === 'Анализ ассортимента') task_type = 'assortment';
    else if (type === 'Подсветка минимальных цен') task_type = 'cheapest';
    else if (type === 'Анализ лучших поставщиков') task_type = 'best_suppliers';

    api.tasks.startTask(token, task_type)
      .then(data => {
        setRunningTask({
          id: data.id,
          type: type,
          status: data.status
        });
        setTaskProgress(10);
        setTaskLogs(['Добавление задачи в очередь...']);
        setActiveTab('tasks');
      })
      .catch(err => {
        console.error(err);
        alert(`Не удалось запустить задачу: ${err.message}`);
      });
  };

  const cancelTask = (taskId) => {
    if (!confirm('Вы уверены, что хотите прервать генерацию этого отчета?')) return;

    api.tasks.cancelTask(token, taskId)
      .then(() => {
        setRunningTask(null);
        loadData();
      })
      .catch(err => {
        console.error(err);
        alert(`Ошибка остановки задачи: ${err.message}`);
      });
  };

  const deleteTask = (taskId) => {
    if (!confirm('Вы уверены, что хотите удалить эту задачу и связанный с ней файл отчета?')) return;

    api.tasks.deleteTask(token, taskId)
      .then(() => {
        loadData();
      })
      .catch(err => {
        console.error(err);
        alert(`Ошибка удаления задачи: ${err.message}`);
      });
  };

  const downloadReportFile = (fileName) => {
    if (!token) return;

    api.files.downloadReportFile(token, fileName)
      .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      })
      .catch(err => {
        console.error(err);
        alert('Не удалось скачать файл отчета.');
      });
  };

  // Catalog Actions
  const handleAddCatalogItem = () => {
    if (!newCanonical.trim() || !token) return;
    const aliasesList = newAliases.split(',').map(s => s.trim()).filter(s => s.length > 0);

    api.catalog.addItem(token, newCanonical.trim(), aliasesList)
      .then(() => {
        setNewCanonical('');
        setNewAliases('');
        loadData();
      })
      .catch(err => console.error(err));
  };

  const importBaseCatalog = () => {
    if (!token) return;
    if (!confirm(`Вы уверены? Это действие ПОЛНОСТЬЮ очистит ваш текущий каталог препаратов и импортирует базовый список "${selectedBaseCatalog}" со всеми синонимами.`)) return;

    api.catalog.importBaseCatalog(token, selectedBaseCatalog)
      .then(() => {
        loadData();
        loadSuggestions();
        alert(`Каталог препаратов "${selectedBaseCatalog}" успешно импортирован!`);
      })
      .catch(err => {
        console.error(err);
        alert('Ошибка при импорте каталога.');
      });
  };

  const saveBaseCatalog = () => {
    if (!token) return;
    const name = prompt('Введите имя для нового базового каталога (например, База данных ММХ (Иванов)):');
    if (name === null) return; // cancelled
    if (!name.trim()) {
      alert('Имя каталога не может быть пустым.');
      return;
    }

    api.catalog.saveBaseCatalog(token, name.trim())
      .then(() => {
        alert('Каталог успешно сохранен в качестве базового на сервере!');
        // Refresh base catalogs list
        api.catalog.getBaseCatalogs(token)
          .then(data => {
            setBaseCatalogs(data);
            setSelectedBaseCatalog(name.trim());
          })
          .catch(err => console.error(err));
      })
      .catch(err => {
        console.error(err);
        alert('Ошибка при сохранении каталога.');
      });
  };

  const handleDeleteCatalogItem = (itemId) => {
    if (!token) return;
    api.catalog.deleteItem(token, itemId)
      .then(() => {
        loadData();
      })
      .catch(err => console.error(err));
  };

  const handleStartEdit = (item) => {
    setEditingId(item.id);
    setEditCanonical(item.canonical);
    setEditAliases(item.aliases.join(', '));
  };

  const handleSaveEdit = (itemId) => {
    if (!editCanonical.trim() || !token) return;
    const aliasesList = editAliases.split(',').map(s => s.trim()).filter(s => s.length > 0);

    api.catalog.updateItem(token, itemId, editCanonical.trim(), aliasesList)
      .then(() => {
        setEditingId(null);
        loadData();
      })
      .catch(err => console.error(err));
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditCanonical('');
    setEditAliases('');
  };

  // Settings handlers
  const handleAddCandidate = (columnKey, val) => {
    const updated = { ...columns };
    updated[columnKey] = [...updated[columnKey], val];
    setColumns(updated);
    saveSettings(updated, producers, useCatalogMatching, legacyPriorityRules, clearInputsAfterProcessing);
  };

  const handleRemoveCandidate = (columnKey, idx) => {
    const updated = { ...columns };
    updated[columnKey] = updated[columnKey].filter((_, i) => i !== idx);
    setColumns(updated);
    saveSettings(updated, producers, useCatalogMatching, legacyPriorityRules, clearInputsAfterProcessing);
  };

  const handleAddProducer = () => {
    if (!newProducer.trim()) return;
    const updated = [...producers, newProducer.trim()];
    setProducers(updated);
    setNewProducer('');
    saveSettings(columns, updated, useCatalogMatching, legacyPriorityRules, clearInputsAfterProcessing);
  };

  const handleRemoveProducer = (idx) => {
    const updated = producers.filter((_, i) => i !== idx);
    setProducers(updated);
    saveSettings(columns, updated, useCatalogMatching, legacyPriorityRules, clearInputsAfterProcessing);
  };

  const handleToggleCatalogMatching = (checked) => {
    setUseCatalogMatching(checked);
    saveSettings(columns, producers, checked, legacyPriorityRules, clearInputsAfterProcessing);
  };

  const handleToggleLegacyRules = (checked) => {
    setLegacyPriorityRules(checked);
    saveSettings(columns, producers, useCatalogMatching, checked, clearInputsAfterProcessing);
  };

  const handleToggleClearInputs = (checked) => {
    setClearInputsAfterProcessing(checked);
    saveSettings(columns, producers, useCatalogMatching, legacyPriorityRules, checked);
  };

  const handleVerifyToken = (verifyToken) => {
    localStorage.setItem('token', verifyToken);
    setToken(verifyToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
  };

  // Loading Screen
  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div style={{ textAlign: 'center' }}>
          <span style={{ fontSize: '2.5rem', animation: 'spin 2s linear infinite', display: 'inline-block' }}>⚙️</span>
          <p style={{ color: 'var(--text-secondary)', marginTop: '16px', fontSize: '0.95rem' }}>Загрузка панели управления...</p>
        </div>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  // Authentication Card
  if (!token) {
    return <Auth onVerifyToken={handleVerifyToken} />;
  }

  return (
    <div className="animate-fade-in" style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Top Header */}
      <Header telegramUser={telegramUser} onLogout={handleLogout} />

      {/* Tabs */}
      <TabBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        priceFilesCount={priceFiles.length}
        runningTask={!!runningTask}
      />

      {/* Tab Contents */}
      <main style={{ flex: 1 }}>
        {activeTab === 'dashboard' && (
          <Dashboard
            priceFiles={priceFiles}
            runningTask={runningTask}
            dragActive={dragActive}
            uploadingFiles={uploadingFiles}
            onDrag={handleDrag}
            onDrop={handleDrop}
            onFileUpload={uploadFileToServer}
            onStartPipeline={startPipeline}
            onClearAllFiles={clearAllFiles}
            onDeleteFile={deleteFile}
            onUpdateFilePreset={updateFilePreset}
          />
        )}

        {activeTab === 'catalog' && (
          <Catalog
            catalog={catalog}
            newCanonical={newCanonical}
            setNewCanonical={setNewCanonical}
            newAliases={newAliases}
            setNewAliases={setNewAliases}
            editingId={editingId}
            editCanonical={editCanonical}
            setEditCanonical={setEditCanonical}
            editAliases={editAliases}
            setEditAliases={setEditAliases}
            suggestions={suggestions}
            loadingSuggestions={loadingSuggestions}
            onLoadSuggestions={loadSuggestions}
            onAcceptSuggestion={acceptSuggestion}
            onIgnoreSuggestion={ignoreSuggestion}
            onAddCatalogItem={handleAddCatalogItem}
            onImportBaseCatalog={importBaseCatalog}
            onSaveBaseCatalog={saveBaseCatalog}
            onDeleteCatalogItem={handleDeleteCatalogItem}
            onStartEdit={handleStartEdit}
            onSaveEdit={handleSaveEdit}
            onCancelEdit={handleCancelEdit}
            baseCatalogs={baseCatalogs}
            selectedBaseCatalog={selectedBaseCatalog}
            onSelectBaseCatalog={setSelectedBaseCatalog}
          />
        )}

        {activeTab === 'settings' && (
          <Settings
            columns={columns}
            producers={producers}
            newProducer={newProducer}
            setNewProducer={setNewProducer}
            useCatalogMatching={useCatalogMatching}
            legacyPriorityRules={legacyPriorityRules}
            clearInputsAfterProcessing={clearInputsAfterProcessing}
            onAddCandidate={handleAddCandidate}
            onRemoveCandidate={handleRemoveCandidate}
            onAddProducer={handleAddProducer}
            onRemoveProducer={handleRemoveProducer}
            onToggleCatalogMatching={handleToggleCatalogMatching}
            onToggleLegacyRules={handleToggleLegacyRules}
            onToggleClearInputs={handleToggleClearInputs}
          />
        )}

        {activeTab === 'tasks' && (
          <Tasks
            runningTask={runningTask}
            elapsedTime={elapsedTime}
            taskProgress={taskProgress}
            taskLogs={taskLogs}
            tasks={tasks}
            onCancelTask={cancelTask}
            onDeleteTask={deleteTask}
            onClearFailedTasks={clearFailedTasks}
            onDownloadReportFile={downloadReportFile}
          />
        )}
      </main>

      {/* Footer */}
      <footer style={{ marginTop: 'auto', paddingTop: '48px', paddingBottom: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
        Price Aggregator Web v1.0.0 • Независимый веб-сервис
      </footer>

      {/* Spin style injection */}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

export default App;

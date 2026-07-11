const getHeaders = (token) => {
  const headers = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

const getJSONHeaders = (token) => ({
  ...getHeaders(token),
  'Content-Type': 'application/json'
});

const handleResponse = (res) => {
  if (!res.ok) {
    return res.json().then(
      (data) => {
        throw new Error(data.detail || `HTTP Error: ${res.status}`);
      },
      () => {
        throw new Error(`HTTP Error: ${res.status}`);
      }
    );
  }
  return res.json();
};

export const api = {
  auth: {
    verify: (token) => fetch(`/api/auth/verify?token=${token}`).then(handleResponse),
    me: (token) => fetch('/api/auth/me', { headers: getHeaders(token) }).then(handleResponse),
  },
  catalog: {
    getItems: (token) => fetch('/api/catalog', { headers: getHeaders(token) }).then(handleResponse),
    addItem: (token, canonical, aliases) => fetch('/api/catalog', {
      method: 'POST',
      headers: getJSONHeaders(token),
      body: JSON.stringify({ canonical, aliases })
    }).then(handleResponse),
    updateItem: (token, id, canonical, aliases) => fetch(`/api/catalog/${id}`, {
      method: 'PUT',
      headers: getJSONHeaders(token),
      body: JSON.stringify({ canonical, aliases })
    }).then(handleResponse),
    deleteItem: (token, id) => fetch(`/api/catalog/${id}`, {
      method: 'DELETE',
      headers: getHeaders(token)
    }).then(handleResponse),
    getBaseCatalogs: (token) => fetch('/api/catalog/base-catalogs', { headers: getHeaders(token) }).then(handleResponse),
    importBaseCatalog: (token, name) => fetch(`/api/catalog/import-default?name=${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: getHeaders(token)
    }).then(handleResponse),
    saveBaseCatalog: (token, name) => fetch(`/api/catalog/save-as-default?name=${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: getHeaders(token)
    }).then(handleResponse),
    getSuggestions: (token) => fetch('/api/catalog/suggest-synonyms', { headers: getHeaders(token) }).then(handleResponse)
  },
  files: {
    getFiles: (token) => fetch('/api/files?file_type=input', { headers: getHeaders(token) }).then(handleResponse),
    deleteFile: (token, id) => fetch(`/api/files/${id}`, {
      method: 'DELETE',
      headers: getHeaders(token)
    }).then(handleResponse),
    clearAll: (token) => fetch('/api/files/clear', {
      method: 'DELETE',
      headers: getHeaders(token)
    }).then(handleResponse),
    updatePreset: (token, id, preset) => fetch(`/api/files/${id}`, {
      method: 'PUT',
      headers: getJSONHeaders(token),
      body: JSON.stringify({ read_preset: preset })
    }).then(handleResponse),
    downloadReportFile: (token, fileName) => fetch(`/api/files/download_by_name/${fileName}`, {
      headers: getHeaders(token)
    }).then(res => {
      if (!res.ok) throw new Error('Download failed');
      return res.blob();
    })
  },
  settings: {
    getSettings: (token) => fetch('/api/settings', { headers: getHeaders(token) }).then(handleResponse),
    saveSettings: (token, columns, producers, useCatalog, legacyRules, clearInputs) => fetch('/api/settings', {
      method: 'PUT',
      headers: getJSONHeaders(token),
      body: JSON.stringify({
        columns,
        producers,
        use_catalog_matching: useCatalog,
        legacy_priority_rules: legacyRules,
        clear_inputs_after_processing: clearInputs
      })
    }).then(handleResponse)
  },
  tasks: {
    getTasks: (token) => fetch('/api/tasks', { headers: getHeaders(token) }).then(handleResponse),
    getTaskStatus: (token, id) => fetch(`/api/tasks/${id}`, { headers: getHeaders(token) }).then(handleResponse),
    startTask: (token, taskType) => fetch('/api/tasks', {
      method: 'POST',
      headers: getJSONHeaders(token),
      body: JSON.stringify({ task_type: taskType })
    }).then(handleResponse),
    cancelTask: (token, id) => fetch(`/api/tasks/${id}/cancel`, {
      method: 'POST',
      headers: getHeaders(token)
    }).then(handleResponse),
    deleteTask: (token, id) => fetch(`/api/tasks/${id}`, {
      method: 'DELETE',
      headers: getHeaders(token)
    }).then(handleResponse),
    clearErrors: (token) => fetch('/api/tasks/errors', {
      method: 'DELETE',
      headers: getHeaders(token)
    }).then(handleResponse)
  }
};

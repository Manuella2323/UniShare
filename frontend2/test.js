import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

// --- STYLES ---
const styles = {
  container: { display: 'flex', height: '100vh', fontFamily: "'Segoe UI', Roboto, Helvetica, sans-serif", background: '#f9f9f9' },
  sidebar: { width: '250px', background: '#fff', borderRight: '1px solid #e0e0e0', padding: '20px', display: 'flex', flexDirection: 'column' },
  main: { flex: 1, padding: '30px', overflowY: 'auto' },
  logo: { fontSize: '24px', color: '#1a73e8', fontWeight: 'bold', marginBottom: '40px', display: 'flex', alignItems: 'center', gap: '10px' },
  addBtn: { background: '#fff', border: '1px solid #dadce0', borderRadius: '24px', padding: '12px 24px', fontSize: '14px', fontWeight: '500', color: '#3c4043', cursor: 'pointer', boxShadow: '0 1px 2px rgba(0,0,0,0.1)', display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '30px' },
  statBox: { marginTop: 'auto', padding: '15px', background: '#f8f9fa', borderRadius: '8px' },
  progressBarBg: { height: '6px', background: '#e0e0e0', borderRadius: '3px', marginTop: '10px', overflow: 'hidden' },
  progressBarFill: { height: '100%', background: '#1a73e8', transition: 'width 0.2s' },
  sectionTitle: { fontSize: '18px', fontWeight: '500', color: '#202124', marginBottom: '20px' },
  fileGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '20px' },
  fileCard: { position: 'relative', background: '#fff', borderRadius: '8px', padding: '15px', border: '1px solid #dadce0', cursor: 'pointer', transition: 'box-shadow 0.2s', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' },
  fileIcon: { fontSize: '48px' },
  fileName: { fontSize: '14px', color: '#3c4043', textAlign: 'center', wordBreak: 'break-all' },
  btnGroup: { display: 'flex', gap: '5px', marginTop: '5px' },
  actionBtn: { padding: '5px 10px', borderRadius: '4px', border: 'none', background: '#e8f0fe', color: '#1a73e8', cursor: 'pointer', fontSize: '12px' },
  deleteBtn: { padding: '5px 10px', borderRadius: '4px', border: 'none', background: '#fce8e6', color: '#c5221f', cursor: 'pointer', fontSize: '12px' },
  progressCard: { position: 'fixed', bottom: '30px', right: '30px', width: '340px', background: 'white', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)', padding: '0', overflow: 'hidden' },
  progressHeader: { background: '#333', color: '#fff', padding: '10px 15px', fontSize: '14px', display: 'flex', justifyContent: 'space-between' },
  progressBody: { padding: '15px', maxHeight: '300px', overflowY: 'auto' },
  ctrlBtn: { background: 'none', border: 'none', color: '#fff', cursor: 'pointer', marginLeft: '10px', fontSize: '16px' }
};

const BATCH_SIZE = 4;
const CHUNK_SIZE = 1024 * 1024; // 1MB

function App() {
  const [files, setFiles] = useState([]);
  const [stats, setStats] = useState({ used: 0, quota: 100, nodes_online: 0 });
  const [tasks, setTasks] = useState([]); 
  const [isPaused, setIsPaused] = useState(false);
  const [processing, setProcessing] = useState(false);
  const controllers = useRef({}); 

  useEffect(() => {
    fetchStatus(); 
    const interval = setInterval(fetchStatus, 5000); 
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await axios.get('http://localhost:5000/status');
      setStats(res.data);
      setFiles(res.data.files);
    } catch (err) { console.error("Server offline"); }
  };

  const handleUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const taskId = Date.now();
    controllers.current[taskId] = new AbortController();
    setTasks([...tasks, { id: taskId, type: 'upload', name: file.name, file: file, progress: 0, status: 'pending', doneBytes: 0, totalBytes: file.size }]);
  };

  const handleDownload = async (filename) => {
    try {
      const infoRes = await axios.get(`http://localhost:5000/file_info?filename=${filename}`);
      const info = infoRes.data;
      const taskId = Date.now();
      controllers.current[taskId] = new AbortController();
      setTasks([...tasks, { id: taskId, type: 'download', name: filename, progress: 0, status: 'pending', doneBytes: 0, totalBytes: info.size, totalChunks: info.total_chunks, chunks: [] }]);
    } catch (e) { alert("File info not found"); }
  };

  const handleCancel = async (taskId) => {
    if (controllers.current[taskId]) {
        controllers.current[taskId].abort();
        delete controllers.current[taskId];
    }
    const index = tasks.findIndex(t => t.id === taskId);
    if (index === -1) return;
    const task = tasks[index];
    const newTasks = [...tasks];
    newTasks[index].status = 'cancelled';
    setTasks(newTasks);
    if (task.type === 'upload') {
      try { await axios.delete(`http://localhost:5000/delete_file?filename=${task.name}`); fetchStatus(); } catch (e) {}
    }
  };

  const handleDelete = async (filename, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete ${filename}?`)) return;
    try { await axios.delete(`http://localhost:5000/delete_file?filename=${filename}`); fetchStatus(); } catch (e) { alert("Failed"); }
  };

  const processTasks = async () => {
    if (isPaused || processing) return;
    const activeIndex = tasks.findIndex(t => (t.status === 'pending' || t.status === 'active') && t.status !== 'cancelled' && t.status !== 'failed');
    if (activeIndex === -1) return;

    const task = tasks[activeIndex];
    setProcessing(true);

    if (!controllers.current[task.id]) controllers.current[task.id] = new AbortController();
    const signal = controllers.current[task.id].signal;

    if (task.status === 'pending') {
      const newTasks = [...tasks];
      newTasks[activeIndex].status = 'active';
      setTasks(newTasks);
    }

    try {
      if (task.type === 'upload') {
        const totalChunks = Math.ceil(task.file.size / CHUNK_SIZE);
        const currentChunkIdx = Math.floor(task.doneBytes / CHUNK_SIZE);

        if (currentChunkIdx < totalChunks) {
          const promises = [];
          let bytesAdded = 0;
          for (let i = 0; i < BATCH_SIZE; i++) {
              const batchIdx = currentChunkIdx + i;
              if (batchIdx >= totalChunks) break;
              const start = batchIdx * CHUNK_SIZE;
              const end = Math.min(start + CHUNK_SIZE, task.file.size);
              const chunk = task.file.slice(start, end);
              const formData = new FormData();
              formData.append('chunk', chunk);
              formData.append('filename', task.name);
              formData.append('index', batchIdx);
              formData.append('total_chunks', totalChunks);
              formData.append('total_size', task.file.size);
              promises.push(axios.post('http://localhost:5000/upload_chunk', formData, { signal }).then(() => {
                  bytesAdded += (end - start);
                  setTasks(prev => {
                      const idx = prev.findIndex(t => t.id === task.id);
                      if (idx === -1 || prev[idx].status === 'cancelled') return prev;
                      const up = [...prev];
                      up[idx].progress = Math.round(((task.doneBytes + bytesAdded) / task.file.size) * 100);
                      return up;
                  });
              }));
          }
          await Promise.all(promises);
          const processed = promises.length;
          setTasks(prev => {
             const idx = prev.findIndex(t => t.id === task.id);
             if (idx === -1 || prev[idx].status === 'cancelled') return prev;
             const up = [...prev];
             up[idx].doneBytes += bytesAdded; // approx
             if (currentChunkIdx + processed >= totalChunks) {
                 up[idx].status = 'completed';
                 up[idx].progress = 100;
                 delete controllers.current[task.id];
                 setTimeout(fetchStatus, 500); 
             }
             return up;
          });
        }
      } 
      else if (task.type === 'download') {
        const currentChunkIdx = task.chunks.length;
        if (currentChunkIdx < task.totalChunks) {
          const promises = [];
          for (let i = 0; i < BATCH_SIZE; i++) {
              const batchIdx = currentChunkIdx + i;
              if (batchIdx >= task.totalChunks) break;
              promises.push(axios.get(`http://localhost:5000/download_chunk`, { params: { filename: task.name, index: batchIdx }, responseType: 'blob', signal }).then(res => ({ idx: batchIdx, data: res.data })));
          }
          const results = await Promise.all(promises);
          setTasks(prev => {
            const idx = prev.findIndex(t => t.id === task.id);
            if (idx === -1 || prev[idx].status === 'cancelled') return prev;
            const up = [...prev];
            results.sort((a,b) => a.idx - b.idx);
            results.forEach(r => { up[idx].chunks.push(r.data); up[idx].doneBytes += r.data.size; });
            up[idx].progress = Math.round((up[idx].doneBytes / task.totalBytes) * 100);
            if (up[idx].chunks.length >= task.totalChunks) {
                const blob = new Blob(up[idx].chunks);
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.setAttribute('download', task.name);
                document.body.appendChild(link);
                link.click();
                link.remove();
                up[idx].status = 'completed';
                delete controllers.current[task.id];
            }
            return up;
          });
        }
      }
    } catch (err) {
        if (!axios.isCancel(err)) {
            setTasks(prev => { const idx = prev.findIndex(t => t.id === task.id); if(idx!==-1) prev[idx].status='failed'; return [...prev]; });
            alert(`Transfer Failed: ${err.message}`);
        }
    }
    setProcessing(false);
  };

  useEffect(() => { if(!processing && !isPaused) processTasks(); }, [tasks, isPaused, processing]);

  const formatSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const addSpace = async () => { await axios.post('http://localhost:5000/add_space'); alert("Launching node..."); fetchStatus(); };
  const activeTasks = tasks.filter(t => t.status !== 'completed' && t.status !== 'cancelled' && t.status !== 'failed');

  return (
    <div style={styles.container}>
      <div style={styles.sidebar}>
        <div style={styles.logo}>☁️ SkyDrive</div>
        <label style={styles.addBtn}><span style={{ fontSize: '20px' }}>+</span> New Upload<input type="file" style={{ display: 'none' }} onChange={handleUpload} /></label>
        <button style={{...styles.addBtn, justifyContent: 'center'}} onClick={addSpace}>Add Space</button>
        <div style={styles.statBox}>
          <div style={{fontSize: '13px', color: '#5f6368'}}>Storage</div>
          <div style={{fontWeight: 'bold', margin: '5px 0'}}>{formatSize(stats.used)} used</div>
          <div style={{fontSize: '12px', color: '#5f6368'}}>of {formatSize(stats.quota)}</div>
          <div style={styles.progressBarBg}><div style={{...styles.progressBarFill, width: `${(stats.used / stats.quota) * 100}%`}}></div></div>
          <div style={{fontSize: '11px', marginTop: '10px', color: '#1a73e8'}}>● {stats.nodes_online} Active Nodes</div>
        </div>
      </div>
      <div style={styles.main}>
        <div style={styles.sectionTitle}>My Files</div>
        <div style={styles.fileGrid}>
          {files.map(file => (
            <div key={file} style={styles.fileCard}>
              <div style={styles.fileIcon} onClick={() => handleDownload(file)}>📄</div>
              <div style={styles.fileName}>{file}</div>
              <div style={styles.btnGroup}>
                <button style={styles.actionBtn} onClick={() => handleDownload(file)}>Download</button>
                <button style={styles.deleteBtn} onClick={(e) => handleDelete(file, e)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      </div>
      {activeTasks.length > 0 && (
        <div style={styles.progressCard}>
          <div style={styles.progressHeader}><span>Active Tasks</span><button onClick={() => setIsPaused(!isPaused)} style={styles.ctrlBtn}>{isPaused ? "▶" : "⏸"}</button></div>
          <div style={styles.progressBody}>
            {activeTasks.map((task) => (
              <div key={task.id} style={{marginBottom: '15px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '5px'}}>
                  <span style={{fontWeight: 'bold'}}>{task.type === 'upload' ? '⬆' : '⬇'} {task.name}</span>
                  <button onClick={() => handleCancel(task.id)} style={{color: 'red', border:'none', background:'none', cursor:'pointer'}}>Cancel</button>
                </div>
                <div style={{fontSize: '11px', color: '#666', marginBottom: '5px'}}>{task.progress}%</div>
                <div style={{height: '4px', background: '#f1f3f4', borderRadius: '2px'}}><div style={{width: `${task.progress}%`, height: '100%', background: task.type === 'upload' ? '#1a73e8' : '#0f9d58', transition: 'width 0.2s'}}></div></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
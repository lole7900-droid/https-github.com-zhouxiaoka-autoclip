import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Bell, ChevronDown, Clapperboard, Clock3, Download, FolderOpen, Grid2X2,
  HelpCircle, Home, Instagram, LayoutTemplate, MoreHorizontal, Play,
  Plus, Search, Settings2, Sparkles, Upload, WandSparkles, Youtube
} from 'lucide-react';
import './styles.css';

const clips = [
  { title: '3 cách xây thói quen tốt', time: '00:42', score: '92', color: 'orange', tag: 'Mẹo hay' },
  { title: 'Khoảnh khắc bất ngờ nhất', time: '00:28', score: '89', color: 'violet', tag: 'Cảm xúc' },
  { title: 'Một ngày làm việc hiệu quả', time: '00:54', score: '86', color: 'blue', tag: 'Năng suất' },
];

function App() {
  const [tab, setTab] = useState('Tất cả');
  const [selected, setSelected] = useState(0);
  const [toast, setToast] = useState('');
  const [search, setSearch] = useState('');
  const [file, setFile] = useState(null);
  const [upload, setUpload] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState({ language: 'vi', provider: 'openai', model: 'gpt-4o-mini-transcribe', aspect_ratio: '9:16', length: 45, count: 3 });
  const filtered = useMemo(() => clips.filter(c => c.title.toLowerCase().includes(search.toLowerCase())), [search]);
  const notify = (message) => { setToast(message); window.setTimeout(() => setToast(''), 2600); };
  const updateConfig = (key, value) => setConfig(current => ({ ...current, [key]: value }));
  const uploadVideo = async () => {
    if (!file) return notify('Hãy chọn một file video trước.');
    setBusy(true);
    try {
      const body = new FormData(); body.append('video', file);
      const response = await fetch('/api/uploads', { method: 'POST', body }); const data = await response.json();
      if (!response.ok) throw new Error(data.error); setUpload(data); notify('Tải video thành công. Hãy chọn cấu hình AI.');
    } catch (error) { notify(error.message || 'Không thể tải video lên.'); } finally { setBusy(false); }
  };
  const startJob = async () => {
    if (!upload) return notify('Tải video lên trước khi phân tích.'); setBusy(true);
    try { const response = await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ video_id: upload.id, config }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error); setJob(data); notify('Đã gửi video vào pipeline AI.'); }
    catch (error) { notify(error.message || 'Không thể khởi động pipeline.'); } finally { setBusy(false); }
  };
  React.useEffect(() => { if (!job || ['ready', 'complete', 'error'].includes(job.status)) return; const timer = window.setInterval(async () => { const response = await fetch(`/api/jobs/${job.id}`); if (response.ok) setJob(await response.json()); }, 1600); return () => window.clearInterval(timer); }, [job]);
  const exportShort = async (highlight) => { try { const response = await fetch(`/api/jobs/${job.id}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ highlight_id: highlight.id }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error); setJob(data); notify('Đang cắt, đóng khung 9:16 và gắn caption...'); } catch (error) { notify(error.message); } };

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Clapperboard size={21}/></span><span>autoclip</span></div>
      <button className="create-button" onClick={() => document.getElementById('creator')?.scrollIntoView({ behavior: 'smooth' })}><Plus size={19}/> Tạo Short mới</button>
      <nav>
        <a className="active"><Home size={19}/> Trang chủ</a>
        <a><Clapperboard size={19}/> Dự án của tôi <b>3</b></a>
        <a><LayoutTemplate size={19}/> Mẫu Shorts</a>
      </nav>
      <div className="sidebar-bottom">
        <a><FolderOpen size={19}/> Thư viện</a>
        <a><Settings2 size={19}/> Cài đặt</a>
        <div className="help-card"><span className="help-icon"><HelpCircle size={18}/></span><div><strong>Cần trợ giúp?</strong><small>Xem hướng dẫn nhanh</small></div></div>
        <div className="profile"><div className="avatar">NT</div><div><strong>Ngọc Trần</strong><small>Gói Pro</small></div><MoreHorizontal size={18}/></div>
      </div>
    </aside>

    <section className="content">
      <header className="topbar"><div className="crumb">Trang chủ <span>/</span> <strong>Tổng quan</strong></div><div className="top-actions"><button className="icon-button"><Bell size={20}/><i/></button><button className="upgrade" onClick={() => notify('Bạn đang dùng gói Pro!')}><Sparkles size={16}/> Nâng cấp</button></div></header>
      <div className="workspace">
        <section className="hero">
          <div className="hero-copy"><p className="eyebrow"><Sparkles size={15}/> AI SHORTS STUDIO</p><h1>Biến video dài thành<br/><em>Shorts nổi bật.</em></h1><p>Tải lên một video, AutoClip sẽ tìm những khoảnh khắc đáng xem nhất và biến chúng thành video ngắn sẵn sàng đăng tải.</p><div className="hero-actions"><button className="primary" onClick={() => document.getElementById('creator')?.scrollIntoView({ behavior: 'smooth' })}><Upload size={18}/> Tải video lên</button><button className="secondary" onClick={() => notify('Thư viện mẫu đang được phát triển')}><Grid2X2 size={18}/> Khám phá mẫu</button></div></div>
          <div className="hero-visual"><div className="ring ring-one"/><div className="ring ring-two"/><div className="phone"><div className="phone-top"><span/><span/><span/></div><div className="video-scene"><div className="sun"/><div className="hill hill-back"/><div className="hill hill-front"/><div className="person"><div className="head"/><div className="body"/></div></div><div className="caption">BÍ QUYẾT ĐỂ<br/><b>SỐNG TÍCH CỰC</b></div><div className="audio">♫  Chạm để nghe câu chuyện</div></div><div className="mini-tag tag-one"><WandSparkles size={15}/><span>AI tìm highlight</span></div><div className="mini-tag tag-two"><span className="check">✓</span><span>Sẵn sàng đăng</span></div></div>
        </section>

        <section className="creator-panel" id="creator"><div className="creator-heading"><div><p className="eyebrow"><WandSparkles size={15}/> TẠO SHORT THẬT</p><h2>Thiết lập pipeline tạo video</h2><p>Video được lưu tại server, transcript được phân tích rồi xuất bằng FFmpeg.</p></div><span className="secure">Tệp chỉ dùng cho job này</span></div><div className="creator-grid"><label className={`dropzone ${file ? 'has-file' : ''}`}><input type="file" accept="video/mp4,video/quicktime,video/x-matroska,video/webm" onChange={e => { setFile(e.target.files?.[0] || null); setUpload(null); setJob(null); }}/><Upload size={23}/><strong>{file ? file.name : 'Chọn video nguồn'}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : 'MP4, MOV, MKV hoặc WebM'}</small></label><div className="settings-grid"><label>Ngôn ngữ<select value={config.language} onChange={e => updateConfig('language', e.target.value)}><option value="vi">Tiếng Việt</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option></select></label><label>AI provider<select value={config.provider} onChange={e => updateConfig('provider', e.target.value)}><option value="openai">OpenAI</option></select></label><label>AI model<select value={config.model} onChange={e => updateConfig('model', e.target.value)}><option value="gpt-4o-mini-transcribe">GPT-4o mini Transcribe</option><option value="whisper-1">Whisper-1</option></select></label><label>Tỷ lệ xuất<select value={config.aspect_ratio} onChange={e => updateConfig('aspect_ratio', e.target.value)}><option>9:16</option></select></label><label>Thời lượng Short<select value={config.length} onChange={e => updateConfig('length', Number(e.target.value))}><option value="30">30 giây</option><option value="45">45 giây</option><option value="60">60 giây</option></select></label><label>Số lượng Short<select value={config.count} onChange={e => updateConfig('count', Number(e.target.value))}><option value="1">1 Short</option><option value="3">3 Shorts</option><option value="5">5 Shorts</option></select></label></div></div><div className="creator-actions"><span>{upload ? `✓ ${upload.name} đã ở server` : '1. Tải video để tiếp tục'}</span><button className="secondary" disabled={busy} onClick={uploadVideo}><Upload size={16}/>{busy ? 'Đang tải...' : 'Tải lên'}</button><button className="primary" disabled={busy || !upload} onClick={startJob}><WandSparkles size={16}/>{busy ? 'Đang khởi tạo...' : 'Phân tích với AI'}</button></div></section>

        {job && <section className={`progress-card ${job.status === 'error' ? 'is-error' : ''}`}><div className="progress-header"><div><span className="status-dot"/><strong>{job.status === 'error' ? 'Pipeline gặp lỗi' : job.status === 'ready' ? 'Đề xuất đã sẵn sàng' : job.status === 'complete' ? 'Short đã được xuất' : 'Đang xử lý video'}</strong><p>{job.error || `${job.progress}% hoàn thành — ${job.status}`}</p></div>{job.output && <a className="download-link" href={job.output} download><Download size={16}/> Tải Short</a>}</div><div className="progress-bar"><i style={{ width: `${job.progress}%` }}/></div><div className="progress-steps">{['Tải lên', 'Transcript', 'Phân tích AI', 'Xuất Short'].map((step, index) => <span key={step} className={job.progress >= [4, 18, 58, 76][index] ? 'done' : ''}>{index + 1}. {step}</span>)}</div></section>}

        {job?.highlights && <section className="suggestions"><div className="section-title"><div><h2>Đoạn AI đề xuất</h2><p>Chọn một khoảnh khắc để cắt video 9:16 và chèn caption.</p></div></div><div className="suggestion-list">{job.highlights.map(highlight => <article key={highlight.id}><span className="highlight-score"><Sparkles size={15}/>{highlight.score}</span><div><h3>{highlight.title}</h3><p>{highlight.content}</p><small>{highlight.start.toFixed(2)}s — {highlight.end.toFixed(2)}s</small></div><button className="primary" onClick={() => exportShort(highlight)}><Clapperboard size={16}/> Tạo Short</button></article>)}</div></section>}

        <section className="analysis-card">
          <div className="analysis-copy"><span className="analysis-icon"><WandSparkles size={21}/></span><div><h2>Để AI tìm những đoạn hay nhất cho bạn</h2><p>Hệ thống phân tích video vẫn ở đây — nhanh hơn, trực quan hơn.</p></div></div>
          <div className="analysis-steps"><span><b>1</b>Tải video</span><hr/><span><b>2</b>AI phân tích</span><hr/><span><b>3</b>Chọn & xuất Short</span></div>
          <button className="start-analysis" onClick={() => notify('Bắt đầu phân tích video mới')}>Bắt đầu <ChevronDown size={16}/></button>
        </section>

        <section className="projects"><div className="section-title"><div><h2>Shorts gần đây</h2><p>Tiếp tục chỉnh sửa hoặc xuất video của bạn.</p></div><button onClick={() => notify('Đang mở tất cả dự án')}>Xem tất cả <span>→</span></button></div><div className="tabs">{['Tất cả', 'Bản nháp', 'Đã xuất'].map(x => <button key={x} onClick={() => setTab(x)} className={tab === x ? 'selected' : ''}>{x}</button>)}<label><Search size={17}/><input placeholder="Tìm video..." value={search} onChange={e => setSearch(e.target.value)}/></label></div>
          <div className="clip-grid">{filtered.map((clip, i) => <article className="clip-card" key={clip.title} onClick={() => setSelected(i)}><div className={`thumbnail ${clip.color}`}><div className="vertical-preview"><div className="preview-gradient"/><span className="big-number">0{i + 1}</span><span className="preview-text">{clip.tag}<br/><b>mỗi ngày</b></span></div><span className="duration"><Clock3 size={12}/>{clip.time}</span><button className="play"><Play size={17} fill="currentColor"/></button>{selected === i && <span className="now-editing">Đang chọn</span>}</div><div className="clip-info"><div><h3>{clip.title}</h3><p>Hôm nay, 10:24</p></div><span className="score"><Sparkles size={13}/>{clip.score}</span></div><div className="clip-footer"><span><Youtube size={16}/> YouTube Shorts</span><button onClick={(e) => {e.stopPropagation(); notify('Đang chuẩn bị xuất video...')}}><Download size={16}/> Xuất</button></div></article>)}</div>
        </section>
      </div>
    </section>
    {toast && <div className="toast"><Sparkles size={17}/>{toast}</div>}
  </main>;
}

createRoot(document.getElementById('root')).render(<App/>);

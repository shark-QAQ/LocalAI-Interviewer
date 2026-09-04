import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import { PageTitle, SubTitle, Card, InkButton, Toast, InkDivider, Modal, StatusChip, ProgressBar } from '../components'

export default function ResumesPage() {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [toast, setToast] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const [knownResumes, setKnownResumes] = useState<any[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 简历项目 ↔ 代码库 待人工确认的映射
  const [mapPending, setMapPending] = useState<{
    resumeId: string; projects: { name: string; status: string }[]; codeRepos: string[];
  } | null>(null)
  const [mapDrafts, setMapDrafts] = useState<Record<string, string>>({})
  const [mappingSaving, setMappingSaving] = useState(false)

  const loadCodeMapping = async (list: any[]) => {
    if (!list || list.length === 0) { setMapPending(null); return }
    try {
      const id = list[0].id
      const m = await api.getResumeCodeMapping(id)
      const pend = (m.projects || []).filter(p => p.status === 'pending')
      if (pend.length) {
        setMapPending({ resumeId: id, projects: pend, codeRepos: m.code_repos || [] })
        setMapDrafts({})
      } else {
        setMapPending(null)
      }
    } catch { setMapPending(null) }
  }

  const loadKnownResumes = async () => {
    try {
      const list = await api.listResumes()
      setKnownResumes(list)
      await loadCodeMapping(list)
    } catch {}
  }

  const saveMap = async (name: string) => {
    if (!mapPending || !(name in mapDrafts)) return
    const repo = mapDrafts[name] ?? ''
    setMappingSaving(true); setToast('')
    try {
      await api.setResumeCodeMapping(mapPending.resumeId, name, repo || null)
      setToast(repo ? `已确认「${name}」↔ ${repo}` : `已确认「${name}」无对应代码库`)
      await loadCodeMapping(knownResumes)
    } catch (e: any) { setToast(e.message) }
    finally { setMappingSaving(false) }
  }

  useEffect(() => { loadKnownResumes() }, [])

  useEffect(() => {
    const pending = knownResumes.filter(r => r.index_status === 'processing' || r.index_status === 'idle')
    if (pending.length === 0) {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
      return
    }
    const poll = async () => {
      let allDone = true
      for (const r of pending) {
        try {
          const full = await api.getResume(r.id)
          if (full.index_status === 'processing' || full.index_status === 'idle') allDone = false
          setKnownResumes(prev => prev.map(item => item.id === r.id ? {
            ...item,
            index_status: full.index_status,
            chunk_count: full.chunk_count,
            indexed_chunks: full.indexed_chunks,
            total_chunks: full.total_chunks,
          } : item))
        } catch { allDone = false }
      }
      if (allDone && pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
    }
    poll()
    pollingRef.current = setInterval(poll, 3000)
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
  }, [knownResumes.length])

  const handleUpload = async () => {
    if (!file) { setToast('请选择简历文件（PDF/DOCX）'); return }
    setUploading(true); setToast('')
    try {
      await api.uploadResume(file)
      setToast('简历上传成功，正在向量化...')
      loadKnownResumes()
      setFile(null)
    } catch (e: any) {
      setToast(e.message)
    } finally { setUploading(false) }
  }

  const handleRename = async (id: string) => {
    if (!editName.trim()) return
    try { await api.renameResume(id, editName.trim()); setEditingId(null); loadKnownResumes(); setToast('重命名成功') }
    catch (e: any) { setToast(e.message) }
  }

  const handleDelete = async (id: string) => {
    try { await api.deleteResume(id); setConfirmDelete(null); loadKnownResumes(); setToast('已删除') }
    catch (e: any) { setToast(e.message) }
  }

  const statusMap: Record<string, string> = { idle: '空闲', processing: '向量化中', completed: '已完成', failed: '失败' }
  const statusColor: Record<string, string> = { idle: 'var(--ink-light)', processing: 'var(--water-blue)', completed: 'var(--jade-green)', failed: 'var(--seal-red)' }
  const resumePct = (r: any) => (r.total_chunks && r.indexed_chunks != null
    ? Math.round((r.indexed_chunks / r.total_chunks) * 100)
    : null)

  return (
    <div>
      <PageTitle>拜帖</PageTitle>
      <SubTitle>递上拜帖，让面试官了解你的才学</SubTitle>
      {toast && <Toast message={toast} type={toast.includes('失败') || toast.includes('错误') ? 'error' : 'info'} />}

      {confirmDelete && (
        <Modal onClose={() => setConfirmDelete(null)}>
          <div style={{ padding: '24px 20px' }}>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--seal-red)', marginBottom: 12 }}>确认删除</h3>
            <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-medium)', marginBottom: 20 }}>
              删除后该简历及其向量数据将被永久移除，确定要删除吗？
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <InkButton variant="ghost" onClick={() => setConfirmDelete(null)}>取消</InkButton>
              <button onClick={() => handleDelete(confirmDelete!)} style={{
                padding: '10px 24px', background: 'var(--seal-red)', color: 'var(--paper-white)',
                border: 'none', borderRadius: 3, cursor: 'pointer', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14,
              }}>确认删除</button>
            </div>
          </div>
        </Modal>
      )}

      <Card>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>上传简历</h3>
        <div style={{
          border: '2px dashed var(--paper-dark)', borderRadius: 4,
          padding: '40px 20px', textAlign: 'center', cursor: 'pointer',
          background: file ? 'rgba(194,58,43,0.03)' : 'rgba(255,255,255,0.3)',
          transition: 'all 0.3s',
        }} onClick={() => inputRef.current?.click()}>
          <input ref={inputRef} type="file" accept=".pdf,.docx" hidden onChange={(e) => setFile(e.target.files?.[0] || null)} />
          {file ? (
            <>
              <div style={{ fontSize: 32, marginBottom: 8 }}>&#128220;</div>
              <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-dark)' }}>{file.name}</p>
              <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginTop: 4 }}>
                {(file.size / 1024).toFixed(1)} KB &middot; 点击更换
              </p>
            </>
          ) : (
            <>
              <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.3 }}>&#128196;</div>
              <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14, color: 'var(--ink-light)' }}>
                点击选择简历（PDF / DOCX）
              </p>
            </>
          )}
        </div>
        <div style={{ marginTop: 20 }}>
          <InkButton onClick={handleUpload} disabled={uploading || !file}>
            {uploading ? '解析中...' : '呈递拜帖'}
          </InkButton>
        </div>
      </Card>

      {mapPending && mapPending.projects.length > 0 && (
        <Card style={{ marginTop: 24, borderTop: '3px solid var(--seal-red)' }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--ink-dark)', marginBottom: 8 }}>
            ⚠ 待确认：简历项目 ↔ 代码库
          </h3>
          <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginBottom: 16 }}>
            以下简历项目没能自动匹配到唯一代码库，请手动确认（可选“无对应代码库”）。确认后即作为面试出题的取材对应。
          </p>
          {mapPending.projects.map(p => (
            <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
              <span style={{ flex: 1, fontFamily: "'Noto Serif SC', serif", fontSize: 13, color: 'var(--ink-dark)' }}>{p.name}</span>
              <select
                value={mapDrafts[p.name] ?? ''}
                onChange={e => setMapDrafts(prev => ({ ...prev, [p.name]: e.target.value }))}
                style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 13, padding: '6px 8px', border: '1px solid var(--paper-dark)', borderRadius: 4, background: 'rgba(255,255,255,0.6)', outline: 'none' }}
              >
                <option value="">— 无对应代码库 —</option>
                {mapPending.codeRepos.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              <button onClick={() => saveMap(p.name)} disabled={mappingSaving || !(p.name in mapDrafts)}
                style={{
                  padding: '6px 16px', fontSize: 13, fontFamily: "'ZCOOL XiaoWei', serif",
                  cursor: (mappingSaving || !(p.name in mapDrafts)) ? 'not-allowed' : 'pointer',
                  background: (mappingSaving || !(p.name in mapDrafts)) ? 'var(--ink-faint)' : 'var(--seal-red)',
                  color: '#fff', border: 'none', borderRadius: 999,
                  opacity: (mappingSaving || !(p.name in mapDrafts)) ? 0.6 : 1,
                }}>
                确认
              </button>
            </div>
          ))}
        </Card>
      )}

      {knownResumes.length > 0 && (
        <Card style={{ marginTop: 24 }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--ink-dark)', marginBottom: 16 }}>拜帖录</h3>
          {knownResumes.map((r: any) => (
            <div key={r.id}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0' }}>
                {editingId === r.id ? (
                  <>
                    <input value={editName} onChange={e => setEditName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleRename(r.id) }} autoFocus
                      style={{ flex: 1, padding: '6px 10px', fontSize: 14, fontFamily: "'Noto Serif SC', serif", border: '1px solid var(--paper-dark)', borderRadius: 3, outline: 'none' }} />
                    <button onClick={() => handleRename(r.id)} style={{ fontSize: 12, color: 'var(--jade-green)', cursor: 'pointer', background: 'none', border: 'none' }}>保存</button>
                    <button onClick={() => setEditingId(null)} style={{ fontSize: 12, color: 'var(--ink-light)', cursor: 'pointer', background: 'none', border: 'none' }}>取消</button>
                  </>
                ) : (
                  <>
                    <span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 16, color: 'var(--ink-dark)' }}>{r.candidate_name}</span>
                    <span style={{ fontSize: 11, color: 'var(--ink-faint)' }}>{r.chunk_count || 0} 块</span>
                    <StatusChip status={r.index_status || 'completed'} labels={statusMap} colors={statusColor} />
                    <button onClick={() => { setEditingId(r.id); setEditName(r.candidate_name) }}
                      style={{ fontSize: 12, color: 'var(--water-blue)', cursor: 'pointer', background: 'none', border: 'none', marginLeft: 'auto' }}>重命名</button>
                    <button onClick={() => setConfirmDelete(r.id)}
                      style={{ fontSize: 12, color: 'var(--seal-red)', cursor: 'pointer', background: 'none', border: 'none' }}>删除</button>
                  </>
                )}
              </div>
              {(r.index_status === 'processing' || r.index_status === 'idle') && r.total_chunks > 0 && (
                <div style={{ marginTop: 8, marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, color: 'var(--ink-light)' }}>向量化进度</span>
                    <span style={{ fontFamily: "'Noto Serif SC', monospace", fontSize: 11, color: 'var(--water-blue)' }}>
                      {r.indexed_chunks || 0}/{r.total_chunks || 0}{resumePct(r) != null ? ` (${resumePct(r)}%)` : ''}
                    </span>
                  </div>
                  <ProgressBar pct={resumePct(r)} />
                </div>
              )}
              <InkDivider />
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}

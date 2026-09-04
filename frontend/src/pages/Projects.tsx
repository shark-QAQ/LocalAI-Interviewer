import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import { PageTitle, SubTitle, Card, InkButton, InkInput, Toast, LoadingDots, InkDivider, Modal, FolderPicker, StatusChip, ProgressBar } from '../components'

interface DirItem { name: string; path: string }
interface IndexResult { name: string; path: string; project_id?: string; error?: string | null }

// “导入代码库”可单文件导入的代码/文档类型（与后端 settings.allowed_extensions 保持一致）
const CODE_EXTS = ['.java', '.py', '.js', '.ts', '.go', '.md', '.yaml', '.yml', '.sql',
  '.kt', '.scala', '.rs', '.c', '.cpp', '.h', '.cs', '.rb', '.php']

// “我的资料”可导入的文档格式（与 FolderPicker 默认一致，这里仅用于给单个文件的默认资料名去扩展名）
const DOC_EXTS = ['.pdf', '.docx', '.txt', '.md', '.markdown']

const STORAGE_KEY = 'localai-indexing-state'
const COMPLETED_KEY = 'localai-completed-projects'

function loadPersisted(): IndexResult[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}
function savePersisted(r: IndexResult[]) { localStorage.setItem(STORAGE_KEY, JSON.stringify(r)) }
function loadCompletedIds(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(COMPLETED_KEY) || '[]')) } catch { return new Set() }
}
function saveCompletedIds(ids: Set<string>) { localStorage.setItem(COMPLETED_KEY, JSON.stringify([...ids])) }

export default function ProjectsPage() {
  const [parentPath, setParentPath] = useState('')
  const [subDirs, setSubDirs] = useState<DirItem[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [force, setForce] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<IndexResult[]>(loadPersisted)
  const [allStatus, setAllStatus] = useState<Record<string, any>>({})
  const [toast, setToast] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerDirs, setPickerDirs] = useState<DirItem[]>([])
  const [pickerFiles, setPickerFiles] = useState<DirItem[]>([])
  const [pickerFile, setPickerFile] = useState<DirItem | null>(null)
  const [pickerParent, setPickerParent] = useState('')
  const [pickerCurrent, setPickerCurrent] = useState('')
  const [pickerLoading, setPickerLoading] = useState(false)
  const [browseInput, setBrowseInput] = useState('')
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [knownProjects, setKnownProjects] = useState<any[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [showCompleteModal, setShowCompleteModal] = useState(false)
  const [completedProjectIds, setCompletedProjectIds] = useState<Set<string>>(loadCompletedIds)
  const [dismissed, setDismissed] = useState(() => {
    const pending = loadPersisted().filter(r => r.project_id && !r.error)
    return pending.length === 0
  })

  // —— 我的资料（全局资料库，参与所有面试的综合出题） ——
  const [knownMaterials, setKnownMaterials] = useState<any[]>([])
  const [matEditingId, setMatEditingId] = useState<string | null>(null)
  const [matEditName, setMatEditName] = useState('')
  const [matConfirmDelete, setMatConfirmDelete] = useState<string | null>(null)
  const [dirPath, setDirPath] = useState('')
  const [dirName, setDirName] = useState('')
  const [dirImporting, setDirImporting] = useState(false)
  const [dirPickerOpen, setDirPickerOpen] = useState(false)

  useEffect(() => { savePersisted(results) }, [results])
  useEffect(() => { saveCompletedIds(completedProjectIds) }, [completedProjectIds])

  // poll indexing progress
  useEffect(() => {
    const pending = results.filter(r => r.project_id && !r.error && !completedProjectIds.has(r.project_id))
    if (pending.length === 0) {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
      if (loading) setLoading(false)
      return
    }
    const poll = async () => {
      let allDone = true
      for (const r of pending) {
        if (!r.project_id) continue
        try {
          const s = await api.getProjectStatus(r.project_id)
          setAllStatus(prev => ({ ...prev, [r.project_id!]: s }))
          if (s.index_status === 'processing' || s.index_status === 'idle') allDone = false
        } catch { allDone = false }
      }
      if (allDone) {
        if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
        setLoading(false)
        const ids = new Set(pending.map(r => r.project_id!).filter(Boolean))
        setCompletedProjectIds(prev => new Set([...prev, ...ids]))
        setShowCompleteModal(true)
        // clear persisted results since all done
        setResults([])
        localStorage.removeItem(STORAGE_KEY)
      }
    }
    poll()
    pollingRef.current = setInterval(poll, 2000)
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
  }, [results])

  const loadKnownProjects = async () => {
    try { setKnownProjects(await api.listProjects()) } catch {}
  }
  useEffect(() => { loadKnownProjects() }, [])

  const loadPickerDirs = async (p: string) => {
    setPickerLoading(true)
    setPickerFile(null)
    try {
      const res = await api.listDirs(p, CODE_EXTS)
      setPickerDirs(res.dirs || []); setPickerFiles(res.files || [])
      setPickerParent(res.parent); setPickerCurrent(p); setBrowseInput(p)
    } catch (e: any) { setToast(e.message); setPickerDirs([]); setPickerFiles([]) }
    finally { setPickerLoading(false) }
  }

  const openPicker = () => { setPickerOpen(true); loadPickerDirs(browseInput || '') }
  const handlePickerSelect = (d: DirItem) => loadPickerDirs(d.path)
  const handlePickerConfirm = () => { setParentPath(pickerCurrent); loadSubDirs(pickerCurrent); setPickerOpen(false) }
  // 返回上级目录（清空当前选中的文件，重新展示父目录内容）
  const goPickerUp = () => { if (pickerParent) loadPickerDirs(pickerParent) }

  // 点代码文件 = 先选中（可再点取消、改选其它，或点“.. / 上级目录”退回），确认后才以单篇研读
  const togglePickerFile = (f: DirItem) =>
    setPickerFile(prev => (prev && prev.path === f.path ? null : f))

  // 浏览确认一个代码文件 → 把它作为独立经卷著录入知识宝库
  const handlePickerFile = async (f: DirItem) => {
    setPickerOpen(false)
    const base = f.name
    const dot = base.lastIndexOf('.')
    const name = dot > 0 ? base.slice(0, dot) : base
    setParentPath(f.path)
    setSubDirs([])
    setSelected(new Set())
    setLoading(true); setToast('')
    try {
      const res = await api.initProject(name, f.path, force)
      setResults(prev => [...prev, { name, path: f.path, ...res, error: null }])
      setToast(`已将「${name}」付之研读`)
    } catch (err: any) { setToast(err.message) }
    finally { setLoading(false) }
  }

  const loadSubDirs = async (p: string) => {
    try { const res = await api.listDirs(p); setSubDirs(res.dirs); setSelected(new Set(res.dirs.map(d => d.path))) }
    catch { setSubDirs([]); setSelected(new Set()) }
  }

  const toggleSelect = (p: string) => setSelected(prev => { const n = new Set(prev); n.has(p) ? n.delete(p) : n.add(p); return n })
  const toggleAll = () => selected.size === subDirs.length ? setSelected(new Set()) : setSelected(new Set(subDirs.map(d => d.path)))

  const handleBatchIndex = async () => {
    if (selected.size === 0) { setToast('请至少选择一个项目'); return }
    setLoading(true); setToast(''); setCompletedProjectIds(new Set())
    const newResults: IndexResult[] = []
    for (const dir of subDirs) {
      if (!selected.has(dir.path)) continue
      try { const res = await api.initProject(dir.name, dir.path, force); newResults.push({ name: dir.name, path: dir.path, ...res, error: null }) }
      catch (err: any) { newResults.push({ name: dir.name, path: dir.path, error: err.message }) }
    }
    setResults(prev => [...prev, ...newResults])
    setToast(`已将 ${newResults.length} 个项目付之研读`)
  }

  const handleRename = async (id: string) => {
    if (!editName.trim()) return
    try { await api.renameProject(id, editName.trim()); setEditingId(null); loadKnownProjects(); setToast('更名已成') }
    catch (e: any) { setToast(e.message) }
  }

  const handleDelete = async (id: string) => {
    try { await api.deleteProject(id); setConfirmDelete(null); loadKnownProjects(); setResults(prev => prev.filter(r => r.project_id !== id)); setToast('已删除') }
    catch (e: any) { setToast(e.message) }
  }

  // —— 我的资料：加载 / 轮询 / 上传 / 改名 / 删除 ——
  const loadMaterials = async () => {
    try { setKnownMaterials(await api.listMaterials()) } catch {}
  }
  useEffect(() => { loadMaterials() }, [])

  const matStartedRef = useRef<Record<string, number>>({})
  const busyMaterials = knownMaterials.some(r => r.index_status === 'processing' || r.index_status === 'idle')

  useEffect(() => {
    // 记录每个“索引中”资料的起始时间，用于估算剩余时间
    knownMaterials.forEach((m: any) => {
      if (m.index_status === 'processing') {
        if (matStartedRef.current[m.id] == null) matStartedRef.current[m.id] = Date.now()
      } else {
        delete matStartedRef.current[m.id]
      }
    })
  }, [knownMaterials])

  useEffect(() => {
    if (!busyMaterials) return
    const t = setInterval(loadMaterials, 2000)
    return () => clearInterval(t)
  }, [busyMaterials])

  const matEta = (m: any) => {
    const started = matStartedRef.current[m.id]
    if (m.index_status !== 'processing' || !started || !m.total_chunks || !m.indexed_chunks) return null
    const elapsed = (Date.now() - started) / 1000
    const rate = m.indexed_chunks / elapsed
    if (rate <= 0) return null
    const remaining = (m.total_chunks - m.indexed_chunks) / rate
    return remaining < 60 ? `~${Math.ceil(remaining)}秒` : `~${Math.ceil(remaining / 60)}分钟`
  }

  const handleMatRename = async (id: string) => {
    if (!matEditName.trim()) return
    try {
      await api.renameMaterial(id, matEditName.trim())
      setMatEditingId(null); loadMaterials(); setToast('已更名')
    } catch (e: any) { setToast(e.message) }
  }

  const handleMatDelete = async (id: string) => {
    try {
      await api.deleteMaterial(id)
      setMatConfirmDelete(null); loadMaterials(); setToast('已删除')
    } catch (e: any) { setToast(e.message) }
  }

  // —— 我的资料：按本地路径导入整个文件夹或单个文件 ——
  const handleDirPick = (p: string) => {
    setDirPath(p)
    if (!dirName.trim()) {
      const base = p.split(/[\\/]/).pop() || p
      const dot = base.lastIndexOf('.')
      const ext = dot > 0 ? '.' + base.slice(dot + 1).toLowerCase() : ''
      setDirName(DOC_EXTS.includes(ext) ? base.slice(0, dot) : base)
    }
    setDirPickerOpen(false)
  }

  const handleDirImport = async () => {
    if (!dirPath.trim()) { setToast('请选择要导入的本地路径（文件夹或文件）'); return }
    setDirImporting(true); setToast('')
    try {
      const res = await api.importMaterial(dirPath.trim(), dirName.trim() || undefined)
      setToast(`已收录「${res.name}」（${res.file_count ?? ''}篇），正开卷研读…`)
      loadMaterials()
      setDirName('')
    } catch (e: any) { setToast(e.message) }
    finally { setDirImporting(false) }
  }

  const calcETA = (r: IndexResult) => {
    const s = allStatus[r.project_id || '']
    if (!s || s.index_status !== 'processing' || !s.total_chunks || !s.indexed_chunks || !s.index_started_at) return null
    const elapsed = (Date.now() - new Date(s.index_started_at).getTime()) / 1000
    const rate = s.indexed_chunks / elapsed
    if (rate <= 0) return null
    const remaining = (s.total_chunks - s.indexed_chunks) / rate
    if (remaining < 60) return `~${Math.ceil(remaining)}秒`
    return `~${Math.ceil(remaining / 60)}分钟`
  }

  const statusMap: Record<string, string> = { idle: '待研读', processing: '研读中', completed: '已藏入', failed: '未成' }
  const statusColor: Record<string, string> = { idle: 'var(--ink-light)', processing: 'var(--water-blue)', completed: 'var(--jade-green)', failed: 'var(--seal-red)' }

  return (
    <div>
      <PageTitle>藏经阁</PageTitle>
      <SubTitle>录入代码与资料，筑就你的知识宝库</SubTitle>
      {toast && <Toast message={toast} type={toast.includes('失败') || toast.includes('错误') ? 'error' : 'info'} />}

      {showCompleteModal && (
        <Modal onClose={() => setShowCompleteModal(false)}>
          <div style={{ textAlign: 'center', padding: '24px 20px' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>&#10003;</div>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 24, color: 'var(--ink-dark)', marginBottom: 8 }}>全部研读完成</h3>
            <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-medium)', marginBottom: 20 }}>
              {results.filter(r => !r.error).length} 个项目已安然藏入知识宝库
            </p>
            <InkButton onClick={() => setShowCompleteModal(false)}>确定</InkButton>
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <Modal onClose={() => setConfirmDelete(null)}>
          <div style={{ padding: '24px 20px' }}>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--seal-red)', marginBottom: 12 }}>确认删除</h3>
            <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-medium)', marginBottom: 20 }}>
              删除后该项目及其向量数据将被永久移除，确定要删除吗？
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <InkButton variant="ghost" onClick={() => setConfirmDelete(null)}>取消</InkButton>
              <button onClick={() => handleDelete(confirmDelete)} style={{
                padding: '10px 24px', background: 'var(--seal-red)', color: 'var(--paper-white)',
                border: 'none', borderRadius: 3, cursor: 'pointer', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14,
              }}>确认删除</button>
            </div>
          </div>
        </Modal>
      )}

      {pickerOpen && (
        <Modal onClose={() => setPickerOpen(false)}>
          <div style={{ width: 500, maxHeight: '70vh', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--paper-dark)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--ink-dark)' }}>选择目录 / 代码文件</span>
              <span onClick={() => setPickerOpen(false)} style={{ cursor: 'pointer', fontSize: 18, color: 'var(--ink-light)' }}>&times;</span>
            </div>
            <div style={{ padding: '10px 20px', borderBottom: '1px solid var(--paper-dark)' }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <input value={browseInput} onChange={e => setBrowseInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') loadPickerDirs(browseInput) }}
                  placeholder="输入路径后回车"
                  style={{ flex: 1, padding: '8px 12px', fontSize: 13, fontFamily: "'Noto Serif SC', serif", border: '1px solid var(--paper-dark)', borderRadius: 3, background: 'rgba(255,255,255,0.5)', outline: 'none' }} />
                <button onClick={() => loadPickerDirs(browseInput)} style={{ padding: '8px 16px', fontSize: 13, cursor: 'pointer', background: 'var(--ink-black)', color: 'var(--paper-white)', border: 'none', borderRadius: 3, fontFamily: "'ZCOOL XiaoWei', serif" }}>跳转</button>
              </div>
              {pickerCurrent && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--ink-light)', fontFamily: "'Noto Serif SC', serif" }}>当前：{pickerCurrent}</div>}
            </div>
            <div style={{ flex: 1, overflow: 'auto', minHeight: 200, maxHeight: 400 }}>
              {pickerLoading ? (
                <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-light)' }}><LoadingDots /></div>
              ) : pickerDirs.length === 0 && pickerFiles.length === 0 ? (
                <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-light)', fontSize: 13 }}>
                  {pickerCurrent ? '此目录下无子文件夹或代码文件' : '输入路径并回车浏览'}
                </div>
              ) : (
                <div>
                  {pickerParent && (
                    <div onClick={() => loadPickerDirs(pickerParent)} style={{ padding: '10px 20px', cursor: 'pointer', fontSize: 13, fontFamily: "'Noto Serif SC', serif", color: 'var(--ink-medium)', borderBottom: '1px solid rgba(0,0,0,0.04)' }}>&#128193; ..</div>
                  )}
                  {pickerDirs.map(d => (
                    <div key={d.path} onClick={() => handlePickerSelect(d)} style={{
                      padding: '10px 20px', cursor: 'pointer', fontSize: 13, fontFamily: "'Noto Serif SC', serif",
                      color: pickerCurrent === d.path ? 'var(--seal-red)' : 'var(--ink-dark)',
                      background: pickerCurrent === d.path ? 'rgba(194,58,43,0.04)' : 'transparent',
                      borderBottom: '1px solid rgba(0,0,0,0.04)',
                    }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(194,58,43,0.04)'}
                      onMouseLeave={e => { if (pickerCurrent !== d.path) e.currentTarget.style.background = 'transparent' }}
                    >&#128193; {d.name}</div>
                  ))}
                  {pickerFiles.length > 0 && (
                    <>
                      <div style={{ padding: '8px 20px', fontSize: 11, color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif", borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
                        代码文件（点选即选中 · 可再点取消或返回上级目录）
                      </div>
                      {pickerFiles.map(f => {
                        const active = pickerFile?.path === f.path
                        return (
                          <div key={f.path} onClick={() => togglePickerFile(f)} style={{
                            padding: '10px 20px', cursor: 'pointer', fontSize: 13, fontFamily: "'Noto Serif SC', serif",
                            color: active ? 'var(--seal-red)' : 'var(--ink-dark)',
                            background: active ? 'rgba(194,58,43,0.05)' : 'transparent',
                            borderBottom: '1px solid rgba(0,0,0,0.04)',
                          }}
                            onMouseEnter={e => e.currentTarget.style.background = active ? 'rgba(194,58,43,0.05)' : 'rgba(194,58,43,0.04)'}
                            onMouseLeave={e => e.currentTarget.style.background = active ? 'rgba(194,58,43,0.05)' : 'transparent'}
                          >&#128196; {f.name}</div>
                        )
                      })}
                    </>
                  )}
                </div>
              )}
            </div>
            {pickerFile && (
              <div style={{ padding: '8px 20px', borderTop: '1px solid var(--paper-dark)', fontSize: 12, color: 'var(--seal-red)', fontFamily: "'Noto Serif SC', serif", display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>已选文件：{pickerFile.name}</span>
                {pickerParent ? (
                  <span onClick={goPickerUp} style={{ cursor: 'pointer', color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif" }}>← 返回上级目录</span>
                ) : (
                  <span onClick={() => setPickerFile(null)} style={{ cursor: 'pointer', color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif" }}>取消选择</span>
                )}
              </div>
            )}
            <div style={{ padding: '12px 20px', borderTop: pickerFile ? 'none' : '1px solid var(--paper-dark)', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button onClick={() => setPickerOpen(false)} style={{ padding: '8px 20px', fontSize: 13, cursor: 'pointer', background: 'transparent', color: 'var(--ink-medium)', border: '1px solid var(--paper-dark)', borderRadius: 3, fontFamily: "'ZCOOL XiaoWei', serif" }}>取消</button>
              {pickerFile ? (
                <button onClick={() => handlePickerFile(pickerFile)} style={{
                  padding: '8px 20px', fontSize: 13, cursor: 'pointer', letterSpacing: 1,
                  background: 'var(--seal-red)', color: '#fff', border: 'none', borderRadius: 3,
                  fontFamily: "'ZCOOL XiaoWei', serif",
                }}>研读此单篇</button>
              ) : (
                <button onClick={handlePickerConfirm} disabled={!pickerCurrent} style={{ padding: '8px 20px', fontSize: 13, cursor: pickerCurrent ? 'pointer' : 'not-allowed', background: pickerCurrent ? 'var(--ink-black)' : 'var(--ink-faint)', color: 'var(--paper-white)', border: 'none', borderRadius: 3, fontFamily: "'ZCOOL XiaoWei', serif", opacity: pickerCurrent ? 1 : 0.5 }}>选此目录</button>
              )}
            </div>
          </div>
        </Modal>
      )}

      <Card>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>著录 · 代码库</h3>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>父目录路径（浏览时也可直接点选单个代码文件）</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <InkInput value={parentPath} onChange={setParentPath} placeholder="输入路径后回车，或点击浏览选择文件夹 / 代码文件" />
            <button onClick={openPicker} style={{ whiteSpace: 'nowrap', padding: '10px 20px', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14, background: 'var(--ink-black)', color: 'var(--paper-white)', border: 'none', borderRadius: 3, cursor: 'pointer', letterSpacing: 1 }}>浏览</button>
          </div>
        </div>
        {subDirs.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <label style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>待著录的项目（{selected.size}/{subDirs.length}）</label>
              <label style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-medium)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
                <input type="checkbox" checked={selected.size === subDirs.length && subDirs.length > 0} onChange={toggleAll} style={{ accentColor: 'var(--seal-red)' }} /> 全选
              </label>
            </div>
            <div style={{ border: '1px solid var(--paper-dark)', borderRadius: 4, background: 'rgba(255,255,255,0.4)', maxHeight: 240, overflow: 'auto' }}>
              {subDirs.map((d, i) => (
                <label key={d.path} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', cursor: 'pointer', borderBottom: i < subDirs.length - 1 ? '1px solid rgba(0,0,0,0.04)' : undefined, background: selected.has(d.path) ? 'rgba(194,58,43,0.04)' : 'transparent' }}
                  onMouseEnter={e => { if (!selected.has(d.path)) e.currentTarget.style.background = 'rgba(0,0,0,0.02)' }}
                  onMouseLeave={e => { if (!selected.has(d.path)) e.currentTarget.style.background = 'transparent' }}
                >
                  <input type="checkbox" checked={selected.has(d.path)} onChange={() => toggleSelect(d.path)} style={{ accentColor: 'var(--seal-red)' }} />
                  <span style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-dark)' }}>{d.name}</span>
                  <span style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 11, color: 'var(--ink-faint)', marginLeft: 'auto' }}>{d.path}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} style={{ accentColor: 'var(--seal-red)' }} />
          <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--ink-medium)' }}>强制重建</span>
        </div>
        <InkButton onClick={handleBatchIndex} disabled={loading || selected.size === 0}>
          {loading ? '研读中...' : `研读收录 (${selected.size} 个)`}
        </InkButton>
      </Card>

      {results.length > 0 && !dismissed && (
        <Card style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--ink-dark)' }}>
              研读进度
              {loading && <span style={{ fontSize: 14, color: 'var(--water-blue)', marginLeft: 8 }}>(研读中...)</span>}
            </h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <InkButton variant="ghost" onClick={() => {
                results.forEach(r => { if (r.project_id) {
                  api.getProjectStatus(r.project_id).then(s => setAllStatus(prev => ({ ...prev, [r.project_id!]: s }))).catch(() => {})
                }})
              }}>刷新</InkButton>
              {!loading && (
                <button onClick={() => { setDismissed(true); setResults([]); localStorage.removeItem(STORAGE_KEY) }}
                  style={{ fontSize: 12, color: 'var(--ink-light)', cursor: 'pointer', background: 'none', border: 'none', padding: '8px 12px' }}>
                  关闭
                </button>
              )}
            </div>
          </div>
          {results.map((r, i) => {
            const s = allStatus[r.project_id || '']
            const st = s?.index_status || (r.error ? 'failed' : 'processing')
            const pct = s?.total_chunks > 0 && s?.indexed_chunks != null ? Math.round((s.indexed_chunks / s.total_chunks) * 100) : null
            const eta = calcETA(r)
            return (
              <div key={i}>
                <div style={{ padding: '12px 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 16, color: 'var(--ink-dark)' }}>{r.name}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {pct !== null && st === 'processing' && (
                        <span style={{ fontFamily: "'Noto Serif SC', monospace", fontSize: 12, color: 'var(--water-blue)' }}>
                          {s.indexed_chunks}/{s.total_chunks} ({pct}%)
                        </span>
                      )}
                      {eta && (
                        <span style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 11, color: 'var(--ink-light)' }}>约余 {eta}</span>
                      )}
                      <StatusChip status={st} labels={statusMap} colors={statusColor} />
                    </div>
                  </div>
                  {pct !== null && st === 'processing' && (
                    <ProgressBar pct={pct} />
                  )}
                  {r.error && <div style={{ fontSize: 11, color: 'var(--seal-red)', marginTop: 4 }}>{r.error}</div>}
                </div>
                {i < results.length - 1 && <InkDivider />}
              </div>
            )
          })}
        </Card>
      )}

      {knownProjects.length > 0 && (
        <Card style={{ marginTop: 24 }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--ink-dark)', marginBottom: 16 }}>知识宝库</h3>
          {knownProjects.map((p: any) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
              {editingId === p.id ? (
                <>
                  <input value={editName} onChange={e => setEditName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') handleRename(p.id) }} autoFocus
                    style={{ flex: 1, padding: '6px 10px', fontSize: 14, fontFamily: "'Noto Serif SC', serif", border: '1px solid var(--paper-dark)', borderRadius: 3, outline: 'none' }} />
                  <button onClick={() => handleRename(p.id)} style={{ fontSize: 12, color: 'var(--jade-green)', cursor: 'pointer', background: 'none', border: 'none' }}>保存</button>
                  <button onClick={() => setEditingId(null)} style={{ fontSize: 12, color: 'var(--ink-light)', cursor: 'pointer', background: 'none', border: 'none' }}>取消</button>
                </>
              ) : (
                <>
                  <span style={{ flex: 1, fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-dark)' }}>{p.name}</span>
                  <span style={{ fontSize: 12, color: 'var(--ink-faint)' }}>{p.chunk_count} 块</span>
                  <button onClick={() => { setEditingId(p.id); setEditName(p.name) }} style={{ fontSize: 12, color: 'var(--water-blue)', cursor: 'pointer', background: 'none', border: 'none' }}>重命名</button>
                  <button onClick={() => setConfirmDelete(p.id)} style={{ fontSize: 12, color: 'var(--seal-red)', cursor: 'pointer', background: 'none', border: 'none' }}>删除</button>
                </>
              )}
            </div>
          ))}
        </Card>
      )}

      {/* —— 我的资料：全局资料库 —— */}
      {matConfirmDelete && (
        <Modal onClose={() => setMatConfirmDelete(null)}>
          <div style={{ padding: '24px 20px' }}>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--seal-red)', marginBottom: 12 }}>确认删除</h3>
            <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-medium)', marginBottom: 20 }}>
              删除后该资料及其向量数据将被永久移除，确定要删除吗？
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <InkButton variant="ghost" onClick={() => setMatConfirmDelete(null)}>取消</InkButton>
              <button onClick={() => handleMatDelete(matConfirmDelete)} style={{
                padding: '10px 24px', background: 'var(--seal-red)', color: 'var(--paper-white)',
                border: 'none', borderRadius: 3, cursor: 'pointer', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14,
              }}>确认删除</button>
            </div>
          </div>
        </Modal>
      )}

      <Card style={{ marginTop: 24 }}>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 8, color: 'var(--ink-dark)' }}>资料藏卷</h3>
        <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginBottom: 20 }}>
          著录本地典章（PDF / DOCX / TXT / Markdown），整卷或单篇皆可；藏入知识宝库，供日后论道综合检索与出题
        </p>

        <h4 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 17, color: 'var(--ink-dark)', margin: '0 0 14px' }}>著录资料</h4>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
            卷名（可选，默认取文件夹名或文件名）
          </label>
          <InkInput value={dirName} onChange={setDirName} placeholder="例如：系统设计笔记 / 项目文档" />
        </div>

        <div style={{ marginBottom: 6 }}>
          <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
            本地路径（文件夹或文件）
          </label>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <InkInput value={dirPath} onChange={setDirPath} placeholder="输入本地文件夹/文件路径，或点击右侧“浏览”选择" />
          <button onClick={() => setDirPickerOpen(true)} style={{
            whiteSpace: 'nowrap', padding: '10px 20px', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14,
            background: 'var(--ink-black)', color: 'var(--paper-white)', border: 'none', borderRadius: 3,
            cursor: 'pointer', letterSpacing: 1,
          }}>浏览</button>
        </div>
        <div style={{ marginTop: 16 }}>
          <InkButton onClick={handleDirImport} disabled={dirImporting || !dirPath.trim()}>
            {dirImporting ? '导入中...' : '导入'}
          </InkButton>
        </div>
        <FolderPicker open={dirPickerOpen} onClose={() => setDirPickerOpen(false)} onPick={handleDirPick} />

        <div style={{ marginTop: 24 }}>
          <InkDivider />
          <h4 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 18, color: 'var(--ink-dark)', margin: '14px 0 4px' }}>资料库</h4>
          {knownMaterials.length === 0 ? (
            <p style={{ padding: '18px 0', textAlign: 'center', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--ink-light)' }}>
              尚无藏卷：著录一个文件夹或单篇文档即可开卷
            </p>
          ) : (
            knownMaterials.map((m: any, i: number) => {
              const st = m.index_status || 'completed'
              const pct = m.total_chunks > 0 && m.indexed_chunks != null
                ? Math.round((m.indexed_chunks / m.total_chunks) * 100)
                : null
              const eta = matEta(m)
              return (
                <div key={m.id} style={{ padding: '12px 0', borderBottom: i < knownMaterials.length - 1 ? '1px solid rgba(0,0,0,0.04)' : undefined }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    {matEditingId === m.id ? (
                      <>
                        <input value={matEditName} onChange={(e) => setMatEditName(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleMatRename(m.id) }} autoFocus
                          style={{ flex: 1, padding: '6px 10px', fontSize: 14, fontFamily: "'Noto Serif SC', serif", border: '1px solid var(--paper-dark)', borderRadius: 3, outline: 'none' }} />
                        <button onClick={() => handleMatRename(m.id)} style={{ fontSize: 12, color: 'var(--jade-green)', cursor: 'pointer', background: 'none', border: 'none' }}>保存</button>
                        <button onClick={() => setMatEditingId(null)} style={{ fontSize: 12, color: 'var(--ink-light)', cursor: 'pointer', background: 'none', border: 'none' }}>取消</button>
                      </>
                    ) : (
                      <>
                        <span style={{ flex: 1, fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-dark)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {m.kind === 'file' ? '📄' : '📁'} {m.name}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--ink-faint)' }}>{m.chunk_count || 0} 块</span>
                        <StatusChip status={st} labels={statusMap} colors={statusColor} />
                        <button onClick={() => { setMatEditingId(m.id); setMatEditName(m.name) }} style={{ fontSize: 12, color: 'var(--water-blue)', cursor: 'pointer', background: 'none', border: 'none' }}>重命名</button>
                        <button onClick={() => setMatConfirmDelete(m.id)} style={{ fontSize: 12, color: 'var(--seal-red)', cursor: 'pointer', background: 'none', border: 'none' }}>删除</button>
                      </>
                    )}
                  </div>
                  {st === 'processing' && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, color: 'var(--ink-light)' }}>研读进度</span>
                        <span style={{ fontFamily: "'Noto Serif SC', monospace", fontSize: 11, color: 'var(--water-blue)' }}>
                          {m.indexed_chunks || 0}/{m.total_chunks || 0}{pct != null ? ` (${pct}%)` : ''}{eta ? ` · ${eta}` : ''}
                        </span>
                      </div>
                      <ProgressBar pct={pct ?? 0} />
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </Card>
    </div>
  )
}

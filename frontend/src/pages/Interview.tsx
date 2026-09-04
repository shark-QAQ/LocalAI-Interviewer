import { useState, useRef, useEffect } from 'react'
import { api } from '../api'
import { useSearchParams } from 'react-router-dom'
import { PageTitle, SubTitle, Card, InkButton, InkSelect, Toast, LoadingDots, InkDivider } from '../components'

interface SourceRef {
  source: string
  file_path: string
  function_name: string
}

interface ChatMsg {
  role: 'user' | 'assistant' | 'evaluation'
  content: string
  score?: number
  comment?: string
  evalType?: 'intro' | 'answer'
  dimensions?: {
    depth?: number
    logic?: number
    integrity?: number
    clarity?: number
    substance?: number
    fit?: number
  }
  round?: number
  cat?: string // 本题类别（项目深挖/技术栈原理/场景与设计/通用基础）
  sources?: SourceRef[] // 本题引用来源
}

// 自我介绍点评使用非技术维度（表达/内容/匹配），与技术题评分（深度/逻辑/完整）区分
const INTRO_DIM_LABELS: { key: keyof NonNullable<ChatMsg['dimensions']>; label: string }[] = [
  { key: 'clarity', label: '表达' },
  { key: 'substance', label: '内容' },
  { key: 'fit', label: '匹配' },
]

// 题目类别标签（与后端 services/scope.py 一致）
const CAT_LABELS: Record<string, string> = {
  project: '项目深挖',
  stack: '技术栈原理',
  design: '场景与设计',
  basics: '通用基础',
}

function HellConfirm({ open, onConfirm, onCancel }: { open: boolean; onConfirm: () => void; onCancel: () => void }) {
  if (!open) return null
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 2000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
    }}>
      <div style={{
        width: 440, background: '#1a1a1a', border: '2px solid #c23a2b',
        borderRadius: 4, overflow: 'hidden',
        boxShadow: '0 0 60px rgba(194,58,43,0.3), 0 0 120px rgba(194,58,43,0.1)',
        animation: 'hellPulse 2s ease-in-out infinite',
      }}>
        <div style={{
          padding: '20px 24px', background: 'linear-gradient(135deg, #c23a2b 0%, #8b1a1a 100%)',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 36, marginBottom: 4 }}>&#9760;</div>
          <div style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 26, color: '#fff', letterSpacing: 4 }}>
            地狱难度
          </div>
        </div>
        <div style={{ padding: '20px 24px' }}>
          <p style={{
            fontFamily: "'Noto Serif SC', serif", fontSize: 14, lineHeight: 2,
            color: '#e0d0c0', textAlign: 'center', marginBottom: 16,
          }}>
            此难度专为<strong style={{ color: '#c23a2b' }}>资深硬核玩家</strong>打造
          </p>
          <p style={{
            fontFamily: "'Noto Serif SC', serif", fontSize: 13, lineHeight: 1.8,
            color: '#999', textAlign: 'center', marginBottom: 20,
          }}>
            问题将深入源码级细节、边界极端场景、架构设计权衡。<br/>
            连续追问不放过任何漏洞。<br/>
            <span style={{ color: '#c23a2b' }}>不适合心理承受能力弱的选手。</span>
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <button onClick={onCancel} style={{
              padding: '10px 28px', fontSize: 14, cursor: 'pointer',
              background: 'transparent', color: '#999',
              border: '1px solid #444', borderRadius: 3,
              fontFamily: "'ZCOOL XiaoWei', serif", letterSpacing: 2,
            }}>
              算了
            </button>
            <button onClick={onConfirm} style={{
              padding: '10px 28px', fontSize: 14, cursor: 'pointer',
              background: 'linear-gradient(135deg, #c23a2b, #8b1a1a)', color: '#fff',
              border: 'none', borderRadius: 3,
              fontFamily: "'ZCOOL XiaoWei', serif", letterSpacing: 2,
              boxShadow: '0 0 16px rgba(194,58,43,0.4)',
            }}>
              我不怕
            </button>
          </div>
        </div>
      </div>
      <style>{`
        @keyframes hellPulse {
          0%, 100% { box-shadow: 0 0 60px rgba(194,58,43,0.3), 0 0 120px rgba(194,58,43,0.1); }
          50% { box-shadow: 0 0 80px rgba(194,58,43,0.5), 0 0 160px rgba(194,58,43,0.2); }
        }
      `}</style>
    </div>
  )
}

export default function InterviewPage() {
  const [projects, setProjects] = useState<any[]>([])
  const [resumes, setResumes] = useState<any[]>([])
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set())
  const [resumeId, setResumeId] = useState('')
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false)
  const projectDropdownRef = useRef<HTMLDivElement>(null)
  const [difficulty, setDifficulty] = useState('mid')
  const [maxRounds, setMaxRounds] = useState(8)
  const [focus, setFocus] = useState('balanced')
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [ended, setEnded] = useState(false)
  const [toast, setToast] = useState('')
  const [hellConfirmOpen, setHellConfirmOpen] = useState(false)
  const [kbQuery, setKbQuery] = useState('')
  const [kbResults, setKbResults] = useState<any[]>([])
  const [kbLoading, setKbLoading] = useState(false)
  const [kbError, setKbError] = useState('')
  const [kbSummary, setKbSummary] = useState('') // 检索结果的“自然语言归一化”结论
  const [refEntries, setRefEntries] = useState<{ round: number; question: string; reference: string; loading: boolean; sources: SourceRef[] }[]>([]) // 每题参考答案（历史，点击才生成）
  const [openRefs, setOpenRefs] = useState<number[]>([]) // 用户点击展开查看答案的题号
  const [hellConfirmed, setHellConfirmed] = useState(false)
  const chatEnd = useRef<HTMLDivElement>(null)
  const questionSeq = useRef(0) // 前端自增的“第几问”，用于 UI 轮次标签
  const [searchParams] = useSearchParams()

  // —— 续面：按 /interview?session=xxx 载入既有会话并继续 ——
  const buildMsgs = (msgs: any[]): ChatMsg[] => {
    const out: ChatMsg[] = []
    for (const m of msgs) {
      const ev = m.eval || {}
      if (m.role === 'user') {
        out.push({ role: 'user', content: m.content })
      } else if (m.role === 'assistant') {
        if ((m.round_num || 0) === 0) out.push({ role: 'assistant', content: m.content })
        else out.push({
          role: 'assistant', content: m.content,
          round: m.round_num, cat: m.cat || undefined,
          sources: m.sources || undefined,
        })
      } else if (m.role === 'system_eval') {
        if (m.type === 'self_intro') {
          out.push({
            role: 'evaluation', evalType: 'intro', content: m.content,
            score: ev.avg, comment: m.content,
            dimensions: { clarity: ev.clarity, substance: ev.substance, fit: ev.fit },
          })
        } else {
          out.push({
            role: 'evaluation', evalType: 'answer', content: m.content,
            score: ev.avg, comment: m.content,
            dimensions: { depth: ev.depth, logic: ev.logic, integrity: ev.integrity },
          })
        }
      }
    }
    return out
  }

  const resumeExisting = async (sid: string) => {
    setLoading(true); setToast('')
    try {
      const sess = await api.getSession(sid)
      const msgs = await api.getInterviewMessages(sid)
      setDifficulty(sess.difficulty || 'mid')
      setFocus(sess.focus || 'balanced')
      setMaxRounds(Number(sess.max_rounds) || 8)
      setSessionId(sid)
      setMessages(buildMsgs(msgs))
      // 重建“参考答案”条目（库里已缓存的直接可用；未缓存的点开时生成并再次落库）
      const entries = msgs
        .filter((m: any) => m.role === 'assistant' && (m.round_num || 0) > 0)
        .map((m: any) => ({
          round: m.round_num,
          question: m.content || '',
          reference: m.reference || '',
          loading: false,
          sources: m.sources || [],
        }))
      setRefEntries(entries)
      setOpenRefs([])
      const last = msgs.reduce((mx: number, m: any) =>
        (m.role === 'assistant' && (m.round_num || 0) > 0 ? Math.max(mx, m.round_num) : mx), 0)
      questionSeq.current = last
      setEnded(Boolean(sess.status === 'terminated' || sess.status === 'reported'))
    } catch (e: any) { setToast(e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => {
    const sid = searchParams.get('session')
    if (sid) resumeExisting(sid)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isHell = difficulty === 'hell'

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => {})
    api.listResumes().then(setResumes).catch(() => {})
  }, [])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node)) {
        setProjectDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleStart = async () => {
    if (!resumeId || selectedProjects.size === 0) { setToast('请选择简历和至少一个项目'); return }
    if (isHell && !hellConfirmed) {
      setHellConfirmOpen(true)
      return
    }
    setLoading(true); setToast('')
    try {
      const projectIds = [...selectedProjects]
      const res = await api.createSession(resumeId, projectIds[0], difficulty, maxRounds, projectIds, focus)
      setSessionId(res.session_id)
      setMessages([])
      setEnded(false)
      questionSeq.current = 0
      setRefEntries([])
      setOpenRefs([])
      // interviewer starts with first question
      setTimeout(() => triggerFirstQuestion(res.session_id), 500)
    } catch (e: any) {
      setToast(e.message)
    } finally { setLoading(false) }
  }

  const triggerFirstQuestion = async (sid: string) => {
    setLoading(true)
    try {
      let streaming = false
      for await (const { event, data } of api.interactSse(sid, null)) {
        if (event === 'token') {
          if (!streaming) {
            streaming = true
            setMessages(prev => [...prev, { role: 'assistant', content: data.content }])
          } else {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last && last.role === 'assistant' && !last.round) {
                return [...prev.slice(0, -1), { ...last, content: last.content + data.content }]
              }
              return prev
            })
          }
        } else if (event === 'greeting') {
          if (!streaming) {
            setMessages(prev => [...prev, { role: 'assistant', content: data.content }])
          }
        } else if (event === 'evaluation') {
          setMessages(prev => [...prev, { role: 'evaluation', content: data.comment, score: data.score, comment: data.comment, dimensions: data.dimensions }])
        } else if (event === 'done') {
          setEnded(true)
        }
      }
    } catch (e: any) {
      setToast(e.message)
    } finally { setLoading(false) }
  }

  const handleHellConfirm = () => {
    setHellConfirmed(true)
    setHellConfirmOpen(false)
  }

  useEffect(() => {
    if (hellConfirmed && isHell && !sessionId && resumeId && selectedProjects.size > 0) {
      handleStart()
    }
  }, [hellConfirmed])

  const handleSend = async () => {
    if (!sessionId) return
    const answer = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: answer || '（请出题）' }])
    setLoading(true)
    try {
      let streaming = false
      let qRound = 0
      for await (const { event, data } of api.interactSse(sessionId, answer || null)) {
        if (event === 'token') {
          if (!streaming) {
            // 轮次由前端计数（第几问），不依赖后端文本/数值，保证“第 N 题”标签正确
            streaming = true
            qRound = ++questionSeq.current
            setMessages(prev => [...prev, { role: 'assistant', content: data.content, round: qRound }])
          } else {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last && last.role === 'assistant' && last.round === qRound) {
                return [...prev.slice(0, -1), { ...last, content: last.content + data.content }]
              }
              return prev
            })
          }
        } else if (event === 'question') {
          // 题目正文已由 token 流式上屏；这里只在“无 token”时兜底建气泡
          if (qRound === 0) qRound = ++questionSeq.current
          if (!streaming) {
            setMessages(prev => [...prev, { role: 'assistant', content: data.content, round: qRound }])
          }
          // 每道题记录一条（答案点击“查看答案”时才生成）；并把引用来源挂到题目气泡上
          const r = qRound || (data.round != null ? Number(data.round) : refEntries.length + 1)
          const srcs: SourceRef[] = (data.sources || [])
          setRefEntries(prev =>
            prev.some(x => x.round === r)
              ? prev
              : [...prev, { round: r, question: data.content || '', reference: '', loading: false, sources: srcs }]
          )
          if (srcs.length > 0 || data.cat) {
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last && last.role === 'assistant' && last.round === r) {
                return [...prev.slice(0, -1), { ...last, sources: srcs, cat: data.cat }]
              }
              return prev
            })
          }
        } else if (event === 'intro_eval') {
          setMessages(prev => [...prev, { role: 'evaluation', evalType: 'intro', content: data.comment, score: data.score, comment: data.comment, dimensions: data.dimensions }])
        } else if (event === 'evaluation') {
          setMessages(prev => [...prev, { role: 'evaluation', evalType: 'answer', content: data.comment, score: data.score, comment: data.comment, dimensions: data.dimensions }])
        } else if (event === 'done') {
          setEnded(true)
        }
      }
    } catch (e: any) {
      setToast(e.message)
    } finally { setLoading(false) }
  }

  const handleKbSearch = async () => {
    if (!sessionId || !kbQuery.trim()) return
    setKbLoading(true); setKbError('')
    try {
      // 综合检索整个知识库（多项目 + 简历 + 资料），并返回自然语言归一化结论
      const res = await api.searchSessionKb(sessionId, kbQuery.trim(), 6)
      setKbResults(res.results || [])
      setKbSummary(res.summary || '')
    } catch (e: any) {
      setKbError(e.message); setKbResults([]); setKbSummary('')
    } finally { setKbLoading(false) }
  }

  // 点“查看答案”：展开该题，并按需向后端拉取高质量标准答案
  const toggleRef = async (e: { round: number; reference: string; loading: boolean }) => {
    const isOpen = openRefs.includes(e.round)
    setOpenRefs(prev => isOpen ? prev.filter(x => x !== e.round) : [...prev, e.round])
    if (!isOpen && !e.reference && !e.loading) {
      setRefEntries(prev => prev.map(x => x.round === e.round ? { ...x, loading: true } : x))
      try {
        const res = await api.getReference(sessionId, e.round)
        setRefEntries(prev => prev.map(x => x.round === e.round ? { ...x, reference: res.reference, loading: false } : x))
      } catch (err: any) {
        setRefEntries(prev => prev.map(x => x.round === e.round ? { ...x, loading: false } : x))
        setToast(err.message || '参考答案生成失败')
      }
    }
  }

  const completedProjects = projects.filter(p => p.index_status === 'completed')
  const resumeOptions = resumes.map(r => ({ value: r.id, label: `${r.candidate_name} · ${r.id}` }))

  const toggleProject = (id: string) => {
    setSelectedProjects(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const toggleAllProjects = () => {
    if (selectedProjects.size === completedProjects.length) setSelectedProjects(new Set())
    else setSelectedProjects(new Set(completedProjects.map(p => p.id)))
  }

  const difficultyOptions = [
    { value: 'junior', label: '初级 · 入门' },
    { value: 'mid', label: '中级 · 熟练' },
    { value: 'senior', label: '高级 · 精通' },
    { value: 'hell', label: '☠ 地狱 · 硬核' },
  ]

  const focusOptions = [
    { value: 'depth', label: '深究', desc: '以项目与代码为重，深探其实现与取舍' },
    { value: 'balanced', label: '兼顾', desc: '项目与原理并问，不偏一隅' },
    { value: 'breadth', label: '广博', desc: '以原理与基础为纲，博采众长' },
  ]
  const focusOrder = ['depth', 'balanced', 'breadth']
  const focusIdx = Math.max(0, focusOrder.indexOf(focus))
  const focusCurrent = focusOptions.find(o => o.value === focus) || focusOptions[1]
  const pickFocus = (v: string) => { if (focusOrder.includes(v)) setFocus(v) }

  // 配置阶段
  if (!sessionId) {
    return (
      <div>
        <HellConfirm open={hellConfirmOpen} onConfirm={handleHellConfirm} onCancel={() => setHellConfirmOpen(false)} />

        <div style={isHell ? { position: 'relative' } : undefined}>
          {isHell && <style>{`
            body { background: #1a1212 !important; }
            main { background: #1a1212 !important; }
          `}</style>}

          <PageTitle>论道</PageTitle>
          <SubTitle>以代码为剑，以思路为锋，切磋技艺</SubTitle>
          {toast && <Toast message={toast} type="error" />}

          <Card style={isHell ? {
            background: 'linear-gradient(135deg, rgba(40,15,15,0.95) 0%, rgba(30,10,10,0.95) 100%)',
            border: '1px solid rgba(194,58,43,0.4)',
            boxShadow: '0 0 40px rgba(194,58,43,0.1)',
          } : undefined}>
            <h3 style={{
              fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20,
              color: isHell ? '#c23a2b' : 'var(--ink-dark)',
            }}>
              {isHell ? '☠ 面试配置 · 地狱模式' : '面试配置'}
            </h3>

            {completedProjects.length === 0 && (
              <div style={{ padding: '12px 16px', background: 'rgba(194,58,43,0.06)', borderRadius: 3, marginBottom: 16, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--seal-red)' }}>
                尚无可面试的项目，请先到「藏经阁」导入并索引代码库
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: isHell ? '#999' : 'var(--ink-light)' }}>
                  拜帖 (简历)
                </label>
                {resumes.length > 0 ? (
                  <InkSelect value={resumeId} onChange={setResumeId}
                    options={[{ value: '', label: '请选择...' }, ...resumeOptions]}
                    style={{ width: '100%', ...(isHell ? { background: '#2a1515', color: '#f0e0d0', borderColor: '#555' } : {}) }} />
                ) : (
                  <InkSelect value="" onChange={() => {}} disabled options={[{ value: '', label: '暂无简历' }]}
                    style={{ width: '100%' }} />
                )}
              </div>
              <div ref={projectDropdownRef} style={{ position: 'relative' }}>
                <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: isHell ? '#bbb' : 'var(--ink-light)' }}>
                  藏经阁 (项目) — {selectedProjects.size}/{completedProjects.length}
                </label>
                <div onClick={() => setProjectDropdownOpen(!projectDropdownOpen)} style={{
                  padding: '10px 14px', cursor: 'pointer',
                  fontFamily: "'Noto Serif SC', serif", fontSize: 14,
                  background: isHell ? '#2a1515' : 'rgba(255,255,255,0.5)',
                  border: `1px solid ${projectDropdownOpen ? (isHell ? '#c23a2b' : 'var(--ink-medium)') : (isHell ? '#555' : 'var(--paper-dark)')}`,
                  borderRadius: 3, color: isHell ? '#e0d0c0' : 'var(--ink-black)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  transition: 'border-color 0.3s',
                }}>
                  <span style={{ opacity: selectedProjects.size > 0 ? 1 : 0.5 }}>
                    {selectedProjects.size > 0 ? `已选 ${selectedProjects.size} 个项目` : '请选择...'}
                  </span>
                  <span style={{ fontSize: 10, transform: projectDropdownOpen ? 'rotate(180deg)' : '', transition: 'transform 0.2s' }}>&#9660;</span>
                </div>
                <div style={{
                  marginTop: 6, fontSize: 11, lineHeight: 1.5,
                  color: isHell ? '#777' : 'var(--ink-faint)',
                  fontFamily: "'ZCOOL XiaoWei', serif",
                }}>
                  面试将按你勾选的代码库 + 简历 + 资料出题；未勾选的代码库不参与
                </div>
                {projectDropdownOpen && (
                  <div className="project-options" style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 100,
                    marginTop: 4, border: `1px solid ${isHell ? '#555' : 'var(--paper-dark)'}`,
                    borderRadius: 4, background: isHell ? '#2a1515' : 'var(--paper-white)',
                    boxShadow: '0 8px 24px rgba(0,0,0,0.12)', maxHeight: 240,
                    overflowY: 'auto', overflowX: 'hidden',
                  }}>
                    <label style={{
                      display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                      cursor: 'pointer', borderBottom: `1px solid ${isHell ? '#444' : 'rgba(0,0,0,0.06)'}`,
                      fontSize: 12, fontFamily: "'ZCOOL XiaoWei', serif",
                      color: isHell ? '#bbb' : 'var(--ink-medium)',
                      background: isHell ? '#333' : 'rgba(0,0,0,0.02)',
                    }}>
                      <input type="checkbox" checked={selectedProjects.size === completedProjects.length && completedProjects.length > 0}
                        onChange={toggleAllProjects} style={{ accentColor: 'var(--seal-red)' }} />
                      全选
                    </label>
                    {completedProjects.map(p => (
                      <label key={p.id} style={{
                        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                        cursor: 'pointer', fontSize: 12.5,
                        fontFamily: "'Noto Serif SC', serif",
                        color: isHell ? '#f0e0d0' : 'var(--ink-dark)',
                        background: selectedProjects.has(p.id) ? (isHell ? 'rgba(194,58,43,0.15)' : 'rgba(194,58,43,0.04)') : 'transparent',
                      }}
                        onMouseEnter={e => e.currentTarget.style.background = isHell ? 'rgba(194,58,43,0.2)' : 'rgba(194,58,43,0.06)'}
                        onMouseLeave={e => e.currentTarget.style.background = selectedProjects.has(p.id) ? (isHell ? 'rgba(194,58,43,0.15)' : 'rgba(194,58,43,0.04)') : 'transparent'}
                      >
                        <input type="checkbox" checked={selectedProjects.has(p.id)}
                          onChange={() => toggleProject(p.id)} style={{ accentColor: 'var(--seal-red)' }} />
                        {p.name}
                        <span style={{ fontSize: 11, color: isHell ? '#666' : 'var(--ink-faint)', marginLeft: 'auto' }}>{p.chunk_count}块</span>
                      </label>
                    ))}
                    {completedProjects.length === 0 && (
                      <div style={{ padding: '12px 14px', fontSize: 13, color: isHell ? '#888' : 'var(--ink-light)', textAlign: 'center' }}>暂无可用项目</div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: isHell ? '#bbb' : 'var(--ink-light)' }}>
                  难度
                </label>
                <InkSelect value={difficulty} onChange={(v) => { setDifficulty(v); if (v !== 'hell') setHellConfirmed(false) }}
                  options={difficultyOptions}
                  style={{ width: '100%', ...(isHell ? { background: '#2a1515', color: '#c23a2b', borderColor: '#c23a2b', fontWeight: 'bold' } : {}) }} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: isHell ? '#bbb' : 'var(--ink-light)' }}>
                  最大轮数
                </label>
                <InkSelect value={String(maxRounds)} onChange={(v) => setMaxRounds(Number(v))}
                  options={[{ value: '5', label: '5 轮' }, { value: '8', label: '8 轮' }, { value: '10', label: '10 轮' }, { value: '15', label: '15 轮' }]}
                  style={{ width: '100%', ...(isHell ? { background: '#2a1515', color: '#f0e0d0', borderColor: '#555' } : {}) }} />
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', marginBottom: 4, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: isHell ? '#bbb' : 'var(--ink-light)' }}>
                发问侧重　<span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 15, color: isHell ? '#c23a2b' : 'var(--seal-red)' }}>{focusCurrent.label}</span>
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={1}
                value={focusIdx}
                onChange={e => pickFocus(focusOrder[Number(e.target.value)])}
                style={{
                  width: '100%', margin: '6px 0 0', cursor: 'pointer',
                  accentColor: isHell ? '#c23a2b' : 'var(--seal-red)',
                  height: 22,
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 0 }}>
                {focusOptions.map(o => {
                  const active = o.value === focus
                  return (
                    <button key={o.value} onClick={() => pickFocus(o.value)} style={{
                      border: 'none', background: 'none', cursor: 'pointer', padding: '2px 0',
                      fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13,
                      color: active ? (isHell ? '#c23a2b' : 'var(--seal-red)') : (isHell ? '#888' : 'var(--ink-medium)'),
                      fontWeight: active ? 'bold' : 'normal',
                    }}>{o.label}</button>
                  )
                })}
              </div>
              <div style={{ marginTop: 2, fontSize: 11, lineHeight: 1.5, color: isHell ? '#777' : 'var(--ink-faint)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
                当　前：{focusCurrent.desc}。一线自“深究”至“广博”：向左偏重项目细究，向右偏重原理博闻
              </div>
            </div>

            {isHell && (
              <div style={{
                padding: '12px 16px', marginBottom: 20, borderRadius: 3,
                background: 'rgba(194,58,43,0.1)', border: '1px solid rgba(194,58,43,0.3)',
                fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: '#c23a2b',
                textAlign: 'center', letterSpacing: 1,
              }}>
                &#9760; 地狱模式已激活 —— 深呼吸，准备迎接挑战
              </div>
            )}

            <InkButton onClick={handleStart} disabled={loading || !resumeId || selectedProjects.size === 0}
              style={isHell ? {
                background: 'linear-gradient(135deg, #c23a2b, #8b1a1a)',
                boxShadow: '0 0 20px rgba(194,58,43,0.4)',
                width: '100%',
              } : undefined}>
              {loading ? '创建中...' : isHell ? '☠ 开启地狱之门' : '开坛论道'}
            </InkButton>
          </Card>
        </div>
      </div>
    )
  }

  // 对话阶段
  const hellStyle = isHell ? {
    background: '#0a0a0a',
  } as React.CSSProperties : undefined

  return (
    <div style={hellStyle}>
      <style>{`
        .ink-scroll::-webkit-scrollbar { width: 10px; height: 10px; }
        .ink-scroll::-webkit-scrollbar-track { background: transparent; }
        .ink-scroll::-webkit-scrollbar-thumb { background: rgba(110,95,80,.30); border-radius: 6px; border: 2px solid rgba(0,0,0,0); background-clip: padding-box; }
        .ink-scroll::-webkit-scrollbar-thumb:hover { background: rgba(110,95,80,.5); background-clip: padding-box; }
        .ink-area { transition: border-color .15s, box-shadow .15s; }
        .ink-area:focus { border-color: var(--seal-red) !important; box-shadow: 0 0 0 1px var(--seal-red); }
        .ink-btn-seal { background: linear-gradient(135deg, #d23b2c 0%, #9e2018 100%); color: #fff; border: none; border-radius: 999px; box-shadow: 0 4px 14px rgba(194,58,43,.35); font-family: 'ZCOOL XiaoWei', serif; letter-spacing: 2px; cursor: pointer; transition: transform .12s ease, box-shadow .15s ease, opacity .15s ease; }
        .ink-btn-seal:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(194,58,43,.45); }
        .ink-btn-seal:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
      `}</style>
      {isHell && <style>{`
        body { background: #1a1212 !important; }
        main { background: #1a1212 !important; }
        main > div { background: #1a1212 !important; }
        .ink-scroll::-webkit-scrollbar-thumb { background: rgba(210,185,160,.30); border: 2px solid rgba(0,0,0,0); background-clip: padding-box; }
        .ink-scroll::-webkit-scrollbar-thumb:hover { background: rgba(210,185,160,.5); background-clip: padding-box; }
      `}</style>}

      <PageTitle>论道</PageTitle>
      <SubTitle style={isHell ? { color: '#888' } : undefined}>
        {isHell ? '☠ 地狱模式 · Session: ' + sessionId : 'Session: ' + sessionId}
      </SubTitle>
      {toast && <Toast message={toast} type={toast.includes('失败') ? 'error' : 'info'} />}

      <div style={{ display: 'flex', gap: 16, alignItems: 'stretch', height: 'calc(100vh - 230px)', minHeight: 460 }}>
      <Card style={{
        height: '100%', display: 'flex', flexDirection: 'column', flex: 1, borderRadius: 8,
        ...(isHell ? {
          background: 'linear-gradient(135deg, rgba(40,15,15,0.95) 0%, rgba(30,10,10,0.95) 100%)',
          border: '1px solid rgba(194,58,43,0.3)',
          boxShadow: '0 0 40px rgba(194,58,43,0.08)',
        } : {}),
        border: `1px solid ${isHell ? 'rgba(194,58,43,0.4)' : '#d5c8b4'}`,
        borderTop: `3px solid ${isHell ? '#c23a2b' : 'var(--seal-red)'}`,
        boxShadow: isHell ? '0 0 40px rgba(194,58,43,0.08)' : '0 6px 18px rgba(0,0,0,.06)',
      }}>
        <div className="ink-scroll" style={{ flex: 1, overflow: 'auto', marginBottom: 16 }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px 0', color: isHell ? '#888' : 'var(--ink-light)' }}>
              <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.3 }}>&#127917;</div>
              <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14 }}>
                {isHell ? '地狱之门已开，开口即可入局' : '论道将启，面试官稍候开场'}
              </p>
            </div>
          )}

          {messages.map((msg, i) => {
            if (msg.role === 'user') {
              return (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', marginBottom: 16 }}>
                  <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, color: isHell ? '#9a6b60' : 'var(--ink-faint)', marginBottom: 4, paddingRight: 4 }}>你</span>
                  <div style={{
                    maxWidth: '70%', padding: '12px 18px', borderRadius: 8, borderBottomRightRadius: 2,
                    background: isHell ? '#3a2020' : 'var(--ink-black)',
                    color: isHell ? '#f0e0d0' : 'var(--paper-white)',
                    fontFamily: "'Noto Serif SC', serif", fontSize: 14, lineHeight: 1.8,
                    border: isHell ? '1px solid rgba(194,58,43,0.35)' : '1px solid rgba(0,0,0,0.18)',
                    boxShadow: isHell ? '0 3px 12px rgba(0,0,0,.35)' : '0 3px 10px rgba(0,0,0,.10)',
                  }}>
                    {msg.content}
                  </div>
                </div>
              )
            }
            if (msg.role === 'evaluation') {
              const isIntro = msg.evalType === 'intro'
              const dimItems = isIntro
                ? INTRO_DIM_LABELS.map(d => ({ label: d.label, value: msg.dimensions?.[d.key] }))
                : [
                    { label: '深度', value: msg.dimensions?.depth },
                    { label: '逻辑', value: msg.dimensions?.logic },
                    { label: '完整', value: msg.dimensions?.integrity },
                  ]
              return (
                <div key={i} style={{
                  marginBottom: 16, padding: '12px 18px', borderRadius: 8,
                  background: isHell ? 'rgba(194,58,43,0.12)' : 'rgba(90,122,106,0.06)',
                  border: `1px solid ${isHell ? 'rgba(194,58,43,0.3)' : 'rgba(90,122,106,0.15)'}`,
                  borderLeft: `3px solid ${isHell ? '#c23a2b' : 'var(--jade-green)'}`,
                }}>
                  <div style={{
                    fontFamily: "'Ma Shan Zheng', cursive", fontSize: 16,
                    color: isHell ? '#c23a2b' : 'var(--jade-green)', marginBottom: 6,
                  }}>
                    {isIntro ? '💬 自我介绍点评' : '📊 本轮品鉴'} · {msg.score?.toFixed(1)} 分
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: isHell ? '#aaa' : 'var(--ink-medium)' }}>
                    {dimItems.map((d, j) => (
                      <span key={j}>{d.label} {d.value ?? '—'}</span>
                    ))}
                  </div>
                  <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 13, color: isHell ? '#bbb' : 'var(--ink-medium)', lineHeight: 1.6 }}>
                    {msg.comment}
                  </p>
                </div>
              )
            }
            return (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', marginBottom: 16 }}>
                <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, color: isHell ? '#c8a89a' : 'var(--ink-light)', marginBottom: 4, paddingLeft: 4 }}>面试官</span>
                <div style={{
                  maxWidth: '75%', padding: '12px 18px', borderRadius: 8, borderTopLeftRadius: 2,
                  background: isHell ? 'rgba(50,20,20,0.92)' : 'rgba(245,240,232,0.92)',
                  border: `1px solid ${isHell ? 'rgba(194,58,43,0.3)' : 'var(--paper-dark)'}`,
                  borderLeft: `3px solid ${isHell ? '#c23a2b' : 'var(--seal-red)'}`,
                  boxShadow: isHell ? '0 3px 12px rgba(0,0,0,.35)' : '0 3px 10px rgba(0,0,0,.06)',
                  fontFamily: "'Noto Serif SC', serif", fontSize: 14, lineHeight: 1.8,
                  color: isHell ? '#e0d0c0' : 'var(--ink-black)',
                }}>
                  {msg.round && (
                    <span style={{
                      fontFamily: "'Ma Shan Zheng', cursive", fontSize: 13,
                      color: isHell ? '#c23a2b' : 'var(--seal-red)', marginRight: 8,
                    }}>
                      第{msg.round}题
                    </span>
                  )}
                  {msg.cat && (
                    <span style={{
                      fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11,
                      color: isHell ? '#c0a0a0' : 'var(--water-blue)', marginRight: 8,
                    }}>
                      · {CAT_LABELS[msg.cat] || msg.cat}
                    </span>
                  )}
                  {msg.content}
                  {msg.sources && msg.sources.length > 0 && (
                    <div style={{
                      marginTop: 8, paddingTop: 6, borderTop: `1px solid ${isHell ? 'rgba(194,58,43,0.2)' : 'rgba(0,0,0,0.06)'}`,
                      fontSize: 11, lineHeight: 1.7, color: isHell ? '#999' : 'var(--ink-faint)',
                      fontFamily: "'ZCOOL XiaoWei', serif",
                    }}>
                      📚 引用自
                      {msg.sources.map((s, j) => {
                        const loc = s.file_path || s.function_name
                        return (
                          <span key={j} style={{ display: 'block' }}>
                            {s.source || ''}{loc ? ` · ${loc}` : ''}
                          </span>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
              <div style={{
                padding: '12px 18px', borderRadius: '4px 4px 4px 0',
                background: isHell ? 'rgba(50,20,20,0.9)' : 'rgba(245,240,232,0.8)',
                border: `1px solid ${isHell ? 'rgba(194,58,43,0.3)' : 'var(--paper-dark)'}`,
              }}>
                <LoadingDots />
              </div>
            </div>
          )}
          <div ref={chatEnd} />
        </div>

        <InkDivider />

        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <textarea
              className="ink-area"
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder={ended ? '面试已结束' : isHell ? '接受审判...' : '在此写下回答，回车提交；Shift+Enter 换行'}
              disabled={loading || ended}
              rows={3}
              style={{
                width: '100%', padding: '12px 14px', resize: 'none',
                fontFamily: "'Noto Serif SC', serif", fontSize: 14,
                background: isHell ? '#2a1515' : 'rgba(255,255,255,0.6)',
                border: `1px solid ${isHell ? 'rgba(194,58,43,0.3)' : 'var(--paper-dark)'}`,
                borderRadius: 4, color: isHell ? '#f0e0d0' : 'var(--ink-black)', outline: 'none',
              }}
            />
          </div>
          <InkButton className="ink-btn-seal" onClick={handleSend} disabled={loading || ended} style={{
            height: 44, minWidth: 92, fontSize: 16, padding: '0 22px',
          }}>
            {loading ? '…' : isHell ? '叩' : '递帖'}
          </InkButton>
        </div>

        {ended && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <InkButton variant="secondary" onClick={() => window.location.href = `/report?session=${sessionId}`}
              style={isHell ? { color: '#c23a2b', borderColor: '#c23a2b' } : undefined}>
              查看品鉴报告
            </InkButton>
          </div>
        )}
      </Card>

      {/* 知识库查询面板 */}
      <Card style={{
        width: 380, height: '100%', display: 'flex', flexDirection: 'column', flexShrink: 0, borderRadius: 8,
        ...(isHell ? {
          background: 'linear-gradient(135deg, rgba(40,15,15,0.95) 0%, rgba(30,10,10,0.95) 100%)',
          border: '1px solid rgba(194,58,43,0.3)',
        } : {}),
        border: `1px solid ${isHell ? 'rgba(194,58,43,0.4)' : '#d5c8b4'}`,
        borderTop: `3px solid ${isHell ? '#c23a2b' : 'var(--jade-green)'}`,
        boxShadow: isHell ? undefined : '0 6px 18px rgba(0,0,0,.06)',
      }}>
        <h3 style={{
          fontFamily: "'Ma Shan Zheng', cursive", fontSize: 18, marginBottom: 12,
          color: isHell ? '#c23a2b' : 'var(--ink-dark)',
        }}>&#128214; 知识库查询</h3>
        <p style={{
          fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12,
          color: isHell ? '#888' : 'var(--ink-light)', marginBottom: 12,
        }}>检索本场范围：所选代码库 / 简历 / 资料</p>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input
            className="ink-area"
            value={kbQuery} onChange={e => setKbQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleKbSearch() }}
            placeholder="例如：线程池 / 缓存策略 / JWT"
            style={{
              flex: 1, padding: '9px 12px', fontSize: 13,
              fontFamily: "'Noto Serif SC', serif", outline: 'none',
              background: isHell ? '#2a1515' : 'rgba(255,255,255,0.6)',
              border: `1px solid ${isHell ? 'rgba(194,58,43,0.3)' : 'var(--paper-dark)'}`,
              borderRadius: 4, color: isHell ? '#f0e0d0' : 'var(--ink-black)',
            }}
          />
          <button className="ink-btn-seal" onClick={handleKbSearch} disabled={kbLoading || !kbQuery.trim()} style={{
            height: 36, minWidth: 64, padding: '0 16px', fontSize: 13,
          }}>
            {kbLoading ? '检索中' : '查询'}
          </button>
        </div>

        {kbError && (
          <div style={{
            padding: '8px 12px', marginBottom: 12, borderRadius: 3, fontSize: 12,
            background: 'rgba(194,58,43,0.1)', color: 'var(--seal-red)',
            fontFamily: "'Noto Serif SC', serif",
          }}>{kbError}</div>
        )}

        {kbSummary && (
          <div style={{
            marginBottom: 12, padding: 10, borderRadius: 6,
            background: isHell ? 'rgba(30,12,12,0.7)' : 'rgba(245,240,232,0.7)',
            border: `1px solid ${isHell ? 'rgba(194,58,43,0.2)' : 'rgba(90,122,106,0.2)'}`,
            borderLeft: `3px solid ${isHell ? '#c23a2b' : 'var(--jade-green)'}`,
          }}>
            <div style={{
              fontFamily: "'Ma Shan Zheng', cursive", fontSize: 13,
              color: isHell ? '#c23a2b' : 'var(--jade-green)', marginBottom: 4,
            }}>
              📖 检索说明（自然语言）
            </div>
            <div style={{
              fontFamily: "'Noto Serif SC', serif", fontSize: 12, lineHeight: 1.8,
              color: isHell ? '#e0d0c0' : 'var(--ink-medium)',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>{kbSummary}</div>
          </div>
        )}

        {kbResults.length > 0 && (
          <div style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, color: 'var(--ink-light)', marginBottom: 6 }}>
            原始命中 {kbResults.length} 处（代码片段）
          </div>
        )}

        <div className="ink-scroll" style={{ flex: 1, overflow: 'auto' }}>
          {kbLoading ? (
            <div style={{ textAlign: 'center', padding: '40px 0' }}><LoadingDots /></div>
          ) : kbResults.length === 0 ? (
            <div style={{
              textAlign: 'center', padding: '40px 0',
              color: isHell ? '#666' : 'var(--ink-light)',
              fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13,
            }}>
              {kbQuery ? '未找到相关内容，换个关键词再试' : '输入关键词，检索项目 / 简历 / 资料'}
            </div>
          ) : (
            kbResults.map((r, i) => (
              <div key={i} style={{
                marginBottom: 12, padding: 10, borderRadius: 4,
                background: isHell ? 'rgba(30,12,12,0.8)' : 'rgba(245,240,232,0.6)',
                border: `1px solid ${isHell ? 'rgba(194,58,43,0.2)' : 'var(--paper-dark)'}`,
              }}>
                <div style={{
                  fontFamily: "'Ma Shan Zheng', cursive", fontSize: 13, marginBottom: 4,
                  color: isHell ? '#c23a2b' : 'var(--seal-red)',
                  wordBreak: 'break-all',
                }}>
                  {r.source ? `📚 ${r.source}` : '代码片段'}
                  {r.function_name ? ` · ƒ ${r.function_name}` : ''}
                </div>
                <div style={{
                  fontFamily: "'Noto Serif SC', serif", fontSize: 11, marginBottom: 6,
                  color: isHell ? '#888' : 'var(--ink-faint)', wordBreak: 'break-all',
                }}>
                  {r.file_path}{r.start_line ? ` : ${r.start_line}${r.end_line ? '-' + r.end_line : ''}` : ''}
                </div>
                <pre className="ink-scroll" style={{
                  fontFamily: "'Noto Serif SC', monospace", fontSize: 11, lineHeight: 1.6,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0,
                  maxHeight: 150, overflow: 'auto', padding: 8, borderRadius: 4,
                  background: isHell ? 'rgba(0,0,0,0.28)' : 'rgba(0,0,0,0.03)',
                  color: isHell ? '#e0d0c0' : 'var(--ink-medium)',
                }}>{r.text}</pre>
              </div>
            ))
          )}
        </div>

        {refEntries.length > 0 && (
          <>
            <InkDivider />
            <div style={{ marginTop: 8 }}>
              <div style={{
                fontFamily: "'Ma Shan Zheng', cursive", fontSize: 15,
                color: isHell ? '#c23a2b' : 'var(--jade-green)', marginBottom: 8,
              }}>
                📖 参考答案（点击“查看答案”展开）
              </div>
              <div className="ink-scroll" style={{ maxHeight: 320, overflow: 'auto' }}>
                {refEntries.map((e) => {
                  const open = openRefs.includes(e.round)
                  return (
                    <div key={e.round} style={{
                      marginBottom: 8, padding: 8, borderRadius: 4,
                      background: isHell ? 'rgba(30,12,12,0.7)' : 'rgba(245,240,232,0.7)',
                      border: `1px solid ${isHell ? 'rgba(194,58,43,0.2)' : 'rgba(90,122,106,0.2)'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          fontFamily: "'Ma Shan Zheng', cursive", fontSize: 13,
                          color: isHell ? '#e0d0c0' : 'var(--ink-dark)', whiteSpace: 'nowrap',
                        }}>
                          第 {e.round} 题
                        </span>
                        <span style={{
                          flex: 1, fontSize: 11, color: isHell ? '#999' : 'var(--ink-faint)',
                          fontFamily: "'Noto Serif SC', serif", overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {e.question || ''}
                        </span>
                        <button onClick={() => toggleRef(e)} style={{
                          whiteSpace: 'nowrap', fontSize: 12, cursor: 'pointer', padding: '4px 13px',
                          borderRadius: 999, border: 'none',
                          background: open ? (isHell ? 'rgba(194,58,43,0.3)' : 'rgba(90,122,106,0.18)') : 'var(--ink-black)',
                          color: open ? (isHell ? '#e0d0c0' : 'var(--jade-green)') : 'var(--paper-white)',
                          fontFamily: "'ZCOOL XiaoWei', serif", letterSpacing: 1,
                        }}>
                          {e.loading ? '生成中…' : open ? '收起' : '查看答案'}
                        </button>
                      </div>
                      {open && (
                        <div style={{
                          marginTop: 6, fontSize: 12, lineHeight: 1.7,
                          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                          fontFamily: "'Noto Serif SC', serif",
                          color: isHell ? '#e0d0c0' : 'var(--ink-medium)',
                        }}>
                          {e.loading ? '答案生成中，请稍候…' : (e.reference || '（生成失败，点“收起”后再次点击重试）')}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        )}
      </Card>
      </div>
    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import { api } from '../api'
import type { ResumeBuiltinTemplate, ResumeGenTurn } from '../api'
import { PageTitle, SubTitle, Card, InkButton, InkInput, InkSelect, Toast, ProgressBar, Modal } from '../components'
import { LockGate } from '../components/ApiGate'

type Phase = 'gate' | 'setup' | 'chat' | 'done'
interface Msg { role: 'user' | 'assistant'; content: string }

function isLockMsg(msg: string): boolean {
  return msg.includes('仅在使用') || msg.includes('切换') || msg.includes('DeepSeek')
}

export default function ResumeGenPage() {
  const [phase, setPhase] = useState<Phase>('gate')
  const [gateMsg, setGateMsg] = useState('')
  const [templates, setTemplates] = useState<ResumeBuiltinTemplate[]>([])
  const [previewKey, setPreviewKey] = useState<string | null>(null)
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [resumes, setResumes] = useState<any[]>([])
  const [resumeId, setResumeId] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [fileName, setFileName] = useState('简历.docx')
  const [desktopFile, setDesktopFile] = useState('')
  const [templateFields, setTemplateFields] = useState<string[]>([])
  const [messages, setMessages] = useState<Msg[]>([])
  const [filled, setFilled] = useState<Record<string, string>>({})
  const [missing, setMissing] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [photoBusy, setPhotoBusy] = useState(false)
  const [toast, setToast] = useState('')
  const photoRef = useRef<HTMLInputElement>(null)

  const lock = (msg: string) => { if (isLockMsg(msg)) { setGateMsg(msg); setPhase('gate') } else setToast(msg) }

  const handlePhoto = async (f: File | null) => {
    if (!f || !sessionId) return
    setPhotoBusy(true); setToast('')
    try {
      await api.uploadResumePhoto(sessionId, f)
      setToast('✓ 照片已添加，生成时将嵌入照片位')
    } catch (e: any) { lock(e.message) }
    finally { setPhotoBusy(false); if (photoRef.current) photoRef.current.value = '' }
  }

  useEffect(() => {
    api.getLlmSettings().then((s) => {
      if (s.provider !== 'deepseek') setGateMsg('为保证生成质量，本功能仅在使用 DeepSeek API 时开放。')
      else {
        setPhase('setup')
        api.getResumeTemplates().then((r) => setTemplates(r.templates || [])).catch(() => {})
        api.listResumes().then((list) => {
          setResumes(list)
          if (list.length) setResumeId(list[0].id)
        }).catch(() => {})
      }
    }).catch((e) => setGateMsg(e.message))
  }, [])

  const startChat = async () => {
    if (!selectedKey) { setToast('请先选择模板'); return }
    setBusy(true); setToast('')
    try {
      const r: ResumeGenTurn = await api.startResumeByTemplate({
        template_key: selectedKey,
        resume_id: resumeId || undefined,
      })
      setSessionId(r.session_id)
      setTemplateFields(r.missing || [])
      setFilled(r.fields || {})
      setMissing(r.missing || [])
      setMessages([{ role: 'assistant', content: r.question || '我们开始吧，请介绍一下你的情况。' }])
      setPhase('chat')
    } catch (e: any) {
      lock(e.message)
    } finally { setBusy(false) }
  }

  const send = async () => {
    const text = input.trim()
    if (!text || busy || !sessionId) return
    setInput(''); setBusy(true)
    setMessages((m) => [...m, { role: 'user', content: text }])
    try {
      const r = await api.resumeGenChat(sessionId, text)
      setFilled(r.fields || {}); setMissing(r.missing || [])
      if (/生成|完成|好了|可以了|就这样|足够了|直接/.test(text)) {
        await generateNow()
        return
      }
      setMessages((m) => [...m, { role: 'assistant', content: r.question || '好的，已记录。请继续补充或点击生成。' }])
    } catch (e: any) {
      lock(e.message)
      setMessages((m) => [...m, { role: 'assistant', content: '（刚才没处理好，麻烦再说一次？）' }])
    } finally { setBusy(false) }
  }

  const generateNow = async () => {
    setBusy(true); setToast('')
    try {
      const r = await api.generateResume(sessionId)
      setFileName(r.file_name || '简历.docx')
      setDesktopFile(r.desktop?.filename || '')
      setPhase('done')
    } catch (e: any) { lock(e.message) } finally { setBusy(false) }
  }

  const download = () => { window.location.href = `/api/v1/resume-gen/sessions/${sessionId}/download` }

  // ---------- gate ----------
  if (phase === 'gate') {
    return (
      <div>
        <PageTitle>挥毫</PageTitle>
        <SubTitle>AI 对话 · 生成简历</SubTitle>
        <LockGate title="简历生成 · 暂未解锁" hint={gateMsg || '点击锁图标查看如何切换至 DeepSeek API。'} />
      </div>
    )
  }

  // ---------- setup: 选模板 → 预览 → 开始 ----------
  if (phase === 'setup') {
    const selected = templates.find((t) => t.key === selectedKey)
    return (
      <div>
        <PageTitle>挥毫</PageTitle>
        <SubTitle>选择模板 · 生成简历</SubTitle>
        {toast && <Toast message={toast} type={isLockMsg(toast) ? 'error' : 'info'} />}

        <Card style={{ maxWidth: 860 }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 6, color: 'var(--ink-dark)' }}>
            ① 选择模板
          </h3>
          <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', lineHeight: 1.7, marginBottom: 16 }}>
            点击卡片可预览版式；选定后用内置专业模板出稿（含照片位），内容由 AI 依你的回答与简历素材润色生成。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px,1fr))', gap: 14 }}>
            {templates.map((t) => {
              const active = selectedKey === t.key
              return (
                <button key={t.key} onClick={() => setSelectedKey(t.key)}
                  style={{
                    textAlign: 'left', cursor: 'pointer', borderRadius: 4, padding: 14,
                    border: active ? `2px solid #${t.accent}` : '1px solid var(--paper-dark)',
                    background: active ? 'rgba(255,255,255,0.75)' : 'rgba(255,255,255,0.4)',
                    color: 'var(--ink-black)', fontFamily: "'Noto Serif SC', serif",
                    display: 'flex', flexDirection: 'column', gap: 6,
                  }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <div style={{
                      width: 26, height: 34, border: '1px dashed #999', borderRadius: 2, flexShrink: 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 8, color: '#999', background: '#faf8f4',
                    }}>照片</div>
                    <span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: `#${t.accent}` }}>{t.name}</span>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--ink-light)', lineHeight: 1.5 }}>{t.desc}</span>
                  <span style={{ fontSize: 12, color: active ? `#${t.accent}` : 'var(--ink-faint)' }}>
                    {active ? '✓ 已选' : '点击选择'}
                  </span>
                </button>
              )
            })}
          </div>

          {selected && (
            <div style={{ marginTop: 18, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <InkButton variant="secondary" onClick={() => setPreviewKey(selected.key)}>预览「{selected.name}」</InkButton>
            </div>
          )}
        </Card>

        <Card style={{ maxWidth: 860, marginTop: 16 }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 14, color: 'var(--ink-dark)' }}>
            ② 内容与开始
          </h3>
          <div style={{ maxWidth: 440, marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
              参考已上传简历做润色（自动关联第一份）
            </label>
            <InkSelect value={resumeId} onChange={setResumeId}
              options={[
                { value: '', label: '不引用，从零收集' },
                ...resumes.map((r: any) => ({ value: r.id, label: r.candidate_name })),
              ]} />
          </div>
          <InkButton onClick={startChat} disabled={busy || !selectedKey}>
            {busy ? '对话准备中…' : '开始生成简历'}
          </InkButton>
        </Card>

        {previewKey && (
          <Modal onClose={() => setPreviewKey(null)}>
            <div style={{ width: 'min(720px, 92vw)', maxHeight: '86vh', overflow: 'auto' }}>
              <iframe
                title="模板预览"
                src={`/api/v1/resume-gen/templates/${previewKey}/preview`}
                style={{ width: '100%', height: 620, border: '1px solid var(--paper-dark)', borderRadius: 4, background: '#fff' }}
              />
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 12 }}>
                <InkButton onClick={() => { setSelectedKey(previewKey); setPreviewKey(null) }}>选用此模板</InkButton>
                <InkButton variant="ghost" onClick={() => setPreviewKey(null)}>关闭</InkButton>
              </div>
            </div>
          </Modal>
        )}
      </div>
    )
  }

  // ---------- done ----------
  if (phase === 'done') {
    return (
      <div>
        <PageTitle>挥毫</PageTitle>
        <SubTitle>简历已生成</SubTitle>
        <Card style={{ maxWidth: 620, marginTop: 12, textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🖋</div>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 24, color: 'var(--ink-dark)', marginBottom: 6 }}>
            简历已生成{desktopFile ? '并保存到桌面' : ''}
          </h3>
          {desktopFile
            ? <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 15, color: 'var(--jade-green)' }}>✓ {desktopFile}</p>
            : <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14, color: 'var(--ink-light)' }}>{fileName}</p>}
          <div style={{ marginTop: 18, display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <InkButton onClick={() => window.open(`/api/v1/resume-gen/sessions/${sessionId}/preview`, '_blank')}>
              打开美观版预览 · 另存 PDF
            </InkButton>
            <InkButton variant="secondary" onClick={download}>Word 版再取一份</InkButton>
            <InkButton variant="secondary" onClick={() => { setPhase('setup'); setSessionId(''); setSelectedKey('') }}>再来一份</InkButton>
          </div>
          <p style={{ marginTop: 14, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-faint)' }}>
            Word 版已自动保存到桌面；想打印/另存 PDF 请用「美观版预览」后 Ctrl+P 保存为 PDF。
          </p>
        </Card>
      </div>
    )
  }

  // ---------- chat ----------
  const filledCount = templateFields.filter((f) => (filled[f] || '').trim()).length
  return (
    <div>
      <PageTitle>挥毫</PageTitle>
      <SubTitle>与 AI 对话完善简历（{missing.length ? `待补 ${missing.length}` : '内容已齐，可直接说“生成简历”'}）</SubTitle>
      {toast && <Toast message={toast} type="info" />}

      <div style={{ maxWidth: 760, marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-faint)' }}>
          <span>已填 {filledCount} / {templateFields.length}</span>
        </div>
        <ProgressBar pct={templateFields.length ? Math.round((filledCount / templateFields.length) * 100) : 0} color="var(--seal-red)" height={5} />
      </div>

      <Card style={{ maxWidth: 760, padding: '20px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <InkButton variant="secondary" onClick={() => photoRef.current?.click()} disabled={photoBusy}>
            {photoBusy ? '上传中…' : '添加照片（照片位）'}
          </InkButton>
          <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
            onChange={(e) => handlePhoto(e.target.files?.[0] ?? null)} />
          <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
            选填：上传本人照片，生成时嵌入所选模板的照片位
          </span>
        </div>
        <div style={{ maxHeight: 420, overflowY: 'auto', marginBottom: 16 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
              <div style={{
                maxWidth: '80%', padding: '10px 14px', borderRadius: 6, lineHeight: 1.7,
                fontFamily: "'Noto Serif SC', serif", fontSize: 14, whiteSpace: 'pre-wrap',
                background: m.role === 'user' ? 'var(--ink-black)' : 'rgba(245,240,232,0.9)',
                color: m.role === 'user' ? 'var(--paper-white)' : 'var(--ink-black)',
                border: m.role === 'user' ? 'none' : '1px solid var(--paper-dark)',
              }}>{m.content}</div>
            </div>
          ))}
          {busy && <div style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--ink-light)' }}>正在思考…</div>}
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <InkInput value={input} onChange={setInput}
              placeholder="用自然语言补充或修改内容（回车发送）…"
              disabled={busy}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); send() } }} />
          </div>
          <InkButton onClick={send} disabled={busy || !input.trim()}>发送</InkButton>
          <InkButton variant="secondary" onClick={generateNow} disabled={busy}>
            {busy ? '生成中…' : '生成简历'}
          </InkButton>
        </div>
        <p style={{ marginTop: 10, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-faint)' }}>
          直接说“生成简历 / 好了 / 可以了”即可立即出稿并保存到桌面。
        </p>
      </Card>
    </div>
  )
}

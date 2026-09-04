import { useState, useEffect } from 'react'
import { api } from '../api'
import { PageTitle, SubTitle, Card, InkButton, InkInput, InkSelect, Toast, LoadingDots, InkDivider, EmptyState } from '../components'

export default function CramPage() {
  const [projects, setProjects] = useState<any[]>([])
  const [resumes, setResumes] = useState<any[]>([])
  const [projectId, setProjectId] = useState('')
  const [resumeId, setResumeId] = useState('')
  const [focus, setFocus] = useState('')
  const [taskId, setTaskId] = useState('')
  const [task, setTask] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => {})
    api.listResumes().then(setResumes).catch(() => {})
  }, [])

  const handleGenerate = async () => {
    if (!projectId) { setToast('请选择项目'); return }
    setLoading(true); setToast('')
    try {
      const areas = focus.split(/[,，]/).map(s => s.trim()).filter(Boolean)
      const res = await api.generateCram(projectId, resumeId || undefined, areas.length ? areas : undefined)
      setTaskId(res.task_id)
      setToast('生成任务已提交')
    } catch (e: any) {
      setToast(e.message)
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!taskId) return
    const timer = setInterval(async () => {
      try {
        const t = await api.getCramTask(taskId)
        setTask(t)
        if (t.status === 'completed' || t.status === 'failed') clearInterval(timer)
      } catch {}
    }, 3000)
    return () => clearInterval(timer)
  }, [taskId])

  const projectOptions = projects.filter(p => p.index_status === 'completed').map(p => ({
    value: p.id, label: `${p.name} (${p.chunk_count}块)`,
  }))
  const resumeOptions = resumes.map(r => ({ value: r.id, label: `${r.candidate_name}` }))

  return (
    <div>
      <PageTitle>秘籍</PageTitle>
      <SubTitle>针对你的修为，定制专属备考秘籍</SubTitle>
      {toast && <Toast message={toast} type={toast.includes('失败') ? 'error' : 'info'} />}

      <Card>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
          生成八股文
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
              藏经阁 (项目)
            </label>
            {projectOptions.length > 0 ? (
              <InkSelect value={projectId} onChange={setProjectId}
                options={[{ value: '', label: '请选择...' }, ...projectOptions]}
                style={{ width: '100%' }} />
            ) : (
              <InkSelect value="" onChange={() => {}} disabled
                options={[{ value: '', label: '暂无可用项目' }]}
                style={{ width: '100%' }} />
            )}
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
              拜帖 (简历, 可选)
            </label>
            <InkSelect value={resumeId} onChange={setResumeId}
              options={[{ value: '', label: '不指定' }, ...resumeOptions]}
              style={{ width: '100%' }} />
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
            重点领域（逗号分隔，可选）
          </label>
          <InkInput value={focus} onChange={setFocus} placeholder="如：JVM调优, 分布式锁, 缓存设计" />
        </div>

        <InkButton onClick={handleGenerate} disabled={loading || !projectId}>
          {loading ? '提交中...' : '修炼秘籍'}
        </InkButton>
      </Card>

      {task && (
        <Card style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, color: 'var(--ink-dark)' }}>
              生成结果
            </h3>
            <span style={{
              fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, padding: '4px 12px', borderRadius: 3,
              background: task.status === 'completed' ? 'rgba(90,122,106,0.1)' :
                         task.status === 'failed' ? 'rgba(194,58,43,0.1)' : 'rgba(106,138,154,0.1)',
              color: task.status === 'completed' ? 'var(--jade-green)' :
                    task.status === 'failed' ? 'var(--seal-red)' : 'var(--water-blue)',
            }}>
              {task.status === 'pending' && '等待中'}
              {task.status === 'processing' && '修炼中...'}
              {task.status === 'completed' && '修炼完成'}
              {task.status === 'failed' && '修炼失败'}
            </span>
          </div>

          {task.status === 'processing' && (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <LoadingDots />
              <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--ink-light)', marginTop: 12 }}>
                秘籍修炼中，请稍候...
              </p>
            </div>
          )}

          {task.status === 'completed' && task.content && (
            <>
              <InkDivider />
              <div style={{
                fontFamily: "'Noto Serif SC', serif", fontSize: 14,
                color: 'var(--ink-dark)', lineHeight: 2,
                whiteSpace: 'pre-wrap', maxHeight: 600, overflow: 'auto',
                padding: '0 4px',
              }}>
                {task.content}
              </div>
              <InkDivider />
              <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
                共 {task.word_count || 0} 字
              </p>
            </>
          )}

          {task.status === 'failed' && (
            <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--seal-red)' }}>
              {task.error_msg || '生成失败，请重试'}
            </p>
          )}
        </Card>
      )}

      {!task && !loading && (
        <EmptyState icon="&#128221;" text="选择项目，修炼专属八股秘籍" />
      )}
    </div>
  )
}

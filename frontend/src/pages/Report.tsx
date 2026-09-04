import { useState, useEffect } from 'react'
import { api } from '../api'
import { PageTitle, SubTitle, Card, Toast, InkDivider, StatusChip } from '../components'

const DIFF_LABELS: Record<string, string> = { junior: '初级', mid: '中级', senior: '高级', hell: '地狱' }
const FOCUS_LABELS: Record<string, string> = { depth: '深究', balanced: '兼顾', breadth: '广博' }

export default function ReportPage() {
  const [sessions, setSessions] = useState<any[]>([])
  const [activeId, setActiveId] = useState('')
  const [report, setReport] = useState<any>(null)
  const [listLoading, setListLoading] = useState(true)
  const [reportLoading, setReportLoading] = useState(false)
  const [toast, setToast] = useState('')

  const summary = report?.summary
  const radar = report?.radar_data

  const loadList = async () => {
    try {
      const list = await api.listInterviews()
      setSessions((list || []).slice(0, 5))
    } catch (e: any) { setToast(e.message) }
    finally { setListLoading(false) }
  }

  const openReport = async (id: string) => {
    setActiveId(id); setReportLoading(true); setToast('')
    try {
      setReport(await api.getReport(id))
    } catch (e: any) { setToast(e.message) }
    finally { setReportLoading(false) }
  }

  const removeSession = async (id: string) => {
    try {
      await api.deleteInterview(id)
      setToast('已除去此场记录')
      if (activeId === id) { setActiveId(''); setReport(null) }
      await loadList()
    } catch (e: any) { setToast(e.message) }
  }

  useEffect(() => {
    loadList()
    const q = new URLSearchParams(window.location.search).get('session')
    if (q) openReport(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <PageTitle>品鉴</PageTitle>
      <SubTitle>回顾论道全程，审视自身修为</SubTitle>
      {toast && <Toast message={toast} type={toast.includes('失败') || toast.includes('错误') ? 'error' : 'info'} />}

      <Card>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 8, color: 'var(--ink-dark)' }}>
          过往论道
        </h3>
        <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginBottom: 16 }}>
          近五场切磋之迹 —— 未竟者可续其论，已竟者可观品鉴
        </p>
        {listLoading ? (
          <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--ink-light)' }}>翻阅卷宗中...</div>
        ) : sessions.length === 0 ? (
          <p style={{ padding: '18px 0', textAlign: 'center', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--ink-light)' }}>
            尚无卷宗，且往「论道」开一场
          </p>
        ) : (
          sessions.map((s: any) => (
            <div key={s.id} style={{ padding: '12px 0', borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 17, color: 'var(--ink-dark)' }}>
                    {s.resume_name || '无名拜帖'}
                    <span style={{ fontFamily: "'Noto Serif SC', monospace", fontSize: 11, color: 'var(--ink-faint)', marginLeft: 8 }}>#{s.id?.slice(0, 8)}</span>
                  </div>
                  <div style={{ marginTop: 4, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-medium)' }}>
                    {DIFF_LABELS[s.difficulty] || '—'} · {FOCUS_LABELS[s.focus] || '均衡'} · 已答 {Math.max(0, (s.current_round ?? 0) - 1)} / {s.max_rounds ?? '?'} 轮
                  </div>
                </div>
                <StatusChip status={s.completed ? 'done' : 'live'} labels={{ done: '已竟', live: '未竟' }} colors={{ done: 'var(--jade-green)', live: 'var(--seal-red)' }} />
                {s.completed ? (
                  <button onClick={() => openReport(s.id)} disabled={reportLoading} style={{
                    whiteSpace: 'nowrap', padding: '5px 14px', fontSize: 12, cursor: 'pointer', borderRadius: 999,
                    background: 'var(--ink-black)', color: '#fff', border: 'none', fontFamily: "'ZCOOL XiaoWei', serif", letterSpacing: 1,
                  }}>观品鉴</button>
                ) : (
                  <button onClick={() => window.location.href = `/interview?session=${s.id}`} style={{
                    whiteSpace: 'nowrap', padding: '5px 14px', fontSize: 12, cursor: 'pointer', borderRadius: 999,
                    background: 'var(--seal-red)', color: '#fff', border: 'none', fontFamily: "'ZCOOL XiaoWei', serif", letterSpacing: 1,
                  }}>续论道</button>
                )}
                <button onClick={() => removeSession(s.id)} style={{
                  whiteSpace: 'nowrap', fontSize: 12, cursor: 'pointer', padding: '5px 10px', borderRadius: 999,
                  background: 'transparent', color: 'var(--ink-light)', border: '1px solid var(--paper-dark)', fontFamily: "'ZCOOL XiaoWei', serif",
                }}>除去</button>
              </div>
            </div>
          ))
        )}
      </Card>

      {report && (
        <>
          <Card style={{ marginTop: 24 }}>
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
              总览
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 42, color: 'var(--seal-red)' }}>
                  {summary?.avg_score ?? '—'}
                </div>
                <div style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginTop: 4 }}>
                  综合评分
                </div>
              </div>
              <div>
                <div style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginBottom: 8 }}>所长</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(summary?.strength_tags || []).map((t: string) => (
                    <span key={t} style={{
                      padding: '3px 10px', borderRadius: 3, fontSize: 12,
                      background: 'rgba(90,122,106,0.08)', color: 'var(--jade-green)',
                      fontFamily: "'Noto Serif SC', serif",
                    }}>{t}</span>
                  ))}
                </div>
              </div>
              <div>
                <div style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)', marginBottom: 8 }}>所短</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(summary?.weakness_tags || []).map((t: string) => (
                    <span key={t} style={{
                      padding: '3px 10px', borderRadius: 3, fontSize: 12,
                      background: 'rgba(194,58,43,0.06)', color: 'var(--seal-red)',
                      fontFamily: "'Noto Serif SC', serif",
                    }}>{t}</span>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          {radar && (
            <Card style={{ marginTop: 24 }}>
              <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
                能力图谱
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {(radar.labels || []).map((label: string, i: number) => {
                  const val = radar.values[i] || 0
                  const pct = (val / 10) * 100
                  return (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ width: 80, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, color: 'var(--ink-medium)', textAlign: 'right' }}>
                        {label}
                      </span>
                      <div style={{ flex: 1, height: 20, background: 'rgba(0,0,0,0.04)', borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{
                          width: `${pct}%`, height: '100%',
                          background: 'linear-gradient(90deg, var(--ink-faint), var(--ink-dark))',
                          borderRadius: 2, transition: 'width 1s ease',
                        }} />
                      </div>
                      <span style={{ width: 36, fontFamily: "'Noto Serif SC', monospace", fontSize: 14, color: 'var(--ink-dark)' }}>
                        {val.toFixed(1)}
                      </span>
                    </div>
                  )
                })}
              </div>
            </Card>
          )}

          {Array.isArray(report.category_stats) && report.category_stats.length > 0 && (
            <Card style={{ marginTop: 24 }}>
              <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
                覆盖方向
              </h3>
              {report.category_stats.map((cs: any) => (
                <div key={cs.cat || cs.label} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 0', borderBottom: '1px solid rgba(0,0,0,0.04)',
                }}>
                  <span style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-dark)' }}>
                    {cs.label}
                  </span>
                  {cs.avg != null ? (
                    <span style={{
                      fontFamily: "'Noto Serif SC', monospace", fontSize: 14,
                      color: cs.avg >= 7 ? 'var(--jade-green)' : cs.avg >= 5 ? 'var(--water-blue)' : 'var(--seal-red)',
                    }}>
                      {cs.count} 题 · 均分 {cs.avg?.toFixed(1) ?? '—'}
                    </span>
                  ) : (
                    <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
                      未考察
                    </span>
                  )}
                </div>
              ))}
            </Card>
          )}

          {report.round_details?.length > 0 && (
            <Card style={{ marginTop: 24 }}>
              <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
                各轮品鉴
              </h3>
              {report.round_details.map((d: any, i: number) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0' }}>
                    <span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 17, color: 'var(--ink-dark)' }}>
                      第{d.round}轮
                      {d.cat_label && (
                        <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--water-blue)', marginLeft: 10 }}>
                          · {d.cat_label}
                        </span>
                      )}
                      {d.skill && (
                        <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, color: 'var(--ink-light)', marginLeft: 8 }}>
                          · {d.skill}
                        </span>
                      )}
                    </span>
                    <span style={{
                      fontFamily: "'Noto Serif SC', monospace", fontSize: 16,
                      color: (d.score || 0) >= 7 ? 'var(--jade-green)' : (d.score || 0) >= 5 ? 'var(--water-blue)' : 'var(--seal-red)',
                    }}>
                      {d.score?.toFixed(1) ?? '—'}
                    </span>
                  </div>
                  {d.comment && (
                    <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 13, color: 'var(--ink-medium)', lineHeight: 1.7, paddingBottom: 12 }}>
                      {d.comment}
                    </p>
                  )}
                  {i < report.round_details.length - 1 && <InkDivider />}
                </div>
              ))}
            </Card>
          )}

          {report.improvement_suggestion && (
            <Card style={{ marginTop: 24, borderLeft: '3px solid var(--seal-red)' }}>
              <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 12, color: 'var(--ink-dark)' }}>
                赠言
              </h3>
              <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 15, color: 'var(--ink-dark)', lineHeight: 2 }}>
                {report.improvement_suggestion}
              </p>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

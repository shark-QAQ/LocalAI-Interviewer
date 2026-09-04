import { useState, useEffect } from 'react'
import { api } from '../api'
import type { MbtiAnswer, MbtiDimension, MbtiQuestion, MbtiResult } from '../api'
import { PageTitle, SubTitle, Card, InkButton, Toast, ProgressBar, InkDivider, LoadingDots } from '../components'
import { LockGate } from '../components/ApiGate'
import RadarChart from '../components/RadarChart'

type Phase = 'gate' | 'intro' | 'genq' | 'quiz' | 'loading' | 'result'

function pickName(dim: MbtiDimension): string {
  return dim.pick === dim.left ? dim.left_name : dim.right_name
}
function pickPct(dim: MbtiDimension): number {
  return dim.pick === dim.left ? dim.left_pct : dim.right_pct
}
function dimLine(dim: MbtiDimension): string {
  return `${dim.label}：${dim.left}·${dim.left_name} ${dim.left_pct}% ／ ${dim.right}·${dim.right_name} ${dim.right_pct}% → 命中 ${dim.pick}·${pickName(dim)}（${pickPct(dim)}%）`
}

export default function MbtiPage() {
  const [phase, setPhase] = useState<Phase>('gate')
  const [gateMsg, setGateMsg] = useState('')
  const [questions, setQuestions] = useState<MbtiQuestion[]>([])
  const [dimLabels, setDimLabels] = useState<{ code: string; label: string }[]>([])
  const [idx, setIdx] = useState(0)
  const [answers, setAnswers] = useState<MbtiAnswer[]>([])
  const [result, setResult] = useState<MbtiResult | null>(null)
  const [toast, setToast] = useState('')

  useEffect(() => {
    api.getLlmSettings()
      .then((s) => {
        if (s.provider !== 'deepseek') {
          setGateMsg('为保证可信度，本测试仅在使用 DeepSeek API 时开放。当前为本地模型，请先到「设置」把文本生成提供方切到 DeepSeek。')
        } else {
          setPhase('intro')
        }
      })
      .catch((e) => setGateMsg(e.message))
  }, [])

  const start = async () => {
    setToast('')
    setPhase('genq')
    try {
      const data = await api.getMbtiQuestions()
      setQuestions(data.questions)
      setDimLabels((data.dimensions || []).map((d) => ({ code: d.code, label: d.label })))
      setAnswers([])
      setIdx(0)
      setPhase('quiz')
    } catch (e: any) {
      // 后端 403 时同样落到门禁提示
      if (String(e.message).includes('仅在使用')) {
        setGateMsg(e.message)
        setPhase('gate')
      } else {
        setToast(e.message)
        setPhase('intro')
      }
    }
  }

  const choose = async (pickA: boolean) => {
    const q = questions[idx]
    const pole = pickA ? q.poleA : q.poleB
    const next = [...answers, { dim: q.dim, pole }]
    setAnswers(next)

    if (idx + 1 < questions.length) {
      setIdx(idx + 1)
      return
    }

    // 最后一题：提交计分
    setPhase('loading')
    setToast('')
    try {
      const r = await api.submitMbti(next)
      setResult(r)
      setPhase('result')
    } catch (e: any) {
      setToast(e.message)
      setPhase('quiz') // 允许重答最后一题
    }
  }

  const again = () => {
    setResult(null); setAnswers([]); setIdx(0)
    setPhase('intro')
  }

  // ---------- 渲染 ----------
  if (phase === 'gate') {
    return (
      <div>
        <PageTitle>问心</PageTitle>
        <SubTitle>MBTI 职业性格测试</SubTitle>
        <LockGate
          title="MBTI 职业测试 · 暂未解锁"
          hint={gateMsg || '为保证判分可信与稳定，本测试仅在使用 DeepSeek API 时开放。点击锁图标查看如何切换。'}
        />
      </div>
    )
  }

  if (phase === 'intro') {
    return (
      <div>
        <PageTitle>问心</PageTitle>
        <SubTitle>MBTI 职业性格测试</SubTitle>
        <Card style={{ maxWidth: 720 }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 24, marginBottom: 16, color: 'var(--ink-dark)' }}>
            认识自我，探索更合适的职业方向
          </h3>
          <ul style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-medium)', lineHeight: 2 }}>
            <li>共 20 道二选一情景题（外向/内向、实感/直觉、思考/情感、判断/感知 四维各 5 题），约 3~5 分钟。</li>
            <li>选项没有对错，凭直觉选你更偏好的那一个。</li>
            <li>完成后得到性格类型、各维度倾向百分比，以及大模型给出的更合适行业推荐（含适合度百分比）。</li>
            <li>结果仅供参考与自我探索，不构成专业职业测评结论。</li>
          </ul>
          <InkButton onClick={start} style={{ marginTop: 12 }}>开始测试</InkButton>
        </Card>
      </div>
    )
  }

  if (phase === 'result' && result) {
    return (
      <div>
        <PageTitle>问心</PageTitle>
        <SubTitle>你的性格类型：{result.type}</SubTitle>
        {toast && <Toast message={toast} type="info" />}

        <Card style={{ maxWidth: 720 }}>
          <div style={{ textAlign: 'center', marginBottom: 20 }}>
            <div style={{
              display: 'inline-block', fontSize: 64, letterSpacing: 8,
              fontFamily: "'Ma Shan Zheng', cursive", color: 'var(--seal-red)',
              borderBottom: '3px solid var(--seal-red)', padding: '0 18px 8px',
            }}>{result.type}</div>
            <div style={{ marginTop: 10, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 18, color: 'var(--ink-medium)' }}>
              {result.type_full}{result.borderline ? '（存在倾向不明显，仅供参考）' : ''}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <RadarChart
              size={300}
              axes={result.dimensions.map((d) => ({ label: `${d.pick} ${pickName(d)}`, value: pickPct(d) }))}
            />
          </div>
          <div style={{ marginTop: 16 }}>
            {result.dimensions.map((d) => (
              <div key={d.dim} style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 13, color: 'var(--ink-medium)', lineHeight: 1.9 }}>
                {dimLine(d)}
              </div>
            ))}
          </div>
          <InkDivider />
          <h4 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 18, color: 'var(--ink-dark)', marginBottom: 8 }}>性格画像</h4>
          <p style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 14, color: 'var(--ink-medium)', lineHeight: 1.9, whiteSpace: 'pre-wrap' }}>{result.summary}</p>
        </Card>

        <Card style={{ maxWidth: 720, marginTop: 20 }}>
          <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 16, color: 'var(--ink-dark)' }}>
            更适合的行业方向
          </h3>
          {result.industries.length >= 3 && (
            <div style={{ textAlign: 'center', marginBottom: 12 }}>
              <RadarChart
                size={280}
                color="var(--jade-green)"
                axes={result.industries.slice(0, 5).map((it) => ({
                  label: it.name.length > 4 ? it.name.slice(0, 4) + '…' : it.name,
                  value: it.pct,
                }))}
              />
            </div>
          )}
          {result.industries.map((it) => (
            <div key={it.name} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 16, color: 'var(--ink-dark)' }}>{it.name}</span>
                <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14, color: 'var(--seal-red)' }}>适合度 {it.pct}%</span>
              </div>
              <div style={{ margin: '6px 0 2px' }}><ProgressBar pct={it.pct} color="var(--seal-red)" height={6} /></div>
              <div style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 12, color: 'var(--ink-light)' }}>{it.why}</div>
            </div>
          ))}
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--ink-faint)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
            行业适合度由 AI 依据你的性格画像生成，用于探索参考，请结合兴趣与能力综合判断。
          </div>
          <div style={{ marginTop: 18 }}>
            <InkButton onClick={again} variant="secondary">再测一次</InkButton>
          </div>
        </Card>
      </div>
    )
  }

  // 生成题目中 / AI 分析结果中：给明确的加载反馈
  if (phase === 'genq' || phase === 'loading') {
    return (
      <div>
        <PageTitle>问心</PageTitle>
        <SubTitle>{phase === 'genq' ? 'AI 生成题目中…' : '分析你的性格…'}</SubTitle>
        <Card style={{ maxWidth: 720, textAlign: 'center', padding: '56px 24px' }}>
          <LoadingDots />
          <p style={{ marginTop: 20, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 15, color: 'var(--ink-light)', lineHeight: 1.9 }}>
            {phase === 'genq'
              ? 'AI 正在四维并行生成 20 道性格测试题，通常几秒到十几秒，请稍候…'
              : '正在依据你的作答分析性格与行业方向，请稍候…'}
          </p>
        </Card>
      </div>
    )
  }

  // quiz
  const q = questions[idx]
  const progressPct = questions.length ? Math.round(((answers.length) / questions.length) * 100) : 0
  return (
    <div>
      <PageTitle>问心</PageTitle>
      <SubTitle>MBTI 职业性格测试 · 第 {idx + 1} / {questions.length} 题</SubTitle>
      {toast && <Toast message={toast} type="info" />}

      <div style={{ maxWidth: 720 }}>
        <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--ink-faint)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
          <span>已答 {answers.length} / {questions.length}</span>
        </div>
        <ProgressBar pct={progressPct} color="var(--seal-red)" height={5} />
      </div>

      <Card style={{ maxWidth: 720, marginTop: 20 }}>
        {!q ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 16 }}>题目加载中…</p>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 8, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }}>
              {dimLabels.find((d) => d.code === q.dim)?.label || ''}
            </div>
            <h3 style={{ fontFamily: "'Noto Serif SC', serif", fontSize: 19, lineHeight: 1.7, color: 'var(--ink-black)', marginBottom: 26, fontWeight: 600 }}>
              {q.text}
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <InkButton variant="secondary" onClick={() => choose(true)}
                style={{ textAlign: 'left', padding: '16px 20px', height: 'auto', lineHeight: 1.6, whiteSpace: 'normal' }}>
                {q.opA}
              </InkButton>
              <InkButton variant="secondary" onClick={() => choose(false)}
                style={{ textAlign: 'left', padding: '16px 20px', height: 'auto', lineHeight: 1.6, whiteSpace: 'normal' }}>
                {q.opB}
              </InkButton>
            </div>
            <div style={{ marginTop: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {idx > 0 ? (
                <InkButton variant="ghost" onClick={() => { setIdx(idx - 1); setAnswers(answers.slice(0, -1)) }}>上一题</InkButton>
              ) : <span />}
              <span style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-faint)' }}>凭直觉选择即可</span>
            </div>
          </>
        )}
      </Card>
    </div>
  )
}

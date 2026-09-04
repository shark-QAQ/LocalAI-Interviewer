import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'
import { api } from '../api'
import type { LlmSettings } from '../api'
import { PageTitle, SubTitle, Card, InkButton, InkInput, InkSelect, Toast, InkDivider } from '../components'

const PROVIDER_OPTIONS = [
  { value: 'ollama', label: '本地 Ollama' },
  { value: 'deepseek', label: 'DeepSeek API' },
]

const DEFAULT_MODEL = 'deepseek-v4-flash'
const DEFAULT_BASE_URL = 'https://api.deepseek.com'

function labelStyle(): CSSProperties {
  return { display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }
}

export default function SettingsPage() {
  const [provider, setProvider] = useState<'ollama' | 'deepseek'>('ollama')
  const [model, setModel] = useState(DEFAULT_MODEL)
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL)
  const [thinkingOn, setThinkingOn] = useState(false) // 深度思考（默认关，更快）
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [hasKey, setHasKey] = useState(false)
  const [keyTail, setKeyTail] = useState('')
  const [test, setTest] = useState<{ ok: boolean; message: string; detail?: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [toast, setToast] = useState('')

  const load = () =>
    api.getLlmSettings()
      .then((s: LlmSettings) => {
        setProvider(s.provider)
        setModel(s.deepseek_model || DEFAULT_MODEL)
        setBaseUrl(s.deepseek_base_url || DEFAULT_BASE_URL)
        setThinkingOn(!(s.deepseek_disable_thinking ?? true))
        setHasKey(s.deepseek_api_key?.has_key ?? false)
        setKeyTail(s.deepseek_api_key?.tail ?? '')
        return s.provider
      })
      .catch((e) => setToast(e.message))

  useEffect(() => {
    load().then((p) => {
      if (p === 'ollama') runTest('ollama')
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const needKey = provider === 'deepseek' && !hasKey && !apiKeyInput.trim()

  const runTest = async (p: 'ollama' | 'deepseek' = provider, draft?: { apiKey?: string }) => {
    setTesting(true)
    setTest(null)
    try {
      const body: Record<string, string> = { provider: p }
      if (p === 'deepseek') {
        if (model.trim()) body.deepseek_model = model.trim()
        if (baseUrl.trim()) body.deepseek_base_url = baseUrl.trim()
        const k = draft?.apiKey ?? apiKeyInput
        if (k?.trim()) body.deepseek_api_key = k.trim()
      }
      const r = await api.testLlm(body)
      setTest({
        ok: r.ok,
        message: r.ok
          ? `连接成功 · ${r.model ?? p}${r.latency_ms != null ? ` · ${r.latency_ms}ms` : ''}`
          : r.message,
      })
    } catch (e: any) {
      setTest({ ok: false, message: e.message })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (needKey) { setToast('切到 DeepSeek 前请先填写 API Key'); return }
    setSaving(true)
    try {
      const body: Record<string, unknown> = { provider }
      if (provider === 'deepseek') {
        if (model.trim()) body.deepseek_model = model.trim()
        if (baseUrl.trim()) body.deepseek_base_url = baseUrl.trim()
        body.deepseek_disable_thinking = !thinkingOn
        if (apiKeyInput.trim()) body.deepseek_api_key = apiKeyInput.trim()
      }
      const s = await api.saveLlmSettings(body as any)
      setThinkingOn(!(s.deepseek_disable_thinking ?? true))
      setHasKey(s.deepseek_api_key?.has_key ?? false)
      setKeyTail(s.deepseek_api_key?.tail ?? '')
      setApiKeyInput('')
      setToast(provider === 'deepseek' ? '已保存，立即生效（文本生成走 DeepSeek）' : '已切回本地 Ollama')
      setTest(null)
    } catch (e: any) {
      setToast(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleClearKey = async () => {
    setSaving(true)
    try {
      await api.saveLlmSettings({ provider: 'deepseek', deepseek_api_key: '__clear__' })
      setHasKey(false); setKeyTail(''); setApiKeyInput('')
      setToast('已清除 API Key')
    } catch (e: any) {
      setToast(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageTitle>设置</PageTitle>
      <SubTitle>文本生成提供方 · 模型 · 密钥</SubTitle>
      {toast && <Toast message={toast} type={toast.includes('失败') || toast.includes('请先') ? 'error' : 'info'} />}

      <Card>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
          文本生成
        </h3>

        <div style={{ maxWidth: 520 }}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle()}>提供方</label>
            <InkSelect
              value={provider}
              onChange={(v) => {
                const p = v as 'ollama' | 'deepseek'
                setProvider(p); setTest(null)
                if (p === 'ollama') runTest('ollama')
              }}
              options={PROVIDER_OPTIONS}
              style={{ width: '100%' }} />
            <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.6, color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
              {provider === 'deepseek'
                ? '出题 / 问答 / 评分 / 八股等文本生成走 DeepSeek API。'
                : '使用本地 Ollama 生成（模型：请先在 Ollama 拉取）。'}
              <br />
              向量检索（Embedding）始终用本地 bge-m3，与文本生成提供方无关。
            </div>
          </div>

          {provider === 'deepseek' && (
            <>
              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle()}>DeepSeek 模型名</label>
                <InkInput value={model} onChange={setModel} placeholder={DEFAULT_MODEL} />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle()}>API Key</label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <div style={{ flex: 1 }}>
                    <InkInput
                      type="password"
                      value={apiKeyInput}
                      onChange={setApiKeyInput}
                      placeholder={hasKey ? `已设置（……${keyTail}），留空则保持不变` : 'sk-...'}
                    />
                  </div>
                  {hasKey && (
                    <InkButton onClick={handleClearKey} disabled={saving}>
                      清除已存 Key
                    </InkButton>
                  )}
                </div>
                {hasKey && !apiKeyInput && (
                  <div style={{ marginTop: 4, fontSize: 12, color: 'var(--jade-green)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
                    ✓ 已配置 Key（尾号 ……{keyTail}），留空保存不会改动
                  </div>
                )}
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle()}>API 地址（默认官方，可填中转/代理）</label>
                <InkInput value={baseUrl} onChange={setBaseUrl} placeholder={DEFAULT_BASE_URL} />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle()}>深度思考（DeepSeek）</label>
                <InkSelect
                  value={thinkingOn ? 'on' : 'off'}
                  onChange={(v) => setThinkingOn(v === 'on')}
                  options={[
                    { value: 'off', label: '关闭（更快，默认推荐）' },
                    { value: 'on', label: '开启（更深入，但每次更慢）' },
                  ]}
                  style={{ width: '100%' }} />
                <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.6, color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
                  该模型默认会在作答前先“思考”一长段。出题/评分/品鉴建议关闭以显著提速；需要深度推理时再开启。
                </div>
              </div>
            </>
          )}

          <InkDivider />

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <InkButton onClick={handleSave} disabled={saving || needKey}>
              {saving ? '保存中...' : '保存并应用'}
            </InkButton>
            <InkButton onClick={() => runTest()} disabled={testing || needKey}>
              {testing ? '测试中...' : '测试连接'}
            </InkButton>
          </div>
          {needKey && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--seal-red)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
              使用 DeepSeek 需先填写 API Key（或已保存过 Key）
            </div>
          )}

          {test && (
            <div style={{
              marginTop: 14, padding: '10px 14px', borderRadius: 3, fontSize: 13,
              fontFamily: "'Noto Serif SC', serif", lineHeight: 1.5,
              background: test.ok ? 'rgba(90,122,106,0.08)' : 'rgba(194,58,43,0.07)',
              color: test.ok ? 'var(--jade-green)' : 'var(--seal-red)',
              border: `1px solid ${test.ok ? 'rgba(90,122,106,0.25)' : 'rgba(194,58,43,0.25)'}`,
            }}>
              {test.ok ? '✓ ' : '✕ '}{test.message}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

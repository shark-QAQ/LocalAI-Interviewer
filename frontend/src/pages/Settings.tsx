import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'
import { api } from '../api'
import type { LlmSettings } from '../api'
import { PageTitle, SubTitle, Card, InkButton, InkInput, InkSelect, Toast, InkDivider } from '../components'

const PROVIDER_OPTIONS = [
  { value: 'ollama', label: '本地 Ollama' },
  { value: 'deepseek', label: 'DeepSeek API' },
]

const EMBED_PROVIDER_OPTIONS = [
  { value: 'ollama', label: 'Ollama (本地 bge-m3)' },
  { value: 'huggingface', label: 'HuggingFace (本地 sentence-transformers)' },
]

const DEFAULT_MODEL = 'deepseek-v4-flash'
const DEFAULT_BASE_URL = 'https://api.deepseek.com'
const DEFAULT_HF_MODEL = 'BAAI/bge-m3'

function labelStyle(): CSSProperties {
  return { display: 'block', marginBottom: 6, fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12, color: 'var(--ink-light)' }
}

export default function SettingsPage() {
  const [provider, setProvider] = useState<'ollama' | 'deepseek'>('ollama')
  const [model, setModel] = useState(DEFAULT_MODEL)
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL)
  const [thinkingOn, setThinkingOn] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [hasKey, setHasKey] = useState(false)
  const [keyTail, setKeyTail] = useState('')
  const [test, setTest] = useState<{ ok: boolean; message: string; detail?: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [toast, setToast] = useState('')

  const [embedProvider, setEmbedProvider] = useState<'ollama' | 'huggingface'>('ollama')
  const [hfModel, setHfModel] = useState(DEFAULT_HF_MODEL)
  const [embedTest, setEmbedTest] = useState<{ ok: boolean; message: string } | null>(null)
  const [embedTesting, setEmbedTesting] = useState(false)

  const load = () =>
    api.getLlmSettings()
      .then((s: LlmSettings) => {
        setProvider(s.provider)
        setModel(s.deepseek_model || DEFAULT_MODEL)
        setBaseUrl(s.deepseek_base_url || DEFAULT_BASE_URL)
        setThinkingOn(!(s.deepseek_disable_thinking ?? true))
        setHasKey(s.deepseek_api_key?.has_key ?? false)
        setKeyTail(s.deepseek_api_key?.tail ?? '')
        setEmbedProvider(s.embedding?.provider || 'ollama')
        setHfModel(s.embedding?.model || DEFAULT_HF_MODEL)
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

  const runEmbedTest = async () => {
    setEmbedTesting(true)
    setEmbedTest(null)
    try {
      const r = await api.testEmbed({
        embedding_provider: embedProvider,
        huggingface_model: embedProvider === 'huggingface' ? hfModel.trim() : undefined,
      })
      setEmbedTest({
        ok: r.ok,
        message: r.ok
          ? `嵌入就绪 · ${r.model ?? r.provider}${r.latency_ms != null ? ` · ${r.latency_ms}ms` : ''}`
          : r.message,
      })
    } catch (e: any) {
      setEmbedTest({ ok: false, message: e.message })
    } finally {
      setEmbedTesting(false)
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
      body.embedding_provider = embedProvider
      if (embedProvider === 'huggingface' && hfModel.trim()) {
        body.huggingface_model = hfModel.trim()
      }
      const s = await api.saveLlmSettings(body as any)
      setThinkingOn(!(s.deepseek_disable_thinking ?? true))
      setHasKey(s.deepseek_api_key?.has_key ?? false)
      setKeyTail(s.deepseek_api_key?.tail ?? '')
      setApiKeyInput('')
      setEmbedProvider(s.embedding?.provider as 'ollama' | 'huggingface' || 'ollama')
      setHfModel(s.embedding?.model || DEFAULT_HF_MODEL)
      const embedMsg = embedProvider === 'huggingface' ? '（嵌入走 HuggingFace 本地模型）' : '（嵌入走 Ollama bge-m3）'
      setToast(provider === 'deepseek'
        ? `已保存，立即生效（文本生成走 DeepSeek ${embedMsg}）`
        : `已切回本地 Ollama ${embedMsg}`)
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
      <SubTitle>文本生成提供方 · 嵌入模型 · 密钥</SubTitle>
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
                  该模型默认会在作答前先"思考"一长段。出题/评分/品鉴建议关闭以显著提速；需要深度推理时再开启。
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

      <Card style={{ marginTop: 20 }}>
        <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, marginBottom: 20, color: 'var(--ink-dark)' }}>
          向量嵌入（Embedding）
        </h3>

        <div style={{ maxWidth: 520 }}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle()}>嵌入提供方</label>
            <InkSelect
              value={embedProvider}
              onChange={(v) => {
                setEmbedProvider(v as 'ollama' | 'huggingface')
                setEmbedTest(null)
              }}
              options={EMBED_PROVIDER_OPTIONS}
              style={{ width: '100%' }} />
            <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.6, color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
              {embedProvider === 'huggingface'
                ? '使用本地 HuggingFace sentence-transformers 加载模型，无需 Ollama。首次加载较慢，后续自动缓存。'
                : '通过本地 Ollama 运行 bge-m3 嵌入模型（需先 ollama pull bge-m3）。'}
            </div>
          </div>

          {embedProvider === 'huggingface' && (
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle()}>模型名或本地路径</label>
              <InkInput value={hfModel} onChange={setHfModel} placeholder="BAAI/bge-m3 或 D:\models\bge-m3" />
              <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.6, color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif" }}>
                填 HuggingFace 模型 ID（如 BAAI/bge-m3）会自动下载；填本地目录路径（如 D:\models\bge-m3）则直接加载，不联网。
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <InkButton onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '保存并应用'}
            </InkButton>
            <InkButton onClick={runEmbedTest} disabled={embedTesting}>
              {embedTesting ? '测试中...' : '测试嵌入'}
            </InkButton>
          </div>

          {embedTest && (
            <div style={{
              marginTop: 14, padding: '10px 14px', borderRadius: 3, fontSize: 13,
              fontFamily: "'Noto Serif SC', serif", lineHeight: 1.5,
              background: embedTest.ok ? 'rgba(90,122,106,0.08)' : 'rgba(194,58,43,0.07)',
              color: embedTest.ok ? 'var(--jade-green)' : 'var(--seal-red)',
              border: `1px solid ${embedTest.ok ? 'rgba(90,122,106,0.25)' : 'rgba(194,58,43,0.25)'}`,
            }}>
              {embedTest.ok ? '✓ ' : '✕ '}{embedTest.message}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

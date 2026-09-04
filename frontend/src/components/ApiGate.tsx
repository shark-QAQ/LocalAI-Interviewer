import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Modal, InkButton } from '../components'

/** “锁链 X 形交叉 + 中间挂锁”锁定图标。点击弹提示：功能需 DeepSeek API，请切换模型。 */
function LockGlyph({ size = 120 }: { size?: number }) {
  const s = 200
  return (
    <svg width={size} height={size} viewBox={`0 0 ${s} ${s}`} fill="none">
      {/* 两条交叉锁链（虚线粗线近似链环） */}
      <line x1="18" y1="18" x2="128" y2="128" stroke="var(--ink-faint)" strokeWidth="14" strokeDasharray="2 12" strokeLinecap="round" opacity="0.85" />
      <line x1="182" y1="18" x2="72" y2="128" stroke="var(--ink-faint)" strokeWidth="14" strokeDasharray="2 12" strokeLinecap="round" opacity="0.85" />
      <line x1="18" y1="182" x2="128" y2="72" stroke="var(--ink-faint)" strokeWidth="14" strokeDasharray="2 12" strokeLinecap="round" opacity="0.85" />
      <line x1="182" y1="182" x2="72" y2="72" stroke="var(--ink-faint)" strokeWidth="14" strokeDasharray="2 12" strokeLinecap="round" opacity="0.85" />
      {/* 中间挂锁 */}
      <g>
        <path d="M100 88 a22 22 0 0 1 44 0 v10 h-44 z" stroke="var(--seal-red)" strokeWidth="9" fill="none" strokeLinecap="round" />
        <rect x="72" y="96" width="56" height="46" rx="8" fill="var(--seal-red)" />
        <circle cx="100" cy="116" r="5" fill="var(--paper-white)" />
        <rect x="97" y="118" width="6" height="14" rx="2" fill="var(--paper-white)" />
      </g>
    </svg>
  )
}

export function LockGate({
  title = '功能受限',
  hint,
}: {
  title?: string
  hint?: string
}) {
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '48px 24px', textAlign: 'center' }}>
      <button
        aria-label="点击查看解锁方式"
        onClick={() => setOpen(true)}
        style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 8, outline: 'none' }}
      >
        <LockGlyph />
      </button>
      <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 24, color: 'var(--ink-dark)', margin: '8px 0 6px' }}>{title}</h3>
      <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14, color: 'var(--ink-light)', maxWidth: 460, lineHeight: 1.8 }}>
        {hint || '点击上方锁图标了解如何解锁。'}
      </p>

      {open && (
        <Modal onClose={() => setOpen(false)}>
          <div style={{ textAlign: 'center', padding: '8px 4px' }}>
            <LockGlyph size={84} />
            <h3 style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 22, color: 'var(--ink-dark)', margin: '8px 0' }}>该功能需 DeepSeek API</h3>
            <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14, color: 'var(--ink-light)', lineHeight: 1.9, marginBottom: 20 }}>
              为保证生成质量与可信度，本功能仅在使用 DeepSeek API 时开放。
              当前是本地模型，请切换到 DeepSeek 后再来使用。
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
              <InkButton onClick={() => nav('/settings')}>去「设置」切换</InkButton>
              <InkButton variant="ghost" onClick={() => setOpen(false)}>知道了</InkButton>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

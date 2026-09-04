import React from 'react'

export function PageTitle({ children }: { children: React.ReactNode }) {
  return (
    <h1 style={{
      fontFamily: "'Ma Shan Zheng', cursive", fontSize: 36,
      color: 'var(--ink-black)', marginBottom: 8, letterSpacing: 6,
      position: 'relative', display: 'inline-block',
    }}>
      {children}
      <svg style={{ position: 'absolute', bottom: -4, left: 0, width: '100%', height: 6 }} viewBox="0 0 200 6">
        <path d="M0,3 Q25,0 50,3 T100,3 T150,3 T200,3" stroke="var(--seal-red)" strokeWidth="1.5" fill="none" opacity="0.4" />
      </svg>
    </h1>
  )
}

export function SubTitle({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <p style={{
      fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14,
      color: 'var(--ink-light)', marginBottom: 32, letterSpacing: 2,
      ...style,
    }}>
      {children}
    </p>
  )
}

export function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(255,255,255,0.6) 0%, rgba(245,240,232,0.4) 100%)',
      border: '1px solid var(--paper-dark)', borderRadius: 4,
      padding: 24, position: 'relative', overflow: 'hidden',
      boxShadow: '0 2px 12px rgba(0,0,0,0.04)',
      ...style,
    }}>
      {children}
    </div>
  )
}

export function InkButton({ children, onClick, disabled, variant = 'primary', style, className }: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'ghost'; style?: React.CSSProperties; className?: string;
}) {
  const base: React.CSSProperties = {
    fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 15,
    padding: '10px 28px', border: 'none', borderRadius: 3,
    cursor: disabled ? 'not-allowed' : 'pointer', letterSpacing: 2,
    transition: 'all 0.3s ease', opacity: disabled ? 0.5 : 1,
    position: 'relative', overflow: 'hidden',
  }
  const variants: Record<string, React.CSSProperties> = {
    primary: {
      background: 'var(--ink-black)', color: 'var(--paper-white)',
    },
    secondary: {
      background: 'transparent', color: 'var(--ink-black)',
      border: '1px solid var(--ink-medium)',
    },
    ghost: {
      background: 'transparent', color: 'var(--ink-medium)',
      padding: '8px 16px',
    },
  }
  return (
    <button className={className} style={{ ...base, ...variants[variant], ...style }} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  )
}

export function InkInput({ value, onChange, placeholder, disabled, type, onKeyDown, style }: {
  value: string; onChange: (v: string) => void;
  placeholder?: string; disabled?: boolean; type?: string;
  onKeyDown?: React.KeyboardEventHandler<HTMLInputElement>; style?: React.CSSProperties;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      disabled={disabled}
      type={type ?? 'text'}
      style={{
        width: '100%', padding: '10px 14px',
        fontFamily: "'Noto Serif SC', serif", fontSize: 14,
        background: 'rgba(255,255,255,0.5)',
        border: '1px solid var(--paper-dark)', borderRadius: 3,
        color: 'var(--ink-black)', outline: 'none',
        transition: 'border-color 0.3s',
        ...style,
      }}
      onFocus={(e) => e.currentTarget.style.borderColor = 'var(--ink-medium)'}
      onBlur={(e) => e.currentTarget.style.borderColor = 'var(--paper-dark)'}
    />
  )
}

export function InkSelect({ value, onChange, options, disabled, style }: {
  value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; disabled?: boolean; style?: React.CSSProperties;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      style={{
        padding: '10px 14px',
        fontFamily: "'Noto Serif SC', serif", fontSize: 14,
        background: 'rgba(255,255,255,0.5)',
        border: '1px solid var(--paper-dark)', borderRadius: 3,
        color: 'var(--ink-black)', outline: 'none', cursor: 'pointer',
        ...style,
      }}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

export function Toast({ message, type = 'info' }: { message: string; type?: 'info' | 'success' | 'error' }) {
  const colors = {
    info: 'var(--water-blue)',
    success: 'var(--jade-green)',
    error: 'var(--seal-red)',
  }
  return (
    <div style={{
      padding: '12px 20px', borderRadius: 3,
      background: colors[type], color: '#fff',
      fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 14,
      letterSpacing: 1, marginBottom: 16,
    }}>
      {message}
    </div>
  )
}

export function LoadingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center', padding: '8px 0' }}>
      {[0, 1, 2].map((i) => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: '50%', background: 'var(--ink-light)',
          animation: `dotPulse 1.4s ease-in-out ${i * 0.2}s infinite`,
        }} />
      ))}
      <style>{`
        @keyframes dotPulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </span>
  )
}

export function StatusChip({ status, labels, colors }: {
  status: string; labels: Record<string, string>; colors: Record<string, string>;
}) {
  const color = colors[status] || 'var(--ink-light)'
  const text = labels[status] || status
  return (
    <span style={{
      fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11, padding: '1px 9px',
      borderRadius: 999, whiteSpace: 'nowrap', background: color + '15', color,
    }}>{text}</span>
  )
}

export function ProgressBar({ pct, color = 'var(--water-blue)', height = 4 }: {
  pct: number | null | undefined; color?: string; height?: number;
}) {
  const width = pct == null ? 0 : Math.min(100, Math.max(0, pct))
  return (
    <div style={{ height, background: 'var(--paper-dark)', borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${width}%`, background: color, borderRadius: 2, transition: 'width .5s ease' }} />
    </div>
  )
}

export function InkDivider() {
  return (
    <svg width="100%" height="12" viewBox="0 0 400 12" preserveAspectRatio="none" style={{ display: 'block', margin: '24px 0' }}>
      <path d="M0,6 Q40,2 80,6 T160,6 T240,6 T320,6 T400,6" stroke="var(--ink-faint)" strokeWidth="0.6" fill="none" opacity="0.4" />
    </svg>
  )
}

export function EmptyState({ icon, text }: { icon: string; text: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--ink-light)' }}>
      <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.4 }}>{icon}</div>
      <p style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 16, letterSpacing: 2 }}>{text}</p>
    </div>
  )
}

export function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(2px)',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--paper-white)', border: '1px solid var(--paper-dark)',
        borderRadius: 6, boxShadow: '0 16px 48px rgba(0,0,0,0.15)',
        maxWidth: 520, width: '90%',
      }} onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

/** “我的资料”可导入的文档格式（FolderPicker 默认只列出这些文件） */
const MATERIAL_EXTS = ['.pdf', '.docx', '.txt', '.md', '.markdown']

interface PickEntry { name: string; path: string }

export function FolderPicker({ open, onClose, onPick, exts = MATERIAL_EXTS }: {
  open: boolean; onClose: () => void; onPick: (path: string) => void; exts?: string[];
}) {
  const [currentPath, setCurrentPath] = React.useState('')
  const [dirs, setDirs] = React.useState<PickEntry[]>([])
  const [files, setFiles] = React.useState<PickEntry[]>([])
  const [pickedFile, setPickedFile] = React.useState<PickEntry | null>(null)
  const [parentDir, setParentDir] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [inputPath, setInputPath] = React.useState('')

  const loadDirs = async (p: string) => {
    setLoading(true)
    try {
      const query = `path=${encodeURIComponent(p)}&files=1&exts=${encodeURIComponent(exts.join(','))}`
      const res = await fetch(`/api/v1/projects/list-dirs?${query}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '加载失败')
      setDirs(data.dirs || [])
      setFiles(data.files || [])
      setPickedFile(null)
      setParentDir(data.parent)
      setCurrentPath(p)
    } catch {
      setDirs([])
      setFiles([])
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    if (open) {
      setInputPath('')
      setDirs([])
      setFiles([])
      setPickedFile(null)
      setParentDir('')
      setCurrentPath('')
      loadDirs('')
    }
  }, [open, exts])

  if (!open) return null

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(2px)',
    }} onClick={onClose}>
      <div style={{
        width: 520, maxHeight: '70vh',
        background: 'var(--paper-white)', border: '1px solid var(--paper-dark)',
        borderRadius: 6, display: 'flex', flexDirection: 'column',
        boxShadow: '0 16px 48px rgba(0,0,0,0.15)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--paper-dark)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20, color: 'var(--ink-dark)' }}>
            选择文件夹或文件
          </span>
          <span onClick={onClose} style={{ cursor: 'pointer', fontSize: 18, color: 'var(--ink-light)', padding: '0 4px' }}>
            &times;
          </span>
        </div>

        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--paper-dark)' }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={inputPath} onChange={e => setInputPath(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') loadDirs(inputPath) }}
              placeholder="输入路径后回车"
              style={{
                flex: 1, padding: '8px 12px', fontSize: 13,
                fontFamily: "'Noto Serif SC', serif",
                border: '1px solid var(--paper-dark)', borderRadius: 3,
                background: 'rgba(255,255,255,0.5)', outline: 'none',
              }}
            />
            <button onClick={() => loadDirs(inputPath)} style={{
              padding: '8px 16px', fontSize: 13, cursor: 'pointer',
              background: 'var(--ink-black)', color: 'var(--paper-white)',
              border: 'none', borderRadius: 3, fontFamily: "'ZCOOL XiaoWei', serif",
            }}>
              跳转
            </button>
          </div>
          {currentPath && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--ink-light)', fontFamily: "'Noto Serif SC', serif" }}>
              当前：{currentPath}
            </div>
          )}
          {pickedFile && (
            <div style={{ marginTop: 4, fontSize: 12, color: 'var(--seal-red)', fontFamily: "'Noto Serif SC', serif", display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span>已选文件：{pickedFile.name}</span>
              {parentDir && (
                <span onClick={() => loadDirs(parentDir)} style={{ cursor: 'pointer', color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif", whiteSpace: 'nowrap' }}>
                  ← 返回上级目录
                </span>
              )}
            </div>
          )}
        </div>

        <div style={{ flex: 1, overflow: 'auto', minHeight: 200 }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-light)' }}>加载中...</div>
          ) : dirs.length === 0 && files.length === 0 && !currentPath ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--ink-light)', fontSize: 13 }}>
              输入路径并回车，或直接输入完整路径后点「选此目录/选此文件」
            </div>
          ) : (
            <div>
              {parentDir && (
                <div onClick={() => loadDirs(parentDir)} style={{
                  padding: '10px 20px', cursor: 'pointer', fontSize: 13,
                  fontFamily: "'Noto Serif SC', serif", color: 'var(--ink-medium)',
                  borderBottom: '1px solid rgba(0,0,0,0.04)',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <span style={{ opacity: 0.3 }}>&#128193;</span> ..
                </div>
              )}
              {dirs.map(d => (
                <div key={d.path} onClick={() => loadDirs(d.path)} style={{
                  padding: '10px 20px', cursor: 'pointer', fontSize: 13,
                  fontFamily: "'Noto Serif SC', serif", color: 'var(--ink-dark)',
                  borderBottom: '1px solid rgba(0,0,0,0.04)',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(194,58,43,0.04)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ opacity: 0.4 }}>&#128193;</span> {d.name}
                </div>
              ))}
              {files.length > 0 && (
                <>
                  <div style={{ padding: '8px 20px', fontSize: 11, color: 'var(--ink-light)', fontFamily: "'ZCOOL XiaoWei', serif", borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
                    可导入的文件（点击选择）
                  </div>
                  {files.map(f => {
                    const active = pickedFile?.path === f.path
                    return (
                      <div key={f.path} onClick={() => setPickedFile(prev => prev && prev.path === f.path ? null : f)} style={{
                        padding: '10px 20px', cursor: 'pointer', fontSize: 13,
                        fontFamily: "'Noto Serif SC', serif",
                        color: active ? 'var(--seal-red)' : 'var(--ink-dark)',
                        background: active ? 'rgba(194,58,43,0.05)' : 'transparent',
                        borderBottom: '1px solid rgba(0,0,0,0.04)',
                        display: 'flex', alignItems: 'center', gap: 8,
                      }}
                        onMouseEnter={e => e.currentTarget.style.background = active ? 'rgba(194,58,43,0.05)' : 'rgba(194,58,43,0.04)'}
                        onMouseLeave={e => e.currentTarget.style.background = active ? 'rgba(194,58,43,0.05)' : 'transparent'}
                      >
                        <span style={{ opacity: 0.5 }}>&#128196;</span> {f.name}
                      </div>
                    )
                  })}
                </>
              )}
              {currentPath && dirs.length === 0 && files.length === 0 && (
                <div style={{ padding: 30, textAlign: 'center', color: 'var(--ink-light)', fontSize: 13 }}>
                  此目录下无子文件夹或可导入文件
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{
          padding: '12px 20px', borderTop: '1px solid var(--paper-dark)',
          display: 'flex', justifyContent: 'flex-end', gap: 10,
        }}>
          <button onClick={onClose} style={{
            padding: '8px 20px', fontSize: 13, cursor: 'pointer',
            background: 'transparent', color: 'var(--ink-medium)',
            border: '1px solid var(--paper-dark)', borderRadius: 3,
            fontFamily: "'ZCOOL XiaoWei', serif",
          }}>
            取消
          </button>
          <button onClick={() => { onPick(pickedFile ? pickedFile.path : currentPath); onClose() }}
            disabled={!currentPath && !pickedFile}
            style={{
              padding: '8px 20px', fontSize: 13, cursor: currentPath || pickedFile ? 'pointer' : 'not-allowed',
              background: currentPath || pickedFile ? 'var(--ink-black)' : 'var(--ink-faint)',
              color: 'var(--paper-white)', border: 'none', borderRadius: 3,
              fontFamily: "'ZCOOL XiaoWei', serif", opacity: currentPath || pickedFile ? 1 : 0.5,
            }}>
            {pickedFile ? '选此文件' : '选此目录'}
          </button>
        </div>
      </div>
    </div>
  )
}

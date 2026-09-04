import type { CSSProperties } from 'react'

export interface RadarAxis { label: string; value: number }

function polyPoints(cx: number, cy: number, n: number, getR: (i: number) => number): string {
  const pts: string[] = []
  for (let i = 0; i < n; i++) {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n
    const r = getR(i)
    pts.push(`${(cx + r * Math.cos(ang)).toFixed(1)},${(cy + r * Math.sin(ang)).toFixed(1)}`)
  }
  return pts.join(' ')
}

/**
 * 纯 SVG 雷达图。value ∈ 0~100。
 * - 预留一圈“标注带宽”，避免左右轴的文字被 svg 裁掉；
 * - svg 允许 overflow 可见，字体略小，标签跨轴重叠概率低。
 */
export default function RadarChart({
  axes,
  size = 340,
  color = 'var(--seal-red)',
  style,
}: {
  axes: RadarAxis[]
  size?: number
  color?: string
  style?: CSSProperties
}) {
  const n = axes.length
  const LABEL_BAND = 42 // 给轴标签预留的外圈带宽
  const total = size
  const cx = total / 2
  const cy = total / 2 + 2
  const R = total / 2 - LABEL_BAND - 8 // 数据多边形半径
  if (n < 2) {
    return (
      <div style={{ color: 'var(--ink-faint)', fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 13, ...style }}>
        数据不足，无法绘制
      </div>
    )
  }

  const ring = (ratio: number) => polyPoints(cx, cy, n, () => R * ratio)
  const dataPoly = polyPoints(cx, cy, n, (i) => R * (Math.max(0, Math.min(100, axes[i].value)) / 100))

  const labelR = R + (LABEL_BAND - 14)
  type Anchor = 'middle' | 'start' | 'end'
  const labels: { x: number; y: number; anchor: Anchor; text: string }[] = []
  const vertexPts: { x: number; y: number; dot: number }[] = []
  for (let i = 0; i < n; i++) {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / n
    const cos = Math.cos(ang)
    const sin = Math.sin(ang)
    vertexPts.push({
      x: cx + R * cos,
      y: cy + R * sin,
      dot: Math.max(0, Math.min(100, axes[i].value)),
    })
    let anchor: Anchor = 'middle'
    if (cos > 0.35) anchor = 'start'
    else if (cos < -0.35) anchor = 'end'
    labels.push({
      x: cx + labelR * cos,
      y: cy + labelR * sin + 4,
      anchor,
      text: axes[i].label,
    })
  }

  return (
    <svg
      width={total}
      height={total + 6}
      viewBox={`0 0 ${total} ${total + 6}`}
      style={{ overflow: 'visible', ...style }}
      role="img"
    >
      {[0.25, 0.5, 0.75, 1].map((r) => (
        <polygon key={r} points={ring(r)} fill="none" stroke="var(--paper-dark)" strokeWidth="1" />
      ))}
      {vertexPts.map((p, i) => (
        <line key={`ax${i}`} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="var(--paper-dark)" strokeWidth="1" />
      ))}
      <polygon points={dataPoly} fill={color} fillOpacity="0.16" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      {vertexPts.map((p, i) => (
        <circle key={`v${i}`} cx={p.x} cy={p.y} r={4} fill={color} />
      ))}
      {labels.map((l, i) => (
        <text key={`l${i}`} x={l.x} y={l.y} textAnchor={l.anchor}
          style={{ fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12.5, fill: 'var(--ink-medium)' }}>
          {l.text}
        </text>
      ))}
    </svg>
  )
}

import { Routes, Route, NavLink } from 'react-router-dom'
import ProjectsPage from './pages/Projects'
import ResumesPage from './pages/Resumes'
import InterviewPage from './pages/Interview'
import ReportPage from './pages/Report'
import CramPage from './pages/Cram'
import SettingsPage from './pages/Settings'
import MbtiPage from './pages/Mbti'
import ResumeGenPage from './pages/ResumeGen'

const navItems = [
  { path: '/projects', label: '藏经阁', sub: '代码库 · 资料库' },
  { path: '/resumes', label: '拜帖', sub: '简历上传' },
  { path: '/interview', label: '论道', sub: '开始面试' },
  { path: '/report', label: '品鉴', sub: '面试报告' },
  { path: '/cram', label: '秘籍', sub: '八股文' },
  { path: '/mbti', label: '问心', sub: 'MBTI 职业测试' },
  { path: '/resume-gen', label: '挥毫', sub: 'AI 生成简历' },
  { path: '/settings', label: '设置', sub: '提供方 · 密钥' },
]

function InkDivider() {
  return (
    <svg width="100%" height="8" viewBox="0 0 400 8" preserveAspectRatio="none" style={{ display: 'block', margin: '8px 0' }}>
      <path d="M0,4 Q50,1 100,4 T200,4 T300,4 T400,4" stroke="var(--ink-faint)" strokeWidth="0.8" fill="none" opacity="0.5" />
    </svg>
  )
}

function SealStamp({ text }: { text: string }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: 56, height: 56, border: '2px solid var(--seal-red)',
      borderRadius: 4, color: 'var(--seal-red)',
      fontFamily: "'Ma Shan Zheng', cursive", fontSize: 18,
      transform: 'rotate(-8deg)', lineHeight: 1.1, textAlign: 'center',
      boxShadow: '0 0 0 1px rgba(194,58,43,0.1)',
    }}>
      {text}
    </div>
  )
}

export default function App() {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* 左侧导航 */}
      <aside style={{
        width: 220, minWidth: 220, display: 'flex', flexDirection: 'column',
        background: 'linear-gradient(180deg, var(--paper-cream) 0%, var(--paper-aged) 100%)',
        borderRight: '1px solid var(--paper-dark)',
        padding: '32px 0', position: 'relative', overflow: 'hidden',
      }}>
        {/* 背景水墨装饰 */}
        <div style={{
          position: 'absolute', top: 0, right: 0, width: 120, height: '100%',
          background: 'linear-gradient(270deg, rgba(180,170,150,0.2) 0%, transparent 100%)',
          pointerEvents: 'none',
        }} />

        <div style={{ textAlign: 'center', marginBottom: 24, padding: '0 16px', position: 'relative' }}>
          <SealStamp text="AI面试" />
          <h1 style={{
            fontFamily: "'Ma Shan Zheng', cursive", fontSize: 26,
            color: 'var(--ink-black)', marginTop: 12, letterSpacing: 4,
          }}>
            本地面试官
          </h1>
          <p style={{
            fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 12,
            color: 'var(--ink-light)', marginTop: 4, letterSpacing: 2,
          }}>
            以代码为卷，以AI为师
          </p>
        </div>

        <InkDivider />

        <nav style={{ flex: 1, padding: '8px 0' }}>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              style={({ isActive }) => ({
                display: 'block', padding: '14px 24px',
                textDecoration: 'none', color: isActive ? 'var(--ink-black)' : 'var(--ink-medium)',
                background: isActive ? 'rgba(194,58,43,0.06)' : 'transparent',
                borderRight: isActive ? '3px solid var(--seal-red)' : '3px solid transparent',
                transition: 'all 0.3s ease',
                position: 'relative',
              })}
            >
              <span style={{
                fontFamily: "'Ma Shan Zheng', cursive", fontSize: 20,
                display: 'block',
              }}>
                {item.label}
              </span>
              <span style={{
                fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 11,
                color: 'var(--ink-light)', marginTop: 2, display: 'block',
              }}>
                {item.sub}
              </span>
            </NavLink>
          ))}
        </nav>

        <div style={{ padding: '16px 24px', textAlign: 'center' }}>
          <InkDivider />
          <p style={{
            fontFamily: "'ZCOOL XiaoWei', serif", fontSize: 10,
            color: 'var(--ink-faint)', letterSpacing: 1, marginTop: 8,
          }}>
            离线运行 · 隐私无忧
          </p>
        </div>
      </aside>

      {/* 主内容区 */}
      <main style={{
        flex: 1, overflow: 'auto', position: 'relative',
        background: 'var(--paper-white)',
      }}>
        {/* 宣纸纹理 */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.03,
          backgroundImage: `url("data:image/svg+xml,%3Csvg width='100' height='100' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='f'%3E%3CfeTurbulence baseFrequency='0.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23f)'/%3E%3C/svg%3E")`,
        }} />

        <div style={{ padding: '40px 56px', maxWidth: 1480, margin: '0 auto', position: 'relative' }}>
          <Routes>
            <Route path="/" element={<NavigateToProjects />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/resumes" element={<ResumesPage />} />
            <Route path="/interview" element={<InterviewPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/cram" element={<CramPage />} />
            <Route path="/mbti" element={<MbtiPage />} />
            <Route path="/resume-gen" element={<ResumeGenPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

function NavigateToProjects() {
  if (window.location.pathname === '/') {
    window.location.replace('/projects')
  }
  return null
}

/**
 * LocalAI 面试官 · 桌面壳主进程（Electron）
 *
 * - 依赖：electron 装在 desktop/node_modules（项目内）。
 * - 缓存与运行时数据：userData 已指到 <项目根>/.desktop-userdata（项目内）。
 * - 行为：启动时若后端(8000)/前端(5173)未在跑则自动拉起，窗口就绪后加载前端；
 *   关闭窗口即退出，并把本进程拉起的子进程一并结束（Windows 下 taskkill /T 整树）。
 *   如果服务已由其它方式启动（如 python start.py），则直接附到现成端口，不重复拉起。
 *
 * - 自测钩子（不影响正常使用）：设 LOCALAI_SMOKE=1 启动时，页面加载完会截图到
 *   LOCALAI_SMOKE_OUT 并打印 SMOKE_OK/SMOKE_FAIL 后自动退出，供“跑测试确认没问题”。
 */
const { app, BrowserWindow, shell, dialog } = require('electron')
const { spawn, spawnSync } = require('child_process')
const net = require('net')
const path = require('path')
const fs = require('fs')

const SMOKE = process.env.LOCALAI_SMOKE === '1'
const SMOKE_OUT = process.env.LOCALAI_SMOKE_OUT

const ROOT = path.resolve(__dirname, '..')
const BACKEND_DIR = path.join(ROOT, 'backend')
const FRONTEND_DIR = path.join(ROOT, 'frontend')
const FRONT_URL = 'http://localhost:5173'

// 一切运行时数据都留在项目内：删除整个项目文件夹即可“删项目即干净”
app.setPath('userData', path.join(ROOT, '.desktop-userdata'))
app.setAppUserModelId('com.localai.interviewer')

const children = []
const killed = new Set()

function log(tag, msg) {
  console.log(`[${tag}] ${msg}`)
}

function probePort(port, host) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host })
    const done = (ok) => { s.destroy(); resolve(ok) }
    s.setTimeout(400)
    s.once('connect', () => done(true))
    s.once('timeout', () => done(false))
    s.once('error', () => done(false))
  })
}

// Vite 8 / Node 新版默认只绑 IPv6 回环（::1），老项目也可能只绑 IPv4 —— 双栈都探一遍
async function portUp(port) {
  return (await probePort(port, '127.0.0.1')) || (await probePort(port, '::1'))
}

async function waitForUp(port, ms = 45000) {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    if (await portUp(port)) return true
    await new Promise((r) => setTimeout(r, 700))
  }
  return false
}

function killTree(p) {
  if (!p || p.pid == null) return
  if (process.platform === 'win32') {
    if (!killed.has(p.pid)) {
      killed.add(p.pid)
      try {
        spawnSync('taskkill', ['/pid', String(p.pid), '/t', '/f'], { stdio: 'ignore' })
      } catch (_) { /* 尽力而为 */ }
    }
  } else {
    try { p.kill('SIGTERM') } catch (_) { /* 尽力而为 */ }
  }
}

function killChildren() {
  for (const p of children) killTree(p)
}

function spawnService(name, cmd, args, cwd, extraEnv = {}) {
  const p = spawn(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...extraEnv },
  })
  children.push(p)
  const onData = (buf) => String(buf).split('\n').forEach((l) => l.trim() && console.log(`[${name}] ${l}`))
  p.stdout?.on('data', onData)
  p.stderr?.on('data', onData)
  p.on('exit', (code) => log(name, `进程已退出 (code=${code})`))
  return p
}

async function ensureServices() {
  const needBackend = !(await portUp(8000))
  const needFront = !(await portUp(5173))

  if (needBackend) {
    const py = path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')
    log('backend', '后端未运行，正在拉起…')
    spawnService(
      'backend',
      py,
      ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000',
       '--reload', '--reload-dir', 'app'],
      BACKEND_DIR,
      { WATCHFILES_FORCE_POLLING: 'true' }, // 轮询兜底：改后端代码必然触发热重载
    )
  } else {
    log('backend', '后端已在运行（:8000），直接复用。')
  }

  if (needFront) {
    const vite = path.join(FRONTEND_DIR, 'node_modules', '.bin', 'vite.cmd')
    log('frontend', '前端未运行，正在拉起 Vite…')
    spawnService(
      'frontend',
      'cmd.exe',
      ['/c', vite, '--port', '5173', '--strictPort'],
      FRONTEND_DIR,
    )
  } else {
    log('frontend', '前端已在运行（:5173），直接复用。')
  }

  // 等“本进程拉起”的服务都真正就绪再开窗，避免页面先于后端出现导致首屏 API 失败
  if (needBackend) {
    const up = await waitForUp(8000)
    if (!up) throw new Error('后端服务 8000 迟迟未就绪，请查看上方日志')
  }
  if (needFront) {
    const up = await waitForUp(5173)
    if (!up) throw new Error('前端服务 5173 迟迟未就绪，请查看上方日志')
  }
}

function quitApp(code) {
  // 先结束本进程拉起的服务，再退出；app.quit() 虽会触发 before-quit，这里双保险
  killChildren()
  app.exit(code)
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    title: 'LocalAI 面试官',
    icon: path.join(__dirname, 'icon.ico'),
    backgroundColor: '#f4efe6',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  // 本应用窗口内的下载（简历等导出文件）默认保存到系统桌面
  win.webContents.session.on('will-download', (_event, item) => {
    try {
      item.setSavePath(path.join(app.getPath('desktop'), item.getFilename()))
    } catch (_) { /* 桌面不可用时退回默认下载目录 */ }
  })

  win.once('ready-to-show', () => win.show())
  win.webContents.on('did-fail-load', (e, code, desc, url) => {
    log('load', `页面加载失败 code=${code} desc=${desc} url=${url}`)
  })
  win.loadURL(FRONT_URL)
  // 页面里的外链一律交给系统浏览器，不在应用窗口里再开
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
  win.on('closed', () => app.quit())

  // ---- 自测模式：加载成功后截图存档并退出 ----
  if (SMOKE) {
    let smokeDone = false
    const runSmoke = () => {
      if (smokeDone) return
      smokeDone = true
      setTimeout(async () => {
        try {
          const img = await win.webContents.capturePage()
          let shot = ''
          if (SMOKE_OUT) {
            shot = path.resolve(SMOKE_OUT)
            fs.mkdirSync(path.dirname(shot), { recursive: true })
            fs.writeFileSync(shot, img.toPNG())
          }
          log('smoke', `SMOKE_OK title=${JSON.stringify(win.getTitle())} url=${win.webContents.getURL()}` + (shot ? ` shot=${shot}` : ''))
          quitApp(0)
        } catch (err) {
          log('smoke', `SMOKE_FAIL ${err && err.message || err}`)
          quitApp(1)
        }
      }, 2500)
    }
    win.webContents.on('did-finish-load', runSmoke)
  }

  return win
}

// 单实例：重复启动时聚焦已有窗口
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const [w] = BrowserWindow.getAllWindows()
    if (w) {
      if (w.isMinimized()) w.restore()
      w.focus()
    }
  })

  app.whenReady().then(async () => {
    try {
      await ensureServices()
      createWindow()
    } catch (err) {
      log('error', err.message)
      if (SMOKE) {
        quitApp(2)
      } else {
        dialog.showErrorBox('LocalAI 面试官启动失败', String(err && err.message || err))
        quitApp(1)
      }
    }
  })

  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', () => {
    // 只结束“本进程拉起”的子进程；复用的外部服务不动
    killChildren()
  })
}

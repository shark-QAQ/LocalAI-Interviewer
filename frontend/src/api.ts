const BASE = ''

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res.json()
}

export interface LlmKeyInfo { has_key: boolean; tail: string }
export interface LlmSettings {
  provider: 'ollama' | 'deepseek'
  deepseek_model: string
  deepseek_base_url: string
  deepseek_disable_thinking: boolean
  deepseek_api_key: LlmKeyInfo
  embedding: { provider: string; model: string }
  ollama_host?: string
  source?: string
}
export interface LlmTestResult {
  ok: boolean
  provider: string
  model?: string
  message: string
  latency_ms?: number
  snippet?: string
  models?: string[]
}

export interface MbtiQuestion {
  dim: string
  text: string
  opA: string
  opB: string
  poleA: string
  poleB: string
}
export interface MbtiAnswer { dim: string; pole: string }
export interface MbtiDimension {
  dim: string
  label: string
  left: string
  left_name: string
  left_pct: number
  right: string
  right_name: string
  right_pct: number
  pick: string
}
export interface MbtiIndustry { name: string; pct: number; why: string }
export interface MbtiResult {
  type: string
  type_full: string
  dimensions: MbtiDimension[]
  borderline: boolean
  summary: string
  industries: MbtiIndustry[]
}
export interface MbtiQuestionsResp {
  dimensions: { code: string; label: string; left: string; left_name: string; right: string; right_name: string }[]
  questions: MbtiQuestion[]
}

export interface ResumeTemplateResp {
  template_id: string
  fields: string[]
  file_name?: string
  mode?: 'placeholder' | 'sections' | 'builtin'
}
export interface ResumeBuiltinTemplate { key: string; name: string; accent: string; desc: string }
export interface ResumeGenTurn {
  session_id: string
  fields: Record<string, string>
  missing: string[]
  done: boolean
  question?: string
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  initProject: (project_name: string, code_path: string, force_rebuild = false) =>
    request<{ project_id: string; status: string; total_chunks: number }>('/api/v1/projects/init', {
      method: 'POST',
      body: JSON.stringify({ project_name, code_path, force_rebuild }),
    }),

  getProjectStatus: (id: string) =>
    request<{ project_id: string; index_status: string; chunk_count: number; last_indexed_at: string }>(
      `/api/v1/projects/${id}/status`
    ),

  listProjects: () => request<any[]>('/api/v1/projects'),

  renameProject: (id: string, name: string) =>
    request<any>(`/api/v1/projects/${id}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),

  deleteProject: (id: string) =>
    request<any>(`/api/v1/projects/${id}`, { method: 'DELETE' }),

  listDirs: (path: string, exts?: string[]) =>
    request<{ parent: string; dirs: { name: string; path: string }[]; files: { name: string; path: string }[] }>(
      `/api/v1/projects/list-dirs?path=${encodeURIComponent(path)}` +
      (exts && exts.length ? `&files=1&exts=${encodeURIComponent(exts.join(','))}` : '')
    ),

  searchKnowledge: (project_id: string, query: string, n_results = 5) =>
    request<{ project_id: string; results: {
      text: string; file_path: string; chunk_type: string; function_name: string;
      language: string; start_line: number | null; end_line: number | null; distance: number | null;
    }[] }>(`/api/v1/projects/${project_id}/search`, {
      method: 'POST',
      body: JSON.stringify({ query, n_results }),
    }),

  uploadResume: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/v1/resumes/upload', { method: 'POST', body: form })
    if (!res.ok) throw new Error('简历上传失败')
    return res.json() as Promise<{ resume_id: string; parsed_data: any }>
  },

  getResume: (id: string) => request<any>(`/api/v1/resumes/${id}`),

  getResumeCodeMapping: (id: string) =>
    request<{ projects: { name: string; status: string }[]; code_repos: string[] }>(
      `/api/v1/resumes/${id}/code-mapping`
    ),

  setResumeCodeMapping: (id: string, project_name: string, code_repo: string | null) =>
    request<any>(`/api/v1/resumes/${id}/code-mapping`, {
      method: 'POST',
      body: JSON.stringify({ project_name, code_repo }),
    }),

  listResumes: () => request<any[]>('/api/v1/resumes'),

  deleteResume: (id: string) =>
    request<any>(`/api/v1/resumes/${id}`, { method: 'DELETE' }),

  renameResume: (id: string, name: string) =>
    request<any>(`/api/v1/resumes/${id}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),

  listMaterials: () => request<any[]>('/api/v1/materials'),

  importMaterial: (path: string, name?: string) =>
    request<any>('/api/v1/materials/import', {
      method: 'POST',
      body: JSON.stringify({ path, name: name || '' }),
    }),

  renameMaterial: (id: string, name: string) =>
    request<any>(`/api/v1/materials/${id}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),

  deleteMaterial: (id: string) =>
    request<any>(`/api/v1/materials/${id}`, { method: 'DELETE' }),

  createSession: (resume_id: string, project_id: string, difficulty = 'mid', max_rounds = 8, projectIds: string[] = [], focus = 'balanced') =>
    request<{ session_id: string; status: string }>('/api/v1/interviews/sessions', {
      method: 'POST',
      body: JSON.stringify({ resume_id, project_id, project_ids: projectIds, difficulty, max_rounds, focus }),
    }),

  searchSessionKb: (session_id: string, query: string, n_results = 8) =>
    request<{ session_id: string; summary: string; results: {
      source: string; text: string; file_path: string; function_name: string; distance: number | null;
    }[] }>(`/api/v1/interviews/sessions/${session_id}/kb-search`, {
      method: 'POST',
      body: JSON.stringify({ query, n_results }),
    }),

  getReference: (session_id: string, round: number) =>
    request<{ round: number; reference: string }>(
      `/api/v1/interviews/sessions/${session_id}/reference`,
      { method: 'POST', body: JSON.stringify({ round }) }
    ),

  getReport: (session_id: string) =>
    request<any>(`/api/v1/interviews/sessions/${session_id}/report`),

  getSession: (session_id: string) =>
    request<any>(`/api/v1/interviews/sessions/${session_id}`),

  listInterviews: () =>
    request<any[]>(`/api/v1/interviews/sessions`),

  deleteInterview: (session_id: string) =>
    request<any>(`/api/v1/interviews/sessions/${session_id}`, { method: 'DELETE' }),

  getInterviewMessages: (session_id: string) =>
    request<any[]>(`/api/v1/interviews/sessions/${session_id}/messages`),

  generateCram: (project_id: string, resume_id?: string, focus_areas?: string[]) =>
    request<{ task_id: string; status: string }>('/api/v1/cram/generate', {
      method: 'POST',
      body: JSON.stringify({ project_id, resume_id, focus_areas }),
    }),

  getCramTask: (task_id: string) =>
    request<any>(`/api/v1/cram/tasks/${task_id}`),

  getLlmSettings: () =>
    request<LlmSettings>('/api/v1/llm/settings'),

  saveLlmSettings: (body: {
    provider?: 'ollama' | 'deepseek'
    deepseek_model?: string
    deepseek_base_url?: string
    deepseek_api_key?: string
    deepseek_disable_thinking?: boolean
  }) =>
    request<LlmSettings>('/api/v1/llm/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  testLlm: (body?: Record<string, string>) =>
    request<LlmTestResult>('/api/v1/llm/test', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),

  getMbtiQuestions: () =>
    request<MbtiQuestionsResp>('/api/v1/mbti/questions'),

  submitMbti: (answers: MbtiAnswer[]) =>
    request<MbtiResult>('/api/v1/mbti/result', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),

  getResumeTemplates: () =>
    request<{ templates: ResumeBuiltinTemplate[] }>('/api/v1/resume-gen/templates'),

  startResumeByTemplate: (body: { template_key: string; resume_id?: string }) =>
    request<ResumeGenTurn>('/api/v1/resume-gen/sessions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  saveResumeExampleToDesktop: () =>
    request<{ desktop: { filename: string; path: string } | null }>('/api/v1/resume-gen/example-template/to-desktop', {
      method: 'POST',
    }),

  uploadResumeTemplate: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/v1/resume-gen/upload-template', { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '模板上传失败' }))
      throw new Error(err.detail || '模板上传失败')
    }
    return res.json() as Promise<ResumeTemplateResp>
  },
  startResumeGen: (body: { template_id: string; resume_id?: string }) =>
    request<ResumeGenTurn>('/api/v1/resume-gen/sessions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  resumeGenChat: (id: string, message: string) =>
    request<ResumeGenTurn>(`/api/v1/resume-gen/sessions/${id}/chat`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  getResumeGenSession: (id: string) =>
    request<ResumeGenTurn & { status?: string }>(`/api/v1/resume-gen/sessions/${id}`),
  uploadResumePhoto: async (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`/api/v1/resume-gen/sessions/${id}/photo`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '照片上传失败' }))
      throw new Error(err.detail || '照片上传失败')
    }
    return res.json()
  },

  generateResume: (id: string) =>
    request<{ session_id: string; file_name: string; desktop?: { filename: string; path: string } | null }>(
      `/api/v1/resume-gen/sessions/${id}/generate`,
      { method: 'POST' }
    ),

  interactSse: async function* (session_id: string, user_answer: string | null) {
    const res = await fetch('/api/v1/interviews/sessions/' + session_id + '/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_answer }),
    })
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventType = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()!

      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          try {
            yield { event: eventType, data: JSON.parse(raw) }
          } catch {
            yield { event: eventType, data: { raw } }
          }
          eventType = ''
        }
      }
    }
  },
}

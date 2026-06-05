import axios from 'axios'
import { getToken, logout } from '../composables/useAuth'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      logout()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  },
)

export const sendChat = (sessionId, message, fields) =>
  api.post('/chat', { session_id: sessionId, message, fields })

export const patchSessionFields = (sessionId, fields) =>
  api.patch(`/session/${sessionId}/fields`, { fields })

export const fetchFieldDefinitions = () => api.get('/field-definitions')

// 核算单元（#7）：POST 让 AI 切分草稿，PATCH 保存用户确认后的单元
export const segmentUnits = (sessionId) =>
  api.post(`/session/${sessionId}/units`, {}, { timeout: 180000 })

export const saveUnits = (sessionId, units) =>
  api.patch(`/session/${sessionId}/units`, { accounting_units: units })

const CONFIRM_TIMEOUT_MS = 600000

export const confirmDiagnosis = (sessionId, fields) =>
  api.post('/confirm', { session_id: sessionId, fields }, { timeout: CONFIRM_TIMEOUT_MS })

export const getDiagnosis = (id) =>
  api.get(`/diagnose/${id}`)

export const listDiagnosesByBpm = (bpmId) =>
  api.get('/diagnose/by-bpm', { params: { bpm_id: bpmId } })

/** 填报溯源：确认字段 + 对话快照 */
export const getDiagnosisTraceability = (id) =>
  api.get(`/diagnose/${id}/traceability`)

/** 提交人工复核结论（规格 §7） */
export const submitReview = (diagnosisId, payload) =>
  api.post(`/diagnose/${diagnosisId}/review`, payload)

/** 查询某条诊断的全部复核记录 */
export const listReviews = (diagnosisId) =>
  api.get(`/diagnose/${diagnosisId}/reviews`)

export const getReportHtml = (id) =>
  `/api/report/${id}/html`

/**
 * 下载报告 PDF/HTML 副本：因为加了认证，直链 <a href> 不再可用，
 * 改成带 Authorization header 的 blob 下载。后端 WeasyPrint 缺失时返回 HTML。
 */
export async function downloadReportPdf(diagnosisId) {
  const res = await api.get(`/report/${diagnosisId}/pdf`, { responseType: 'blob' })
  const disposition = res.headers['content-disposition'] || ''
  const match = /filename=([^;]+)/.exec(disposition)
  const filename = match ? match[1].trim().replace(/^"|"$/g, '') : `report_${diagnosisId}.pdf`
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default api

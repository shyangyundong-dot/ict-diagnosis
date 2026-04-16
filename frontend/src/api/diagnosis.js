import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export const sendChat = (sessionId, message, fields) =>
  api.post('/chat', { session_id: sessionId, message, fields })

export const patchSessionFields = (sessionId, fields) =>
  api.patch(`/session/${sessionId}/fields`, { fields })

export const fetchFieldDefinitions = () => api.get('/field-definitions')

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

export const getReportPdf = (id) =>
  `/api/report/${id}/pdf`

export default api

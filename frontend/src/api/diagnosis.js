import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 长文本第二轮对话可能较慢，与后端 httpx 超时对齐
})

export const sendChat = (sessionId, message, fields) =>
  api.post('/chat', { session_id: sessionId, message, fields })

export const patchSessionFields = (sessionId, fields) =>
  api.patch(`/session/${sessionId}/fields`, { fields })

export const fetchFieldDefinitions = () => api.get('/field-definitions')

export const confirmDiagnosis = (sessionId, fields) =>
  api.post('/confirm', { session_id: sessionId, fields })

export const getDiagnosis = (id) =>
  api.get(`/diagnose/${id}`)

export const getReportHtml = (id) =>
  `/api/report/${id}/html`

export const getReportPdf = (id) =>
  `/api/report/${id}/pdf`

export default api

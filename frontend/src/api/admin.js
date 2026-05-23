import api from './diagnosis.js'

export const listLines = (includeInactive = true) =>
  api.get('/admin/lines', { params: { include_inactive: includeInactive } })

export const createLine = (name) => api.post('/admin/lines', { name })

export const updateLine = (id, payload) => api.patch(`/admin/lines/${id}`, payload)

export const listUsers = (includeInactive = true) =>
  api.get('/admin/users', { params: { include_inactive: includeInactive } })

export const getUser = (id) => api.get(`/admin/users/${id}`)

export const createUser = (payload) => api.post('/admin/users', payload)

export const updateUser = (id, payload) => api.patch(`/admin/users/${id}`, payload)

export const resetPassword = (id, newPassword) =>
  api.post(`/admin/users/${id}/reset-password`, { new_password: newPassword })

export const getUserActivity = (id) => api.get(`/admin/users/${id}/activity`)

export const listAudit = (params = {}) => api.get('/admin/audit', { params })

export const listLegacy = () => api.get('/admin/legacy')

export const claimLegacy = (diagnosisIds, targetUserId) =>
  api.post('/admin/legacy/claim', { diagnosis_ids: diagnosisIds, target_user_id: targetUserId })

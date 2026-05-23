import { reactive, readonly } from 'vue'
import axios from 'axios'

const TOKEN_KEY = 'ict_diagnosis_token'

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: null,
  loaded: false,
})

export function getToken() {
  return state.token
}

export async function loadUserFromToken() {
  if (state.loaded) return
  if (!state.token) {
    state.loaded = true
    return
  }
  try {
    const { data } = await axios.get('/api/me', {
      headers: { Authorization: `Bearer ${state.token}` },
    })
    state.user = data
  } catch (e) {
    state.token = ''
    state.user = null
    localStorage.removeItem(TOKEN_KEY)
  } finally {
    state.loaded = true
  }
}

export async function login(username, password) {
  const { data } = await axios.post('/api/auth/login', { username, password })
  state.token = data.token
  state.user = data.user
  localStorage.setItem(TOKEN_KEY, data.token)
  state.loaded = true
  return data
}

export function logout() {
  state.token = ''
  state.user = null
  localStorage.removeItem(TOKEN_KEY)
}

export function markPasswordChanged() {
  if (state.user) state.user.must_change_password = false
}

export function useAuth() {
  return {
    state: readonly(state),
    login,
    logout,
    loadUserFromToken,
    markPasswordChanged,
  }
}

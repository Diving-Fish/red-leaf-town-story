export function loginAsAdmin() {
  window.location.href = '/api/oauth/red-leaf-town/start?next=' + encodeURIComponent(window.location.pathname + window.location.search)
}

export function clearLegacyAdminToken() {
  localStorage.removeItem('red_leaf_town_admin_token')
}

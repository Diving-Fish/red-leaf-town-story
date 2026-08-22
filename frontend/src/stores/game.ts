import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError } from '@/api'
import type { AccountState, ActionResult, GameState } from '@/types'

export const useGameStore = defineStore('game', () => {
  const status = ref<'checking' | 'guest' | 'ready' | 'error'>('checking')
  const state = ref<GameState | null>(null)
  const account = ref<AccountState | null>(null)
  const busy = ref(false)
  const notice = ref('')
  const error = ref('')
  const serverOffsetMs = ref(0)

  const player = computed(() => state.value?.player || null)
  const inventoryMap = computed(() => {
    const result = new Map<string, GameState['inventory'][number]>()
    for (const item of state.value?.inventory || []) {
      const current = result.get(item.item_id)
      result.set(item.item_id, current ? { ...current, quantity: current.quantity + item.quantity } : item)
    }
    return result
  })

  function acceptState(nextState: GameState) {
    state.value = nextState
    serverOffsetMs.value = nextState.server_time * 1000 - Date.now()
    if (account.value) account.value.state = nextState
  }

  async function initialize() {
    status.value = 'checking'
    error.value = ''
    const params = new URLSearchParams(location.search)
    const oauthError = params.get('oauth_error')
    if (oauthError) {
      error.value = oauthError
      history.replaceState({}, '', `${location.pathname}${location.hash}`)
    }
    try {
      account.value = await api<AccountState>('/api/red-leaf-town/account')
      acceptState(account.value.state)
      status.value = 'ready'
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) status.value = 'guest'
      else {
        status.value = 'error'
        error.value = caught instanceof Error ? caught.message : '加载失败'
      }
    }
  }

  async function refresh(silent = false) {
    if (status.value !== 'ready' || busy.value) return
    try {
      const nextState = await api<GameState>('/api/red-leaf-town/state')
      acceptState(nextState)
    } catch (caught) {
      if (!silent) fail(caught)
    }
  }

  async function action(path: string, payload?: unknown, successMessage = '', method = 'POST') {
    if (busy.value) return
    busy.value = true
    error.value = ''
    try {
      const result = await api<ActionResult>(path, {
        method,
        body: payload === undefined ? undefined : JSON.stringify(payload),
      })
      acceptState(result.state)
      if (successMessage) showNotice(successMessage)
      return result.result
    } catch (caught) {
      fail(caught)
    } finally {
      busy.value = false
    }
  }

  function buy(shopId: string, quantity = 1) {
    return action('/api/red-leaf-town/shop/buy', { shop_id: shopId, quantity }, '种子已放入仓库')
  }

  function plant(slot: number, cropId: string) {
    return action(`/api/red-leaf-town/plots/${slot}/plant`, { crop_id: cropId }, '种子已经种下')
  }

  async function harvest(slot: number) {
    const result = await action(`/api/red-leaf-town/plots/${slot}/harvest`)
    if (result) showNotice(`收获了 ${result.quantity} 个${result.quality_name || ''}产物`)
    return result
  }

  function assignPartner(slot: number, partnerId: string | null) {
    return action(
      `/api/red-leaf-town/plots/${slot}/partners`,
      { partner_id: partnerId || '' },
      partnerId ? '伙伴已安排到这块土地' : '伙伴已撤下',
      'PUT',
    )
  }

  function assignGatheringPartner(siteId: string, partnerId: string | null) {
    return action(
      `/api/red-leaf-town/gathering/sites/${siteId}/partner`,
      { partner_id: partnerId || '' },
      partnerId ? '伙伴已前往采集点' : '伙伴已撤回',
      'PUT',
    )
  }

  function startGathering(siteId: string, taskId: string) {
    return action(
      `/api/red-leaf-town/gathering/sites/${siteId}/start`,
      { task_id: taskId },
      '伙伴已经出发采集',
    )
  }

  async function collectGathering(siteId: string) {
    const result = await action(`/api/red-leaf-town/gathering/sites/${siteId}/collect`)
    if (result) showNotice(`带回了 ${result.quantity} 个${result.quality_name || ''}采集物`)
    return result
  }

  function unlockTalent(nodeId: string) {
    return action(`/api/red-leaf-town/talents/${nodeId}/unlock`, undefined, '天赋已经点亮')
  }

  function sell(itemId: string, quantity: number, quality: number | null = null) {
    return action(`/api/red-leaf-town/inventory/${itemId}/sell`, { quantity, quality: quality || 0 }, '交易完成')
  }

  async function createBindingCode() {
    busy.value = true
    try {
      return await api<{ binding_code: string; command: string; expires_in: number }>(
        '/api/red-leaf-town/account/binding-code',
        { method: 'POST' },
      )
    } catch (caught) {
      fail(caught)
      return null
    } finally {
      busy.value = false
    }
  }

  async function logout() {
    await api<unknown>('/api/red-leaf-town/logout', { method: 'POST' }).catch(() => undefined)
    account.value = null
    state.value = null
    status.value = 'guest'
  }

  function effectiveNow() {
    return Math.floor((Date.now() + serverOffsetMs.value) / 1000)
  }

  function showNotice(message: string) {
    notice.value = message
    window.setTimeout(() => {
      if (notice.value === message) notice.value = ''
    }, 2800)
  }

  function fail(caught: unknown) {
    error.value = caught instanceof Error ? caught.message : '操作失败'
    showNotice(error.value)
  }

  return {
    status,
    state,
    account,
    player,
    inventoryMap,
    busy,
    notice,
    error,
    initialize,
    refresh,
    buy,
    plant,
    harvest,
    assignPartner,
    assignGatheringPartner,
    startGathering,
    collectGathering,
    unlockTalent,
    sell,
    createBindingCode,
    logout,
    effectiveNow,
    showNotice,
  }
})

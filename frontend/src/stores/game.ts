import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError } from '@/api'
import { PRODUCTION_COPY, type ProductionIndustry } from '@/lib/production'
import { qualityName } from '@/lib/quality'
import { useStoryStore } from '@/stores/story'
import { useTickerStore } from '@/stores/ticker'
import type { AccountState, ActionResult, GachaResult, GameState, Reward, TributeDeliveryResult } from '@/types'

export interface ProductionOutcome {
  quantity?: number
  quality?: number
  quality_name?: string
  drops?: Array<{
    item_id: string
    quantity: number
    quality: number
    quality_name: string
    item?: { name: string } | null
  }>
}

interface ActionOptions {
  payload?: unknown
  method?: string
  successMessage?: string
  cue?: string
}

const API_ROOT = '/api/red-leaf-town'

export const useGameStore = defineStore('game', () => {
  const ticker = useTickerStore()
  const story = useStoryStore()
  const status = ref<'checking' | 'guest' | 'ready' | 'error'>('checking')
  const state = ref<GameState | null>(null)
  const account = ref<AccountState | null>(null)
  const pending = ref(new Set<string>())
  const notice = ref('')
  const error = ref('')
  const serverOffsetMs = ref(0)
  let acceptedAt = 0

  const player = computed(() => state.value?.player || null)
  const busy = computed(() => pending.value.size > 0)
  const serverNow = computed(() => Math.floor((ticker.now + serverOffsetMs.value) / 1000))

  const inventoryMap = computed(() => {
    const result = new Map<string, GameState['inventory'][number]>()
    for (const item of state.value?.inventory || []) {
      const current = result.get(item.item_id)
      result.set(item.item_id, current ? { ...current, quantity: current.quantity + item.quantity } : item)
    }
    return result
  })

  const liveStamina = computed(() => {
    const current = player.value
    if (!current) return 0
    if (current.stamina >= current.stamina_cap) return current.stamina_cap
    const elapsed = Math.max(0, serverNow.value - current.stamina_updated_at)
    const gained = Math.floor(elapsed / current.stamina_restore_seconds)
    return Math.min(current.stamina_cap, current.stamina + gained)
  })

  const staminaNextIn = computed(() => {
    const current = player.value
    if (!current || liveStamina.value >= current.stamina_cap) return 0
    const elapsed = Math.max(0, serverNow.value - current.stamina_updated_at)
    return current.stamina_restore_seconds - (elapsed % current.stamina_restore_seconds)
  })

  const readyCounts = computed(() => {
    const snapshot = state.value
    const counts = { plots: 0, gathering: 0, mining: 0, crafting: 0, total: 0 }
    if (!snapshot) return counts
    counts.plots = snapshot.plots.filter((entry) => entry.ready).length
    counts.gathering = snapshot.gathering_sites.filter((entry) => entry.ready).length
    counts.mining = snapshot.mining_sites.filter((entry) => entry.ready).length
    counts.crafting = snapshot.crafting_stations.filter((entry) => entry.ready).length
    counts.total = counts.plots + counts.gathering + counts.mining + counts.crafting
    return counts
  })

  const nextReadyAt = computed(() => {
    const snapshot = state.value
    if (!snapshot) return 0
    const stamps: number[] = []
    for (const plot of snapshot.plots) {
      if (!plot.empty && !plot.ready && plot.ready_at) stamps.push(plot.ready_at)
    }
    const nodes = [...snapshot.gathering_sites, ...snapshot.mining_sites, ...snapshot.crafting_stations]
    for (const node of nodes) {
      if (!node.empty && !node.ready && node.task_snapshot) stamps.push(node.task_snapshot.ready_at)
    }
    return stamps.length ? Math.min(...stamps) : 0
  })

  // 剧情结算完的存档直接采用，伙伴加入之类的奖励不用等下一次轮询。
  story.bindState((settled) => {
    acceptState(settled.state, performance.now())
    const granted = (settled.result as { granted?: Reward | null }).granted
    const text = granted ? rewardText(granted) : ''
    if (text) showNotice(text)
  })

  function rewardText(reward: Reward) {
    const parts: string[] = []
    if (reward.coins) parts.push(`红叶币 ×${reward.coins}`)
    if (reward.experience) parts.push(`经验 ×${reward.experience}`)
    if (reward.talent_points) parts.push(`天赋点 ×${reward.talent_points}`)
    parts.push(...reward.items.map((item) => `${item.name} ×${item.quantity}`))
    parts.push(...reward.partners.map((partner) => `${partner.name} 加入`))
    return parts.length ? `获得 ${parts.join('、')}` : ''
  }

  function isPending(key: string) {
    return pending.value.has(key)
  }

  function isPendingPrefix(prefix: string) {
    for (const key of pending.value) {
      if (key.startsWith(prefix)) return true
    }
    return false
  }

  function acceptState(nextState: GameState, startedAt: number) {
    if (startedAt < acceptedAt) return
    acceptedAt = startedAt
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
      const startedAt = performance.now()
      account.value = await api<AccountState>(`${API_ROOT}/account`)
      acceptState(account.value.state, startedAt)
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
    if (status.value !== 'ready' || isPending('refresh')) return
    pending.value.add('refresh')
    try {
      const startedAt = performance.now()
      acceptState(await api<GameState>(`${API_ROOT}/state`), startedAt)
    } catch (caught) {
      if (!silent) fail(caught)
    } finally {
      pending.value.delete('refresh')
    }
  }

  async function action(key: string, path: string, options: ActionOptions = {}) {
    if (pending.value.has(key)) return undefined
    pending.value.add(key)
    error.value = ''
    const startedAt = performance.now()
    try {
      const result = await api<ActionResult>(path, {
        method: options.method || 'POST',
        body: options.payload === undefined ? undefined : JSON.stringify(options.payload),
      })
      acceptState(result.state, startedAt)
      if (options.successMessage) showNotice(options.successMessage)
      if (options.cue) story.cue(options.cue)
      return result.result
    } catch (caught) {
      fail(caught)
      return undefined
    } finally {
      pending.value.delete(key)
    }
  }

  function outcomeText(result: ProductionOutcome | undefined, verb: string, noun: string) {
    if (!result) return ''
    if (result.drops?.length) {
      const summary = result.drops
        .map((drop) => `${drop.quality_name || qualityName(drop.quality)}${drop.item?.name || drop.item_id}×${drop.quantity}`)
        .join('、')
      return `${verb}${summary}`
    }
    const quality = result.quality_name || qualityName(result.quality)
    return `${verb} ${result.quantity} 个${quality}${noun}`
  }

  function buy(shopId: string, quantity = 1) {
    return action(`shop:${shopId}:${quantity}`, `${API_ROOT}/shop/buy`, {
      payload: { shop_id: shopId, quantity },
      successMessage: '种子已放入仓库',
      cue: 'action:buy',
    })
  }

  function sell(itemId: string, quantity: number, quality: number | null = null) {
    return action(`inventory:${itemId}:${quality || 0}:${quantity}`, `${API_ROOT}/inventory/${itemId}/sell`, {
      payload: { quantity, quality: quality || 0 },
      successMessage: '交易完成',
      cue: 'action:sell',
    })
  }

  function plant(slot: number, cropId: string, taskItemId = '') {
    return action(`plot:${slot}:plant:${cropId}`, `${API_ROOT}/plots/${slot}/plant`, {
      payload: { crop_id: cropId, task_item_id: taskItemId },
      successMessage: '种子已经种下',
      cue: 'action:plant',
    })
  }

  async function harvest(slot: number) {
    const result = (await action(`plot:${slot}:harvest`, `${API_ROOT}/plots/${slot}/harvest`, {
      cue: 'action:harvest',
    })) as
      | ProductionOutcome
      | undefined
    if (result) showNotice(outcomeText(result, '收获了', '产物'))
    return result
  }

  function assignPartner(slot: number, partnerId: string | null) {
    return action(`plot:${slot}:partner`, `${API_ROOT}/plots/${slot}/partners`, {
      payload: { partner_id: partnerId || '' },
      method: 'PUT',
      successMessage: partnerId ? '伙伴已安排到这块土地' : '伙伴已撤下',
    })
  }

  function unlockTalent(nodeId: string) {
    return action(`talent:${nodeId}`, `${API_ROOT}/talents/${nodeId}/unlock`, {
      successMessage: '天赋已经点亮',
      cue: 'action:unlock_talent',
    })
  }

  async function deliverTribute(portalId: string, tributeId: string, quantity: number) {
    const result = (await action(
      `portal:${portalId}:${tributeId}`,
      `${API_ROOT}/portals/${portalId}/tributes/${tributeId}/deliver`,
      { payload: { quantity }, cue: 'action:deliver_tribute' },
    )) as TributeDeliveryResult | undefined
    if (!result) return undefined
    // 传送门开了是主线进度，让剧情层也有机会插话。
    if (result.portal_completed) story.cue('action:portal_complete')
    showNotice(deliveryText(result))
    return result
  }

  function deliveryText(result: TributeDeliveryResult) {
    if (result.portal_completed) return `${result.portal_name}开启了`
    if (result.tribute_completed) return '这一项贡品已经交齐'
    return `交付了 ${result.delivered} 个，还差 ${result.required - result.total_delivered} 个`
  }

  function productionBase(industry: ProductionIndustry, nodeId: string) {
    return `${API_ROOT}/${PRODUCTION_COPY[industry].endpoint}/${nodeId}`
  }

  function assignProductionPartner(industry: ProductionIndustry, nodeId: string, partnerId: string | null) {
    return action(`${industry}:${nodeId}:partner`, `${productionBase(industry, nodeId)}/partner`, {
      payload: { partner_id: partnerId || '' },
      method: 'PUT',
      successMessage: partnerId ? '伙伴已安排到岗位' : '伙伴已撤下',
    })
  }

  function startProduction(industry: ProductionIndustry, nodeId: string, taskId: string, taskItemId = '') {
    const copy = PRODUCTION_COPY[industry]
    return action(`${industry}:${nodeId}:start:${taskId}`, `${productionBase(industry, nodeId)}/start`, {
      payload: { [copy.startPayloadKey]: taskId, task_item_id: taskItemId },
      successMessage: '任务已经开始',
      cue: `action:start_${industry}`,
    })
  }

  async function collectProduction(industry: ProductionIndustry, nodeId: string) {
    const copy = PRODUCTION_COPY[industry]
    const result = (await action(`${industry}:${nodeId}:collect`, `${productionBase(industry, nodeId)}/collect`, {
      cue: `action:collect_${industry}`,
    })) as
      | ProductionOutcome
      | undefined
    if (result) showNotice(outcomeText(result, copy.collectVerb, copy.collectNoun))
    return result
  }

  function convertMapleFlame(quantity: number) {
    return action(`gacha:convert:${quantity}`, `${API_ROOT}/gacha/convert`, {
      payload: { quantity },
      successMessage: '引路枫叶已经点亮',
    })
  }

  async function recruit(count: 1 | 10, poolId: string) {
    const requestId = crypto.randomUUID()
    const result = await action(`gacha:pull:${requestId}`, `${API_ROOT}/gacha/pull`, {
      payload: { count, request_id: requestId, pool_id: poolId },
    })
    return result as unknown as GachaResult | undefined
  }

  function trainPartner(partnerId: string, itemId: string, quantity = 1) {
    return action(`partner:${partnerId}:train:${itemId}`, `${API_ROOT}/partners/${partnerId}/train`, {
      payload: { item_id: itemId, quantity },
      successMessage: '伙伴获得了经验',
    })
  }

  function starUpPartner(partnerId: string) {
    return action(`partner:${partnerId}:star-up`, `${API_ROOT}/partners/${partnerId}/star-up`, {
      successMessage: '伙伴升星完成',
    })
  }

  function breakthroughPartner(partnerId: string) {
    return action(`partner:${partnerId}:breakthrough`, `${API_ROOT}/partners/${partnerId}/breakthrough`, {
      successMessage: '伙伴突破完成',
    })
  }

  function useActiveTaskItem(industry: ProductionIndustry | 'farming', slotId: string | number, taskItemId: string) {
    return action(`${industry}:${slotId}:item:${taskItemId}`, `${API_ROOT}/tasks/use-item`, {
      payload: { industry, slot_id: String(slotId), task_item_id: taskItemId },
      successMessage: '特殊道具已经生效',
    })
  }

  async function createBindingCode() {
    if (isPending('binding-code')) return null
    pending.value.add('binding-code')
    try {
      return await api<{ binding_code: string; command: string; expires_in: number }>(
        `${API_ROOT}/account/binding-code`,
        { method: 'POST' },
      )
    } catch (caught) {
      fail(caught)
      return null
    } finally {
      pending.value.delete('binding-code')
    }
  }

  async function logout() {
    await api<unknown>(`${API_ROOT}/logout`, { method: 'POST' }).catch(() => undefined)
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
    pending,
    busy,
    notice,
    error,
    serverNow,
    liveStamina,
    staminaNextIn,
    readyCounts,
    nextReadyAt,
    isPending,
    isPendingPrefix,
    initialize,
    refresh,
    buy,
    sell,
    plant,
    harvest,
    assignPartner,
    unlockTalent,
    assignProductionPartner,
    startProduction,
    collectProduction,
    convertMapleFlame,
    recruit,
    trainPartner,
    starUpPartner,
    breakthroughPartner,
    useActiveTaskItem,
    deliverTribute,
    createBindingCode,
    logout,
    effectiveNow,
    showNotice,
  }
})

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Check, Search, Sparkles, TriangleAlert, UserRound, WandSparkles } from 'lucide-vue-next'

import { api } from '@/api'
import PartnerAvatar from '@/components/PartnerAvatar.vue'
import type { AdminPlayerSummary, AdminPartnerGrantResult, PartnerDefinition } from '@/types'

const props = defineProps<{
  adminToken: string
  partners: PartnerDefinition[]
}>()

const query = ref('')
const players = ref<AdminPlayerSummary[]>([])
const selectedPlayerId = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const deleteConfirmation = ref('')

const selectedPlayer = computed(() => players.value.find((player) => player.player_id === selectedPlayerId.value) || null)
const availablePartners = computed(() => props.partners.filter(
  (partner) => !selectedPlayer.value?.owned_partner_ids.includes(partner.id),
))
// 删号不可恢复，要求把角色名原样打一遍才放行。
const deletable = computed(() => Boolean(
  selectedPlayer.value && deleteConfirmation.value.trim() === selectedPlayer.value.display_name,
))

watch(selectedPlayerId, () => (deleteConfirmation.value = ''))

function headers() {
  return { 'X-Admin-Token': props.adminToken, 'Content-Type': 'application/json' }
}

function initialArtwork(partner: PartnerDefinition) {
  return partner.artworks.find((artwork) => artwork.breakthrough === 0)
}

function initialCrop(partner: PartnerDefinition) {
  return partner.avatar_crops.find((crop) => crop.breakthrough === 0)
}

async function searchPlayers() {
  busy.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ q: query.value.trim(), limit: '50' })
    players.value = await api<AdminPlayerSummary[]>(`/api/red-leaf-town/admin/players?${params}`, { headers: headers() })
    if (!players.value.some((player) => player.player_id === selectedPlayerId.value)) {
      selectedPlayerId.value = players.value[0]?.player_id || ''
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '玩家搜索失败'
  } finally {
    busy.value = false
  }
}

async function grantPartner(partnerId: string) {
  if (!selectedPlayer.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await api<AdminPartnerGrantResult>(
      `/api/red-leaf-town/admin/players/${encodeURIComponent(selectedPlayer.value.player_id)}/partners`,
      { method: 'POST', headers: headers(), body: JSON.stringify({ partner_id: partnerId }) },
    )
    const index = players.value.findIndex((player) => player.player_id === result.player.player_id)
    if (index >= 0) players.value[index] = result.player
    flash('伙伴已发放，玩家刷新后即可查看')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '发放失败'
  } finally {
    busy.value = false
  }
}

async function deletePlayer() {
  if (!selectedPlayer.value || !deletable.value || busy.value) return
  const target = selectedPlayer.value
  busy.value = true
  error.value = ''
  try {
    await api(`/api/red-leaf-town/admin/players/${encodeURIComponent(target.player_id)}`, {
      method: 'DELETE',
      headers: headers(),
    })
    players.value = players.value.filter((player) => player.player_id !== target.player_id)
    selectedPlayerId.value = players.value[0]?.player_id || ''
    deleteConfirmation.value = ''
    flash(`${target.display_name} 的存档已删除，该账号再次登录会重新建号`)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '删除失败'
  } finally {
    busy.value = false
  }
}

function flash(message: string) {
  notice.value = message
  window.setTimeout(() => (notice.value = ''), 2600)
}

onMounted(searchPlayers)
</script>

<template>
  <section class="grant-panel">
    <header>
      <div><p>PLAYER DELIVERY</p><h1>玩家存档管理</h1><span>搜索玩家，发放其尚未持有的伙伴，或删除整个角色存档。</span></div>
      <form @submit.prevent="searchPlayers"><Search :size="16" /><input v-model="query" placeholder="玩家名称或 Player ID" /><button :disabled="busy">搜索</button></form>
    </header>
    <p v-if="error" class="grant-error">{{ error }}</p>
    <p v-if="notice" class="grant-notice"><Check :size="15" />{{ notice }}</p>

    <div class="grant-layout">
      <aside class="player-results">
        <small>搜索结果 · {{ players.length }}</small>
        <button v-for="player in players" :key="player.player_id" :class="{ active: selectedPlayerId === player.player_id }" @click="selectedPlayerId = player.player_id">
          <span><UserRound :size="17" /></span><div><strong>{{ player.display_name }}</strong><small>Lv.{{ player.level }} · {{ player.player_id.slice(0, 8) }}</small></div><i>{{ player.owned_partner_ids.length }}</i>
        </button>
        <div v-if="!players.length" class="no-players">没有找到玩家</div>
      </aside>

      <main v-if="selectedPlayer" class="grant-workspace">
        <div class="selected-player">
          <span><UserRound :size="24" /></span><div><small>当前玩家</small><h2>{{ selectedPlayer.display_name }}</h2><code>{{ selectedPlayer.player_id }}</code></div>
        </div>

        <section class="owned-section">
          <h3>已经持有</h3>
          <div v-if="selectedPlayer.owned_partner_ids.length" class="owned-chips">
            <span v-for="partnerId in selectedPlayer.owned_partner_ids" :key="partnerId"><Check :size="12" />{{ partners.find((partner) => partner.id === partnerId)?.name || partnerId }}</span>
          </div>
          <p v-else>该玩家还没有伙伴。</p>
        </section>

        <section class="available-section">
          <h3>可发放伙伴</h3>
          <div v-if="availablePartners.length" class="grant-partner-grid">
            <article v-for="partner in availablePartners" :key="partner.id">
              <PartnerAvatar class="grant-avatar" :artwork="initialArtwork(partner)" :crop="initialCrop(partner)" :name="partner.name" :size="44">
                <Sparkles :size="20" />
              </PartnerAvatar>
              <div><strong>{{ partner.name }}</strong><small>{{ partner.rarity }} 星 · {{ partner.id }}</small></div>
              <button :disabled="busy" @click="grantPartner(partner.id)"><WandSparkles :size="14" />发放</button>
            </article>
          </div>
          <div v-else class="all-owned"><Check :size="28" /><strong>没有可发放的伙伴</strong><span>该玩家已经持有目录中的全部伙伴。</span></div>
        </section>

        <section class="danger-section">
          <h3><TriangleAlert :size="14" />删除角色</h3>
          <p>存档、伙伴、进行中的任务和 QQ 绑定会一起清掉，无法恢复。该水鱼账号再次登录会当作新居民重新建号，开局剧情也会重新播放。</p>
          <div class="danger-actions">
            <input v-model="deleteConfirmation" :placeholder="`输入 ${selectedPlayer.display_name} 以确认`" />
            <button :disabled="!deletable || busy" @click="deletePlayer">永久删除</button>
          </div>
        </section>
      </main>
      <div v-else class="select-player-placeholder"><UserRound :size="38" /><span>请先选择玩家</span></div>
    </div>
  </section>
</template>

<style scoped>
.grant-panel { padding: 34px clamp(20px, 4vw, 54px) 70px; }.grant-panel > header { display: flex; align-items: end; justify-content: space-between; gap: 25px; margin-bottom: 25px; }.grant-panel header p { margin: 0; color: #d17149; font-size: 12px; font-weight: 800; letter-spacing: .2em; }.grant-panel header h1 { margin: 5px 0; font: 700 30px Georgia, 'Noto Serif SC', serif; }.grant-panel header span { color: #7f8c82; font-size: 12px; }.grant-panel form { width: min(410px, 100%); height: 42px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; padding-left: 12px; border: 1px solid #ffffff16; border-radius: 10px; background: #111914; }.grant-panel form svg { color: #78857b; }.grant-panel form input { min-width: 0; color: #eee9dd; border: 0; outline: 0; background: transparent; }.grant-panel form button { align-self: stretch; padding: 0 15px; color: #172016; font-weight: 800; border: 0; border-radius: 0 9px 9px 0; background: #a8c985; cursor: pointer; }
.grant-error,.grant-notice { display: flex; align-items: center; gap: 6px; padding: 10px 13px; border-radius: 9px; font-size: 12px; }.grant-error { color: #efa08f; border: 1px solid #dc806d33; background: #dc806d0d; }.grant-notice { color: #acd08b; border: 1px solid #91b67333; background: #91b6730d; }
.grant-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 14px; align-items: start; }.player-results { min-height: 430px; padding: 13px; border: 1px solid #ffffff10; border-radius: 17px 6px; background: #141e18; }.player-results > small { display: block; margin: 3px 6px 11px; color: #6f7b73; font-size: 12px; }.player-results > button { width: 100%; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 9px; padding: 9px; margin-top: 4px; text-align: left; color: #cbd2c8; border: 1px solid transparent; border-radius: 10px; background: transparent; cursor: pointer; }.player-results > button.active { border-color: #98b97833; background: #98b97811; }.player-results > button > span { width: 36px; height: 36px; display: grid; place-items: center; color: #9fbd84; border-radius: 11px 4px; background: #243128; }.player-results strong,.player-results button small { display: block; }.player-results button small { margin-top: 3px; color: #6f7c73; font-size: 12px; }.player-results button i { min-width: 21px; padding: 3px; color: #d5ae63; text-align: center; font-size: 12px; font-style: normal; border-radius: 99px; background: #d5ae6311; }.no-players { padding: 50px 10px; color: #667269; text-align: center; font-size: 12px; }
.grant-workspace { min-width: 0; padding: 22px; border: 1px solid #ffffff10; border-radius: 20px 7px; background: #17211b; }.selected-player { display: flex; align-items: center; gap: 12px; padding-bottom: 18px; border-bottom: 1px solid #ffffff0e; }.selected-player > span { width: 48px; height: 48px; display: grid; place-items: center; color: #b4ce99; border-radius: 15px 5px; background: #29382d; }.selected-player small,.selected-player code { display: block; color: #6e7b72; font-size: 12px; }.selected-player h2 { margin: 2px 0; font-size: 18px; }.owned-section,.available-section { margin-top: 22px; }.owned-section h3,.available-section h3 { margin: 0 0 10px; font-size: 12px; }.owned-section > p { color: #748077; font-size: 12px; }.owned-chips { display: flex; flex-wrap: wrap; gap: 6px; }.owned-chips span { display: flex; align-items: center; gap: 4px; padding: 6px 9px; color: #a9c88e; font-size: 12px; border-radius: 99px; background: #8fb26f12; }
.danger-section { margin-top: 26px; padding: 15px; border: 1px solid #dc806d2e; border-radius: 12px; background: #dc806d08; }.danger-section h3 { display: flex; align-items: center; gap: 5px; margin: 0 0 8px; color: #e79c88; font-size: 12px; }.danger-section > p { margin: 0 0 11px; color: #98867f; font-size: 12px; line-height: 1.65; }.danger-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }.danger-actions input { min-width: 0; height: 34px; padding: 0 11px; color: #eee9dd; font-size: 12px; border: 1px solid #ffffff16; border-radius: 8px; outline: 0; background: #111914; }.danger-actions button { min-height: 34px; padding: 0 14px; color: #2a1512; font-size: 12px; font-weight: 800; border: 0; border-radius: 8px; background: #dc9382; cursor: pointer; }.danger-actions button:disabled { color: #7e6b66; background: #dc806d24; cursor: not-allowed; }
.grant-partner-grid { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 8px; }.grant-partner-grid article { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; padding: 10px; border: 1px solid #ffffff0e; border-radius: 12px; background: #101813; }.grant-avatar { color: #9ebd82; }.grant-partner-grid strong,.grant-partner-grid small { display: block; }.grant-partner-grid small { margin-top: 3px; color: #6d7970; font-size: 12px; }.grant-partner-grid button { min-height: 33px; display: flex; align-items: center; gap: 5px; padding: 0 10px; color: #172016; font-size: 12px; font-weight: 800; border: 0; border-radius: 8px; background: #a8c985; cursor: pointer; }.all-owned,.select-player-placeholder { min-height: 250px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: #69756c; }.all-owned strong { color: #9eaa9f; }.all-owned span { font-size: 12px; }.select-player-placeholder { min-height: 430px; border: 1px dashed #ffffff10; border-radius: 20px; font-size: 12px; }
@media (max-width: 850px) { .grant-panel > header { align-items: start; flex-direction: column; }.grant-layout { grid-template-columns: 1fr; }.player-results { min-height: 0; max-height: 260px; overflow: auto; }.grant-partner-grid { grid-template-columns: 1fr; } }
</style>

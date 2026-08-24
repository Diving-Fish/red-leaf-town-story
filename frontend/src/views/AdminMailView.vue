<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Check, LockKeyhole, Mail, Megaphone, Plus, Search, Send, Trash2, UserRound, X } from 'lucide-vue-next'

import { api, ApiError } from '@/api'
import type { AdminMailEntry, AdminPlayerSummary, ItemDefinition, MailScope } from '@/types'

interface MailCatalogPartner {
  partner_id: string
  name: string
  rarity: number
}

interface AdminMailPayload {
  scope: MailScope
  entries: AdminMailEntry[]
  items: ItemDefinition[]
  partners: MailCatalogPartner[]
}

interface DraftItem {
  item_id: string
  quantity: number
  quality: number
}

const TOKEN_KEY = 'red_leaf_town_admin_token'
const token = ref(localStorage.getItem(TOKEN_KEY) || '')
const tokenInput = ref(token.value)
const authenticated = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const scope = ref<MailScope>('global')
const entries = ref<AdminMailEntry[]>([])
const items = ref<ItemDefinition[]>([])
const partners = ref<MailCatalogPartner[]>([])

const title = ref('')
const sender = ref('镇长')
const body = ref('')
const registeredBefore = ref(localInput(Date.now()))
const expiresAt = ref('')
const coins = ref<number | null>(null)
const experience = ref<number | null>(null)
const mapleFlame = ref<number | null>(null)
const guideLeaves = ref<number | null>(null)
const talentPoints = ref<number | null>(null)
const draftItems = ref<DraftItem[]>([])
const draftPartnerIds = ref<string[]>([])

const query = ref('')
const players = ref<AdminPlayerSummary[]>([])
const recipientId = ref('')

const recipient = computed(() => players.value.find((player) => player.player_id === recipientId.value) || null)
const attachmentCount = computed(() => (
  [coins.value, experience.value, mapleFlame.value, guideLeaves.value, talentPoints.value].filter(Boolean).length
  + draftItems.value.length
  + draftPartnerIds.value.length
))
const sendable = computed(() => Boolean(
  title.value.trim() && sender.value.trim() && body.value.trim()
  && (scope.value === 'global' ? registeredBefore.value : recipientId.value),
))

watch(scope, () => {
  entries.value = []
  if (authenticated.value) refresh()
})
watch(recipientId, () => {
  if (authenticated.value && scope.value === 'player') refresh()
})

function headers(): Record<string, string> {
  return { 'X-Admin-Token': token.value, 'Content-Type': 'application/json' }
}

function localInput(milliseconds: number) {
  const date = new Date(milliseconds - new Date().getTimezoneOffset() * 60_000)
  return date.toISOString().slice(0, 16)
}

function toSeconds(value: string) {
  return value ? Math.floor(new Date(value).getTime() / 1000) : 0
}

function stamp(seconds: number) {
  if (!seconds) return '不过期'
  const date = new Date(seconds * 1000)
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function itemName(itemId: string) {
  return items.value.find((item) => item.id === itemId)?.name || itemId
}

function hasQuality(itemId: string) {
  return Boolean(items.value.find((item) => item.id === itemId)?.has_quality)
}

async function unlock() {
  token.value = tokenInput.value.trim()
  error.value = ''
  try {
    await refresh()
    localStorage.setItem(TOKEN_KEY, token.value)
    authenticated.value = true
  } catch (caught) {
    error.value = caught instanceof ApiError && caught.status === 403 ? 'Token 不正确' : '后台连接失败'
  }
}

async function refresh() {
  if (scope.value === 'player' && !recipientId.value) {
    entries.value = []
    return
  }
  const params = new URLSearchParams({ scope: scope.value, player_id: recipientId.value })
  const payload = await api<AdminMailPayload>(`/api/red-leaf-town/admin/mail?${params}`, { headers: headers() })
  entries.value = payload.entries
  items.value = payload.items
  partners.value = payload.partners
}

async function searchPlayers() {
  busy.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ q: query.value.trim(), limit: '50' })
    players.value = await api<AdminPlayerSummary[]>(`/api/red-leaf-town/admin/players?${params}`, { headers: headers() })
    if (!players.value.some((player) => player.player_id === recipientId.value)) recipientId.value = ''
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '玩家搜索失败'
  } finally {
    busy.value = false
  }
}

function addDraftItem() {
  const first = items.value[0]
  if (first) draftItems.value.push({ item_id: first.id, quantity: 1, quality: 0 })
}

function attachments() {
  return {
    coins: coins.value || 0,
    experience: experience.value || 0,
    maple_flame: mapleFlame.value || 0,
    guide_leaves: guideLeaves.value || 0,
    talent_points: talentPoints.value || 0,
    items: draftItems.value.map((entry) => ({
      item_id: entry.item_id,
      quantity: entry.quantity,
      quality: hasQuality(entry.item_id) ? entry.quality : 0,
    })),
    partner_ids: draftPartnerIds.value,
  }
}

async function send() {
  if (!sendable.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api<unknown>('/api/red-leaf-town/admin/mail', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({
        scope: scope.value,
        recipient_id: scope.value === 'player' ? recipientId.value : '',
        registered_before: scope.value === 'global' ? toSeconds(registeredBefore.value) : 0,
        title: title.value.trim(),
        sender: sender.value.trim(),
        body: body.value.trim(),
        expires_at: toSeconds(expiresAt.value),
        attachments: attachments(),
      }),
    })
    notice.value = scope.value === 'global' ? '公告已投递到全镇信箱' : `已寄给 ${recipient.value?.display_name || '收件人'}`
    title.value = ''
    body.value = ''
    coins.value = null
    experience.value = null
    mapleFlame.value = null
    guideLeaves.value = null
    talentPoints.value = null
    draftItems.value = []
    draftPartnerIds.value = []
    await refresh()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '投递失败'
  } finally {
    busy.value = false
  }
}

async function withdraw(entry: AdminMailEntry) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ recipient_id: entry.recipient_id })
    await api<unknown>(`/api/red-leaf-town/admin/mail/${entry.mail_id}?${params}`, {
      method: 'DELETE',
      headers: headers(),
    })
    notice.value = `已撤回《${entry.title}》`
    await refresh()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '撤回失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="admin-page">
    <section v-if="!authenticated" class="unlock-card">
      <div class="admin-seal"><LockKeyhole :size="34" /></div>
      <p class="kicker">RED LEAF TOWN ADMIN</p>
      <h1>镇邮局</h1>
      <p>请输入管理员 Token。凭据只保存在当前浏览器。</p>
      <form @submit.prevent="unlock">
        <input v-model="tokenInput" type="password" autocomplete="current-password" placeholder="Admin Token" />
        <button type="submit">进入后台</button>
      </form>
      <span v-if="error" class="form-error">{{ error }}</span>
      <a href="/red-leaf-town/"><ArrowLeft :size="15" />返回红叶镇</a>
    </section>

    <template v-else>
      <header class="admin-header">
        <div class="brand"><span><Mail :size="22" /></span><div><strong>红叶镇后台</strong><small>镇邮局</small></div></div>
        <nav class="admin-links">
          <RouterLink :to="{ name: 'admin-crops' }">作物数值</RouterLink>
          <RouterLink :to="{ name: 'admin-partners' }">伙伴管理</RouterLink>
          <RouterLink :to="{ name: 'admin-story' }">剧情素材</RouterLink>
        </nav>
        <div class="header-actions">
          <span v-if="notice" class="notice"><Check :size="15" />{{ notice }}</span>
          <a href="/red-leaf-town/"><ArrowLeft :size="16" />玩家前台</a>
        </div>
      </header>

      <div class="admin-body">
        <p v-if="error" class="editor-error">{{ error }}</p>

        <div class="mail-workbench">
          <section class="compose-card">
            <div class="scope-switch" role="tablist">
              <button role="tab" :aria-selected="scope === 'global'" :class="{ active: scope === 'global' }" @click="scope = 'global'">
                <Megaphone :size="16" />全服邮件
              </button>
              <button role="tab" :aria-selected="scope === 'player'" :class="{ active: scope === 'player' }" @click="scope = 'player'">
                <UserRound :size="16" />个人邮件
              </button>
            </div>

            <p class="scope-note">
              {{ scope === 'global'
                ? '只有在截止时刻之前注册的居民会收到这封信，之后的新居民看不到。'
                : '这封信只投进一个人的信箱，其他人看不到。' }}
            </p>

            <div v-if="scope === 'player'" class="recipient-picker">
              <form class="search-row" @submit.prevent="searchPlayers">
                <input v-model="query" placeholder="按角色名或编号搜索收件人" />
                <button type="submit" :disabled="busy"><Search :size="15" />搜索</button>
              </form>
              <div v-if="players.length" class="player-list">
                <button
                  v-for="player in players"
                  :key="player.player_id"
                  :class="{ active: player.player_id === recipientId }"
                  @click="recipientId = player.player_id"
                >
                  <b>{{ player.display_name }}</b><small>Lv.{{ player.level }} · {{ player.player_id.slice(0, 8) }}</small>
                </button>
              </div>
              <p v-else class="hint">先搜索并选中一位居民。</p>
            </div>

            <div class="field-grid">
              <label class="wide"><span>标题</span><input v-model="title" maxlength="60" placeholder="例如：红叶镇邮局开张" /></label>
              <label><span>发件人</span><input v-model="sender" maxlength="30" placeholder="镇长" /></label>
              <label v-if="scope === 'global'"><span>注册截止时刻</span><input v-model="registeredBefore" type="datetime-local" /></label>
              <label><span>过期时间（留空则永不过期）</span><input v-model="expiresAt" type="datetime-local" /></label>
            </div>

            <label class="body-field">
              <span>正文</span>
              <textarea v-model="body" rows="7" maxlength="4000" placeholder="信里想说的话。换行会原样保留。" />
              <small>{{ body.length }} / 4000</small>
            </label>

            <div class="attachment-block">
              <div class="attachment-heading"><strong>附件</strong><small>{{ attachmentCount }} 项 · 收件人一次性整封领取</small></div>
              <div class="field-grid currency-grid">
                <label><span>红叶币</span><input v-model.number="coins" type="number" min="0" placeholder="0" /></label>
                <label><span>经验</span><input v-model.number="experience" type="number" min="0" placeholder="0" /></label>
                <label><span>枫火</span><input v-model.number="mapleFlame" type="number" min="0" placeholder="0" /></label>
                <label><span>引路枫叶</span><input v-model.number="guideLeaves" type="number" min="0" placeholder="0" /></label>
                <label><span>天赋点</span><input v-model.number="talentPoints" type="number" min="0" placeholder="0" /></label>
              </div>

              <div v-for="(entry, index) in draftItems" :key="index" class="item-row">
                <select v-model="entry.item_id">
                  <option v-for="item in items" :key="item.id" :value="item.id">{{ item.name }}</option>
                </select>
                <input v-model.number="entry.quantity" type="number" min="1" max="9999" />
                <select v-if="hasQuality(entry.item_id)" v-model.number="entry.quality">
                  <option :value="0">默认品质</option>
                  <option v-for="level in [1, 2, 3, 4, 5]" :key="level" :value="level">品质 {{ level }}</option>
                </select>
                <span v-else class="no-quality">无品质</span>
                <button class="row-remove" aria-label="移除附件" @click="draftItems.splice(index, 1)"><X :size="15" /></button>
              </div>
              <button class="add-row" :disabled="draftItems.length >= 8 || !items.length" @click="addDraftItem">
                <Plus :size="15" />添加物品附件
              </button>

              <div v-if="partners.length" class="partner-picker">
                <small>随信赠送伙伴（已拥有的收件人不会重复获得）</small>
                <div>
                  <label v-for="partner in partners" :key="partner.partner_id">
                    <input v-model="draftPartnerIds" type="checkbox" :value="partner.partner_id" />
                    <span>{{ partner.name }} · {{ partner.rarity }}★</span>
                  </label>
                </div>
              </div>
            </div>

            <button class="send-button" :disabled="!sendable || busy" @click="send">
              <Send :size="16" />{{ busy ? '投递中' : '投递这封信' }}
            </button>
          </section>

          <aside class="sent-card">
            <header>
              <div><small>ALREADY IN THE POST BOX</small><h2>信箱里的信</h2></div>
              <span>{{ entries.length }} 封</span>
            </header>
            <p v-if="scope === 'player' && !recipientId" class="hint">选中一位居民后可以看到寄给他的信。</p>
            <p v-else-if="!entries.length" class="hint">这个信箱还是空的。</p>
            <article v-for="entry in entries" :key="entry.mail_id" class="sent-letter">
              <div>
                <b>{{ entry.title }}</b>
                <small>{{ entry.sender }} · {{ stamp(entry.created_at) }}</small>
                <small v-if="entry.scope === 'global'">投给 {{ stamp(entry.registered_before) }} 前注册的居民</small>
                <small v-else>寄给 {{ entry.recipient_name || entry.recipient_id.slice(0, 8) }}</small>
                <small>失效：{{ stamp(entry.expires_at) }}</small>
                <p v-if="!entry.attachments.empty" class="sent-attachments">
                  附件：
                  <template v-if="entry.attachments.coins">红叶币 ×{{ entry.attachments.coins }} </template>
                  <template v-if="entry.attachments.experience">经验 ×{{ entry.attachments.experience }} </template>
                  <template v-if="entry.attachments.maple_flame">枫火 ×{{ entry.attachments.maple_flame }} </template>
                  <template v-if="entry.attachments.guide_leaves">引路枫叶 ×{{ entry.attachments.guide_leaves }} </template>
                  <template v-if="entry.attachments.talent_points">天赋点 ×{{ entry.attachments.talent_points }} </template>
                  <template v-for="item in entry.attachments.items" :key="item.item_id">{{ itemName(item.item_id) }} ×{{ item.quantity }} </template>
                  <template v-for="partner in entry.attachments.partners" :key="partner.partner_id">{{ partner.name }} </template>
                </p>
              </div>
              <button class="row-remove" aria-label="撤回" :disabled="busy" @click="withdraw(entry)"><Trash2 :size="15" /></button>
            </article>
          </aside>
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.admin-page { min-height: 100vh; color: #eee8db; background: radial-gradient(circle at 85% 0, #783d2922, transparent 28%), #0d1410; }
.unlock-card { width: min(430px, calc(100% - 32px)); margin: 0 auto; padding-top: 16vh; text-align: center; }
.admin-seal { width: 70px; height: 70px; display: grid; place-items: center; margin: auto; color: #d4a95b; border: 1px solid #d4a95b66; border-radius: 22px 7px; }
.kicker { margin: 24px 0 8px; color: #78857b; font-size: 11px; letter-spacing: .22em; }
.unlock-card h1 { margin: 0; font-size: 30px; }
.unlock-card > p:not(.kicker) { color: #879188; }
.unlock-card form { display: flex; gap: 8px; margin: 28px 0 12px; }
.unlock-card input { flex: 1; }
.unlock-card button { padding: 0 20px; color: #172016; font-weight: 800; border: 0; border-radius: 9px; background: #aacb88; }
.unlock-card > a { display: inline-flex; align-items: center; gap: 5px; margin-top: 18px; color: #879188; font-size: 13px; }

.admin-header { min-height: 72px; position: sticky; top: 0; z-index: 10; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 18px; padding: 10px 28px; border-bottom: 1px solid #ffffff12; background: #0e1611ef; backdrop-filter: blur(16px); }
.brand { display: flex; align-items: center; gap: 11px; }
.brand > span { width: 39px; height: 39px; display: grid; place-items: center; color: #d5ad60; border: 1px solid #d5ad6044; border-radius: 13px 4px; }
.brand strong,.brand small { display: block; }
.brand small { color: #778278; font-size: 12px; margin-top: 2px; }
.admin-links { display: flex; gap: 5px; padding: 4px; border: 1px solid #ffffff10; border-radius: 11px; background: #080d0a55; }
.admin-links a { padding: 8px 12px; color: #8f9a91; font-size: 12px; border-radius: 7px; }
.admin-links a:hover { color: #e8e6dc; background: #ffffff0e; }
.header-actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
.header-actions a { min-height: 37px; display: inline-flex; align-items: center; gap: 7px; padding: 0 13px; color: #a8b2a8; border: 1px solid #ffffff14; border-radius: 9px; }
.notice { display: flex; align-items: center; gap: 5px; color: #aacb88; font-size: 12px; }

.admin-body { width: min(1400px, 100%); margin: 0 auto; padding: 28px clamp(16px, 4vw, 54px) 90px; }
.editor-error,.form-error { display: block; padding: 10px 12px; color: #efad9d; font-size: 13px; border: 1px solid #d36f5733; border-radius: 9px; background: #d36f570d; }
.editor-error { margin-bottom: 18px; }
.mail-workbench { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr); gap: 18px; align-items: start; }
.compose-card,.sent-card { padding: 20px; border: 1px solid #ffffff12; border-radius: 20px 7px 20px 7px; background: #131b16; }

.scope-switch { display: flex; gap: 5px; padding: 4px; border: 1px solid #ffffff10; border-radius: 12px; background: #0a100c; }
.scope-switch button { flex: 1; min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; color: #8e9a90; border: 0; border-radius: 8px; background: transparent; cursor: pointer; }
.scope-switch button.active { color: #1a2318; font-weight: 700; background: #d5ad60; }
.scope-note { margin: 12px 0 16px; color: #7f8a80; font-size: 12px; line-height: 1.7; }

.recipient-picker { margin-bottom: 16px; padding: 13px; border: 1px solid #ffffff0e; border-radius: 12px; background: #0d1310; }
.search-row { display: flex; gap: 8px; }
.search-row input { flex: 1; }
.search-row button { display: inline-flex; align-items: center; gap: 5px; padding: 0 14px; color: #1a2318; font-weight: 700; border: 0; border-radius: 8px; background: #aacb88; cursor: pointer; }
.player-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; margin-top: 10px; max-height: 180px; overflow: auto; }
.player-list button { padding: 9px 11px; text-align: left; color: #a4aea5; border: 1px solid #ffffff0e; border-radius: 9px; background: #ffffff04; cursor: pointer; }
.player-list button.active { color: #eee8db; border-color: #d5ad6055; background: #d5ad600f; }
.player-list b,.player-list small { display: block; }
.player-list small { margin-top: 2px; color: #78837a; font-size: 11px; }
.hint { margin: 10px 0 0; color: #78837a; font-size: 12px; }

.field-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.currency-grid { grid-template-columns: repeat(auto-fit, minmax(122px, 1fr)); }
label { display: grid; gap: 5px; }
label.wide { grid-column: 1 / -1; }
label > span { color: #7f8a80; font-size: 12px; }
input, select, textarea { min-height: 38px; padding: 8px 11px; color: #eee8db; border: 1px solid #ffffff14; border-radius: 9px; background: #0b100d; font: inherit; }
input:focus, select:focus, textarea:focus { outline: 1px solid #d5ad6066; }
textarea { resize: vertical; line-height: 1.8; }
.body-field { margin-top: 14px; }
.body-field small { justify-self: end; color: #6f7a72; }

.attachment-block { margin-top: 18px; padding: 15px; border: 1px dashed #ffffff18; border-radius: 13px; background: #0d1310; }
.attachment-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.attachment-heading small { color: #78837a; }
.item-row { display: grid; grid-template-columns: minmax(0, 1fr) 92px 132px auto; align-items: center; gap: 8px; margin-top: 8px; }
.no-quality { color: #6f7a72; font-size: 12px; text-align: center; }
.row-remove { width: 34px; height: 34px; display: grid; place-items: center; color: #cf8c80; border: 1px solid #cf8c8026; border-radius: 8px; background: #cf8c800a; cursor: pointer; }
.add-row { display: inline-flex; align-items: center; gap: 6px; margin-top: 10px; padding: 8px 13px; color: #a4aea5; border: 1px dashed #ffffff1e; border-radius: 8px; background: transparent; cursor: pointer; }
.partner-picker { margin-top: 14px; padding-top: 12px; border-top: 1px solid #ffffff0e; }
.partner-picker > small { color: #78837a; }
.partner-picker > div { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; }
.partner-picker label { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; color: #a4aea5; font-size: 12px; border: 1px solid #ffffff12; border-radius: 99px; background: #ffffff04; cursor: pointer; }
.partner-picker input { min-height: 0; }

.send-button { width: 100%; min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 18px; color: #182116; font-weight: 800; border: 0; border-radius: 10px; background: #aacb88; cursor: pointer; }
.send-button:disabled { opacity: .42; cursor: not-allowed; }

.sent-card > header { display: flex; align-items: end; justify-content: space-between; gap: 12px; padding-bottom: 13px; margin-bottom: 12px; border-bottom: 1px solid #ffffff0e; }
.sent-card small { color: #78837a; }
.sent-card h2 { margin: 4px 0 0; font: 700 19px Georgia, 'Noto Serif SC', serif; }
.sent-card > header > span { color: #78837a; font-size: 12px; }
.sent-letter { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 10px; padding: 12px; margin-bottom: 8px; border: 1px solid #ffffff0e; border-radius: 11px 4px 11px 4px; background: #ffffff04; }
.sent-letter b { display: block; margin-bottom: 5px; }
.sent-letter small { display: block; margin-top: 2px; font-size: 11px; }
.sent-attachments { margin: 8px 0 0; color: #b9a465; font-size: 11px; line-height: 1.7; }

@media (max-width: 1000px) {
  .mail-workbench { grid-template-columns: 1fr; }
  .admin-header { grid-template-columns: 1fr auto; row-gap: 10px; }
  .admin-links { grid-column: 1 / -1; order: 3; overflow: auto; }
}
@media (max-width: 620px) {
  .admin-header { padding: 10px 15px; }
  .admin-body { padding: 20px 15px 70px; }
  .item-row { grid-template-columns: minmax(0, 1fr) 74px auto; }
  .item-row select:last-of-type,.no-quality { grid-column: 1 / -1; }
}
</style>

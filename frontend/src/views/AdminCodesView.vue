<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Check, ClipboardCopy, Download, LockKeyhole, RefreshCw, Ticket } from 'lucide-vue-next'

import { api, ApiError } from '@/api'
import { loginAsAdmin, clearLegacyAdminToken } from '@/composables/adminAuth'

interface CodeRecord {
  code: string
  kind: string
  batch: string
  note: string
  created_at: number
  redeemed_by: string
  redeemed_at: number
  redeemed_by_name: string
}

clearLegacyAdminToken()
const MAX_BATCH = 500

const authenticated = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const count = ref(10)
const batch = ref('')
const note = ref('')
const generated = ref<string[]>([])
const records = ref<CodeRecord[]>([])
const filter = ref<'all' | 'open' | 'spent'>('all')

const generatedText = computed(() => generated.value.join('\n'))
const spent = computed(() => records.value.filter((entry) => entry.redeemed_by).length)
const visible = computed(() => {
  if (filter.value === 'open') return records.value.filter((entry) => !entry.redeemed_by)
  if (filter.value === 'spent') return records.value.filter((entry) => entry.redeemed_by)
  return records.value
})
const canGenerate = computed(() => count.value >= 1 && count.value <= MAX_BATCH)

function headers(): Record<string, string> {
  return { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' }
}

function stamp(seconds: number) {
  if (!seconds) return '—'
  const date = new Date(seconds * 1000)
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

async function unlock() {

  error.value = ''
  try {
    await refresh()

    authenticated.value = true
  } catch (caught) {
    error.value = caught instanceof ApiError && caught.status === 403 ? '当前账号没有管理员权限' : '后台连接失败'
  }
}

async function refresh() {
  records.value = await api<CodeRecord[]>('/api/red-leaf-town/admin/redemption-codes?limit=500', {
    headers: headers(),
  })
}

async function generate() {
  if (!canGenerate.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await api<{ codes: string[]; count: number }>('/api/red-leaf-town/admin/redemption-codes', {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({ count: count.value, batch: batch.value.trim(), note: note.value.trim() }),
    })
    generated.value = result.codes
    notice.value = `已生成 ${result.count} 个激活码`
    await refresh()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '生成失败'
  } finally {
    busy.value = false
  }
}

async function copyGenerated() {
  if (!generated.value.length) return
  try {
    await navigator.clipboard.writeText(generatedText.value)
    notice.value = `已复制 ${generated.value.length} 个激活码`
  } catch {
    error.value = '浏览器不允许复制，请手动全选文本框'
  }
}

function downloadGenerated() {
  if (!generated.value.length) return
  const blob = new Blob([`${generatedText.value}\n`], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `red-leaf-town-codes-${batch.value.trim() || Date.now()}.txt`
  link.click()
  URL.revokeObjectURL(url)
}
onMounted(unlock)
</script>

<template>
  <main class="admin-page">
    <section v-if="!authenticated" class="unlock-card">
      <div class="admin-seal"><LockKeyhole :size="34" /></div>
      <p class="kicker">RED LEAF TOWN ADMIN</p>
      <h1>激活码</h1>
      <p>请使用已获得管理员权限的水鱼账号登录。</p>
      <form @submit.prevent="loginAsAdmin">
        <button type="submit">水鱼账号登录</button>
      </form>
      <span v-if="error" class="form-error">{{ error }}</span>
      <a href="/red-leaf-town/"><ArrowLeft :size="15" />返回红叶镇</a>
    </section>

    <template v-else>
      <header class="admin-header">
        <div class="brand"><span><Ticket :size="22" /></span><div><strong>红叶镇后台</strong><small>月卡激活码</small></div></div>
        <nav class="admin-links">
          <RouterLink :to="{ name: 'admin-crops' }">作物数值</RouterLink>
          <RouterLink :to="{ name: 'admin-partners' }">伙伴管理</RouterLink>
          <RouterLink :to="{ name: 'admin-mail' }">镇邮局</RouterLink>
          <RouterLink :to="{ name: 'admin-story' }">剧情素材</RouterLink>
        </nav>
        <div class="header-actions">
          <span v-if="notice" class="notice"><Check :size="15" />{{ notice }}</span>
          <a href="/red-leaf-town/"><ArrowLeft :size="16" />玩家前台</a>
        </div>
      </header>

      <div class="admin-body">
        <span v-if="error" class="editor-error">{{ error }}</span>

        <div class="codes-workbench">
          <section class="issue-card">
            <h2>批量生成</h2>
            <p class="hint">每个激活码续 30 天月卡，兑换时到账 300 枫火。一码只能用一次。</p>

            <div class="field-grid">
              <label>
                <span>生成数量</span>
                <input v-model.number="count" type="number" min="1" :max="MAX_BATCH" />
              </label>
              <label>
                <span>批次名</span>
                <input v-model="batch" placeholder="留空按时间自动命名" maxlength="40" />
              </label>
              <label class="wide">
                <span>备注</span>
                <input v-model="note" placeholder="发放渠道、活动名等，仅后台可见" maxlength="120" />
              </label>
            </div>

            <button class="issue-button" :disabled="!canGenerate || busy" @click="generate">
              生成 {{ count }} 个激活码
            </button>

            <div v-if="generated.length" class="issue-output">
              <div class="output-heading">
                <strong>{{ generated.length }} 个激活码</strong>
                <div class="output-actions">
                  <button @click="copyGenerated"><ClipboardCopy :size="14" />复制全部</button>
                  <button @click="downloadGenerated"><Download :size="14" />下载 txt</button>
                </div>
              </div>
              <textarea :value="generatedText" readonly rows="10" spellcheck="false"></textarea>
              <p class="hint">这批码只在本次生成后显示一次，请先复制保存。下方列表随时可以查到码本身和兑换状态。</p>
            </div>
          </section>

          <section class="ledger-card">
            <div class="ledger-heading">
              <div>
                <h2>激活码总览</h2>
                <small>共 {{ records.length }} 个，已兑换 {{ spent }} 个</small>
              </div>
              <button class="ghost-button" :disabled="busy" @click="refresh"><RefreshCw :size="14" />刷新</button>
            </div>

            <div class="filter-switch">
              <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
              <button :class="{ active: filter === 'open' }" @click="filter = 'open'">未兑换</button>
              <button :class="{ active: filter === 'spent' }" @click="filter = 'spent'">已兑换</button>
            </div>

            <p v-if="!visible.length" class="hint">这里还没有激活码。</p>
            <ul v-else class="ledger-list">
              <li v-for="entry in visible" :key="entry.code" :class="{ spent: Boolean(entry.redeemed_by) }">
                <code>{{ entry.code }}</code>
                <span class="ledger-batch">{{ entry.batch || '—' }}</span>
                <span class="ledger-state">
                  <template v-if="entry.redeemed_by">{{ entry.redeemed_by_name || entry.redeemed_by }} · {{ stamp(entry.redeemed_at) }}</template>
                  <template v-else>未兑换</template>
                </span>
              </li>
            </ul>
          </section>
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

.codes-workbench { display: grid; grid-template-columns: minmax(0, 1fr) minmax(340px, .85fr); gap: 18px; align-items: start; }
.issue-card,.ledger-card { padding: 20px; border: 1px solid #ffffff12; border-radius: 20px 7px 20px 7px; background: #131b16; }
h2 { margin: 0 0 6px; font-size: 17px; }
.hint { margin: 0 0 14px; color: #78837a; font-size: 12px; line-height: 1.7; }
.field-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
label { display: grid; gap: 5px; }
label.wide { grid-column: 1 / -1; }
label > span { color: #7f8a80; font-size: 12px; }
input, textarea { min-height: 38px; padding: 8px 11px; color: #eee8db; border: 1px solid #ffffff14; border-radius: 9px; background: #0b100d; font: inherit; }
input:focus, textarea:focus { outline: 1px solid #d5ad6066; }

.issue-button { width: 100%; min-height: 44px; margin-top: 16px; color: #1a2318; font-weight: 800; border: 0; border-radius: 10px; background: #d5ad60; cursor: pointer; }
.issue-button:disabled { opacity: .45; cursor: default; }

.issue-output { margin-top: 18px; padding-top: 16px; border-top: 1px solid #ffffff0e; }
.output-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.output-actions { display: flex; gap: 7px; }
.output-actions button { display: inline-flex; align-items: center; gap: 5px; padding: 7px 11px; color: #a4aea5; font-size: 12px; border: 1px solid #ffffff14; border-radius: 8px; background: #ffffff05; cursor: pointer; }
.output-actions button:hover { color: #eee8db; background: #ffffff0d; }
.issue-output textarea { width: 100%; font: 13px/1.9 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .05em; resize: vertical; }
.issue-output .hint { margin: 10px 0 0; }

.ledger-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.ledger-heading h2 { margin: 0; }
.ledger-heading small { color: #78837a; font-size: 12px; }
.ghost-button { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; color: #a4aea5; font-size: 12px; border: 1px solid #ffffff14; border-radius: 8px; background: transparent; cursor: pointer; }
.filter-switch { display: flex; gap: 5px; padding: 4px; margin-bottom: 12px; border: 1px solid #ffffff10; border-radius: 11px; background: #0a100c; }
.filter-switch button { flex: 1; min-height: 34px; color: #8e9a90; font-size: 12px; border: 0; border-radius: 8px; background: transparent; cursor: pointer; }
.filter-switch button.active { color: #1a2318; font-weight: 700; background: #d5ad60; }

.ledger-list { display: grid; gap: 5px; max-height: 560px; overflow: auto; margin: 0; padding: 0; list-style: none; }
.ledger-list li { display: grid; grid-template-columns: minmax(0, auto) minmax(0, 1fr); gap: 2px 10px; padding: 9px 11px; border: 1px solid #ffffff0e; border-radius: 9px; background: #ffffff04; }
.ledger-list li.spent { opacity: .62; }
.ledger-list code { color: #eee8db; font: 700 13px ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .05em; }
.ledger-list li.spent code { text-decoration: line-through; }
.ledger-batch { justify-self: end; color: #78837a; font-size: 11px; }
.ledger-state { grid-column: 1 / -1; color: #8f9a91; font-size: 11px; }
.ledger-list li:not(.spent) .ledger-state { color: #aacb88; }

@media (max-width: 1000px) {
  .codes-workbench { grid-template-columns: 1fr; }
  .admin-header { grid-template-columns: 1fr; gap: 10px; }
  .header-actions { justify-content: flex-start; }
}
</style>

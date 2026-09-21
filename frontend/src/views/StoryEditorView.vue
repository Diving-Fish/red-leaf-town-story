<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowLeft, ChevronLeft, ChevronRight, ChevronRight as ChevronIn, Copy, Download, FileText,
  Image as ImageIcon, Leaf, List, MessageSquare, Monitor, Play, Plus, Redo2, Trash2, Undo2, Upload, UserSquare2, X,
} from 'lucide-vue-next'

import { ApiError, api } from '@/api'
import StoryOverlay from '@/components/story/StoryOverlay.vue'
import StoryStage from '@/components/story/StoryStage.vue'
import StepInspector from '@/components/story-editor/StepInspector.vue'
import { foldStage } from '@/lib/story-stage'
import {
  createDraft, createStep, draftFromExample, hasBackground, hydrate, ID_PATTERN, indexResources,
  MAX_STEPS, MAX_TEXT, parseScriptFile, stepAsset, STEP_LABELS, toScriptFile,
  type DraftStep, type DraftStepType, type StoryDraft,
} from '@/lib/story-draft'
import { useHistory } from '@/composables/useHistory'
import { useStoryStore } from '@/stores/story'
import type { StoryResources, StoryScript } from '@/types'

const SLOT_NAMES: Record<string, string> = { left: '左侧', center: '居中', right: '右侧' }
const DRAFTS_KEY = 'red_leaf_town_story_drafts'
const ACTIVE_KEY = 'red_leaf_town_story_draft_key'

const story = useStoryStore()
const history = useHistory<StoryDraft>(createDraft())
const draft = history.state

const drafts = ref<Record<string, StoryDraft>>({})
const activeKey = ref('')
const selected = ref(0)
const resources = ref<StoryResources>({ assets: [], partners: [], uploads: [], upload: null as never, example: null })
const loadError = ref('')
const status = ref<'checking' | 'guest' | 'ready'>('checking')
const narrow = ref(false)
const notice = ref('')
const shareUrl = ref('')
const sharing = ref(false)
const sheet = ref<'' | 'meta' | 'drafts'>('')
const dragFrom = ref(-1)
const dragOver = ref(-1)
const fileInput = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLElement | null>(null)

const catalog = computed(() => indexResources(resources.value))
const quota = computed(() => resources.value.upload || null)
const loginUrl = `/api/oauth/red-leaf-town/start?next=${encodeURIComponent('/red-leaf-town/story-editor')}`
const steps = computed(() => draft.value.steps)
const hydrated = computed(() => hydrate(steps.value, catalog.value))
const stage = computed(() => foldStage(hydrated.value, selected.value + 1, 'stage'))
const current = computed<DraftStep | null>(() => steps.value[selected.value] || null)
const speakers = computed(() => [
  ...new Set(steps.value.flatMap((step) => (step.type === 'dialogue' && step.speaker ? [step.speaker] : []))),
])

const problems = computed(() => {
  const found: string[] = []
  const entry = draft.value
  if (!ID_PATTERN.test(entry.id)) found.push('剧本 ID 需以小写字母开头，仅可使用小写字母、数字、下划线和减号')
  if (!entry.title.trim()) found.push('剧本缺少标题')
  if (!steps.value.some((step) => step.type === 'dialogue')) found.push('剧本需要至少一句对话')
  if (!hasBackground(steps.value)) found.push('剧本需要至少一个已选图的背景步骤，否则将退回插话模式')
  if (steps.value.length > MAX_STEPS) found.push(`步骤数上限 ${MAX_STEPS}，当前 ${steps.value.length} 步`)
  steps.value.forEach((step, position) => {
    const at = `第 ${position + 1} 步`
    if (step.type === 'dialogue') {
      if (!step.text.trim()) found.push(`${at}：台词为空`)
      else if (step.text.length > MAX_TEXT) found.push(`${at}：台词超过 ${MAX_TEXT} 字`)
      return
    }
    if (step.type === 'portrait' && step.visible && !stepAsset(step, catalog.value)) {
      found.push(`${at}：立绘未选择图片`)
    }
  })
  return found
})

/* ---------- 步骤操作 ---------- */

function patch(label: string, changes: Record<string, unknown>) {
  const position = selected.value
  history.mutate(`${label}#${position}`, (entry) => {
    entry.steps[position] = { ...entry.steps[position], ...changes } as DraftStep
  })
}

function add(type: DraftStepType) {
  const at = steps.value.length ? selected.value + 1 : 0
  history.mutate(`add-${Date.now()}`, (entry) => {
    entry.steps.splice(at, 0, createStep(type))
  })
  select(at)
}

function duplicate() {
  if (!current.value) return
  const at = selected.value
  history.mutate(`dup-${Date.now()}`, (entry) => {
    entry.steps.splice(at + 1, 0, JSON.parse(JSON.stringify(entry.steps[at])))
  })
  select(at + 1)
}

function remove(position = selected.value) {
  if (steps.value.length <= 1) return
  history.mutate(`del-${Date.now()}`, (entry) => {
    entry.steps.splice(position, 1)
  })
  select(Math.min(position, draft.value.steps.length - 1))
}

function move(from: number, to: number) {
  if (from === to || from < 0 || to < 0) return
  history.mutate(`move-${Date.now()}`, (entry) => {
    const [moved] = entry.steps.splice(from, 1)
    entry.steps.splice(to, 0, moved)
  })
  select(to)
}

function select(position: number) {
  selected.value = Math.max(0, Math.min(position, steps.value.length - 1))
  scrollRowIntoView()
}

// 撤销、重做和删除都可能让步数变少，选中项统一在这里收敛，不用每个调用点各写一遍。
watch(() => steps.value.length, (count) => {
  if (selected.value > count - 1) selected.value = Math.max(0, count - 1)
})

function scrollRowIntoView() {
  requestAnimationFrame(() => {
    listRef.value?.querySelector('.op-row.is-active')?.scrollIntoView({ block: 'nearest' })
  })
}

function setField(label: string, changes: Partial<StoryDraft>) {
  history.mutate(label, (entry) => Object.assign(entry, changes))
}

/* ---------- 行摘要 ---------- */

function rowIcon(step: DraftStep) {
  if (step.type === 'dialogue') return MessageSquare
  return step.type === 'background' ? ImageIcon : UserSquare2
}

function rowSummary(step: DraftStep) {
  if (step.type === 'background') {
    const asset = stepAsset(step, catalog.value)
    return step.asset_id ? `切换背景 · ${asset?.name || step.asset_id}` : '移除背景'
  }
  if (step.type === 'portrait') {
    const side = SLOT_NAMES[step.slot] || '左侧'
    if (!step.visible) return `${side}立绘退场`
    const asset = stepAsset(step, catalog.value)
    return `${side} · ${asset?.name || step.asset_id || step.partner_id || '未选择图片'}`
  }
  return ''
}

/* ---------- 预览 ---------- */

function playFull() {
  if (!steps.value.some((step) => step.type === 'dialogue')) return
  const script: StoryScript = {
    id: 'story-editor-preview',
    title: draft.value.title,
    mode: 'stage',
    priority: 0,
    repeatable: true,
    trigger_description: '',
    rewards: { coins: 0, experience: 0, talent_points: 0, maple_flame: 0, guide_leaves: 0, items: [], partners: [], empty: true },
    steps: hydrated.value,
  }
  story.preview(script)
}

/* ---------- 草稿箱 ---------- */

function readDrafts(): Record<string, StoryDraft> {
  try {
    const raw = JSON.parse(localStorage.getItem(DRAFTS_KEY) || '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch {
    return {}
  }
}

let persistTimer = 0

function schedulePersist() {
  window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(persist, 400)
}

function persist() {
  window.clearTimeout(persistTimer)
  if (!activeKey.value) return
  drafts.value[activeKey.value] = { ...draft.value, updated_at: Date.now() }
  try {
    localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts.value))
    localStorage.setItem(ACTIVE_KEY, activeKey.value)
  } catch {
    flash('浏览器存储空间不足，请导出备份')
  }
}

function openDraft(key: string) {
  const entry = drafts.value[key]
  if (!entry) return
  activeKey.value = key
  history.reset(JSON.parse(JSON.stringify(entry)))
  selected.value = 0
  sheet.value = ''
}

function newDraft(seed?: StoryDraft) {
  const key = `d${Date.now().toString(36)}`
  const entry = seed || createDraft()
  drafts.value[key] = JSON.parse(JSON.stringify(entry))
  activeKey.value = key
  history.reset(entry)
  selected.value = 0
  sheet.value = ''
  persist()
}

function dropDraft(key: string) {
  if (!window.confirm(`确认删除草稿「${drafts.value[key]?.title || key}」？删除后无法恢复。`)) return
  delete drafts.value[key]
  localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts.value))
  if (key === activeKey.value) {
    const next = Object.keys(drafts.value)[0]
    if (next) openDraft(next)
    else newDraft()
  }
}

/* ---------- 导入导出 ---------- */

async function shareStory() {
  if (problems.value.length) {
    flash(problems.value[0]!)
    return
  }
  sharing.value = true
  shareUrl.value = ''
  try {
    const result = await api<{ id: string }>('/api/red-leaf-town/story/shares', {
      method: 'POST',
      body: JSON.stringify(toScriptFile(draft.value, catalog.value)),
    })
    shareUrl.value = new URL(`${import.meta.env.BASE_URL}story-share/${result.id}`, window.location.origin).href
    try {
      await navigator.clipboard.writeText(shareUrl.value)
      flash('分享链接已复制，其他人无需登录即可观看')
    } catch {
      flash('分享已生成，请复制下方链接')
    }
  } catch (caught) {
    flash(caught instanceof Error ? caught.message : '分享失败，请重试')
  } finally {
    sharing.value = false
  }
}

function exportFile() {
  const payload = JSON.stringify(toScriptFile(draft.value, catalog.value), null, 2)
  const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${draft.value.id}.json`
  anchor.click()
  URL.revokeObjectURL(url)
  flash(`已导出 ${draft.value.id}.json`)
}

async function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const parsed = parseScriptFile(JSON.parse(await file.text()))
    const key = `d${Date.now().toString(36)}`
    drafts.value[key] = parsed
    activeKey.value = key
    history.reset(parsed)
    selected.value = 0
    persist()
    flash(`已导入「${parsed.title}」，共 ${parsed.steps.length} 步`)
  } catch (caught) {
    flash(caught instanceof Error ? caught.message : '无法读取该文件')
  }
}

function flash(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3200)
}

/* ---------- 快捷键 ---------- */

function onKey(event: KeyboardEvent) {
  if (story.active) return
  const target = event.target as HTMLElement | null
  const typing = target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  const meta = event.metaKey || event.ctrlKey
  if (meta && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    event.shiftKey ? history.redo() : history.undo()
    return
  }
  if (meta && event.key.toLowerCase() === 'y') {
    event.preventDefault()
    history.redo()
    return
  }
  if (meta && event.key.toLowerCase() === 'd') {
    event.preventDefault()
    duplicate()
    return
  }
  if (typing) return
  if (event.key === 'ArrowDown') { event.preventDefault(); select(selected.value + 1) }
  if (event.key === 'ArrowUp') { event.preventDefault(); select(selected.value - 1) }
  if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); remove() }
}

async function loadResources() {
  resources.value = await api<StoryResources>('/api/red-leaf-town/story/resources')
}

/** 选图弹窗传完或删完图之后，把素材清单和剩余额度重新拉一遍。 */
async function refreshResources() {
  try {
    await loadResources()
  } catch {
    // 拉不到就沿用手里这份，别打断正在写的东西。
  }
}

function measure() {
  narrow.value = window.innerWidth < 900
}

onMounted(async () => {
  measure()
  window.addEventListener('resize', measure)
  window.addEventListener('keydown', onKey)
  try {
    await loadResources()
    status.value = 'ready'
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 401) {
      status.value = 'guest'
      return
    }
    status.value = 'ready'
    loadError.value = caught instanceof Error ? caught.message : '素材库加载失败'
  }
  drafts.value = readDrafts()
  const saved = localStorage.getItem(ACTIVE_KEY) || ''
  if (drafts.value[saved]) openDraft(saved)
  else if (Object.keys(drafts.value)[0]) openDraft(Object.keys(drafts.value)[0])
  else newDraft(resources.value.example ? draftFromExample(resources.value.example) : undefined)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', measure)
  window.removeEventListener('keydown', onKey)
  persist()
})

watch(draft, schedulePersist, { deep: true })
</script>

<template>
  <!-- 工作区不做窄屏适配，直接请用户换电脑 -->
  <main v-if="narrow" class="gate">
    <span class="gate-seal"><Monitor :size="32" /></span>
    <h1>请用电脑打开</h1>
    <p>编辑器需要同时显示操作列表、16:9 预览和参数面板，窄屏无法容纳。请在宽度 900px 以上的设备上打开。</p>
    <a class="gate-back" href="/red-leaf-town/"><ArrowLeft :size="15" />回到红叶镇</a>
  </main>

  <main v-else-if="status === 'checking'" class="gate">
    <span class="gate-seal"><Leaf :size="32" /></span>
    <p class="gate-quiet">正在验证登录状态……</p>
  </main>

  <main v-else-if="status === 'guest'" class="gate">
    <span class="gate-seal"><Leaf :size="32" /></span>
    <h1>剧情编辑器</h1>
    <p>编排红叶镇的剧情，导出后提交给维护者。编辑器需要登录：上传的图片会记录上传者，草稿仅保存在本地浏览器。</p>
    <a class="gate-login" :href="loginUrl">使用水鱼账号登录<ChevronIn :size="17" /></a>
    <a class="gate-back" href="/red-leaf-town/"><ArrowLeft :size="15" />回到红叶镇</a>
  </main>

  <div v-else class="editor">
    <!-- 左半区：工具、当前段、列表、添加、提示 -->
    <section class="pane pane--left">
      <header class="bar">
        <button type="button" class="drafts-button" title="草稿箱" @click="sheet = 'drafts'"><List :size="16" /></button>
        <input
          class="title-input"
          :value="draft.title"
          maxlength="64"
          aria-label="剧本标题"
          @input="setField('标题', { title: ($event.target as HTMLInputElement).value })"
        />
        <button type="button" :disabled="!history.past.value.length" title="撤销 (Ctrl+Z)" @click="history.undo()"><Undo2 :size="15" /></button>
        <button type="button" :disabled="!history.future.value.length" title="重做 (Ctrl+Shift+Z)" @click="history.redo()"><Redo2 :size="15" /></button>
      </header>

      <nav class="bar bar--tools">
        <button type="button" @click="sheet = 'meta'"><FileText :size="14" />剧本信息</button>
        <button type="button" @click="fileInput?.click()"><Upload :size="14" />导入</button>
        <button type="button" class="primary" @click="exportFile"><Download :size="14" />导出</button>
        <button type="button" :disabled="sharing" @click="shareStory"><Copy :size="14" />{{ sharing ? '生成中…' : '分享' }}</button>
        <input ref="fileInput" type="file" accept="application/json,.json" hidden @change="importFile" />
      </nav>

      <div v-if="shareUrl" class="strip strip--ok">
        <span>分享的是当前版本，修改后请重新分享。链接包含本剧本使用的上传素材。</span>
        <input :value="shareUrl" readonly aria-label="剧情分享链接" style="width: 100%" @focus="($event.target as HTMLInputElement).select()" />
        <a :href="shareUrl" target="_blank" rel="noopener">打开分享页面</a>
      </div>
      <p v-if="notice" class="strip strip--ok">{{ notice }}</p>
      <p v-if="loadError" class="strip strip--alert">
        素材库加载失败：{{ loadError }}。请<a href="/red-leaf-town/">登录红叶镇</a>后重试。
      </p>

      <div class="step-head">
        <strong>第 {{ selected + 1 }} 步 · {{ current ? STEP_LABELS[current.type] : '无' }}</strong>
        <div class="step-nav">
          <button type="button" :disabled="selected <= 0" title="上一步" @click="select(selected - 1)"><ChevronLeft :size="14" /></button>
          <span>{{ selected + 1 }}/{{ steps.length }}</span>
          <button type="button" :disabled="selected >= steps.length - 1" title="下一步" @click="select(selected + 1)"><ChevronRight :size="14" /></button>
        </div>
        <button v-if="steps.length > 1" type="button" class="step-drop" title="删除此步骤" @click="remove()"><Trash2 :size="13" /></button>
        <button type="button" class="step-play" @click="playFull"><Play :size="13" />试播</button>
      </div>

      <div ref="listRef" class="op-list">
        <article
          v-for="(step, position) in steps"
          :key="position"
          class="op-row"
          :class="[`op-row--${step.type}`, { 'is-active': position === selected, 'is-over': dragOver === position }]"
          draggable="true"
          @click="select(position)"
          @dragstart="dragFrom = position"
          @dragover.prevent="dragOver = position"
          @dragend="dragFrom = -1; dragOver = -1"
          @drop.prevent="move(dragFrom, position); dragFrom = -1; dragOver = -1"
        >
          <span class="op-index">{{ position + 1 }}</span>
          <span class="op-glyph"><component :is="rowIcon(step)" :size="12" /></span>
          <div class="op-body">
            <template v-if="step.type === 'dialogue'">
              <span v-if="step.speaker" class="op-speaker">{{ step.speaker }}</span>
              <p class="op-line" :class="{ 'is-aside': !step.speaker, 'is-empty': !step.text.trim() }">
                {{ step.text.trim() || '未填写台词' }}
              </p>
            </template>
            <p v-else class="op-direction">{{ rowSummary(step) }}</p>
          </div>
          <button class="op-drop" type="button" title="删除此步骤" @click.stop="remove(position)"><X :size="12" /></button>
        </article>
      </div>

      <div class="op-add">
        <button type="button" @click="add('dialogue')"><Plus :size="12" />{{ STEP_LABELS.dialogue }}</button>
        <button type="button" @click="add('portrait')"><Plus :size="12" />{{ STEP_LABELS.portrait }}</button>
        <button type="button" @click="add('background')"><Plus :size="12" />{{ STEP_LABELS.background }}</button>
        <button type="button" class="icon" title="复制当前步骤 (Ctrl+D)" @click="duplicate"><Copy :size="12" /></button>
      </div>

      <ul v-if="problems.length" class="problems">
        <li v-for="problem in problems.slice(0, 3)" :key="problem">{{ problem }}</li>
        <li v-if="problems.length > 3">…… 还有 {{ problems.length - 3 }} 条</li>
      </ul>
    </section>

    <!-- 右半区：上半整块预览，下半整块参数，高度各占半屏、锁死 -->
    <section class="pane pane--right">
      <div class="preview">
        <div
          class="preview-frame"
          title="左键下一步，右键上一步"
          @click="select(selected + 1)"
          @contextmenu.prevent="select(selected - 1)"
        >
          <StoryStage
            embedded
            hide-caret
            mode="stage"
            :background="stage.background"
            :portraits="stage.portraits"
            :line="stage.line"
          />
        </div>
      </div>
      <div class="params">
        <StepInspector
          v-if="current"
          :step="current"
          :resources="catalog"
          :speakers="speakers"
          :quota="quota"
          @patch="patch"
          @resources-changed="refreshResources"
        />
      </div>
    </section>

    <!-- 剧本信息 / 草稿箱 -->
    <div v-if="sheet" class="sheet-scrim" @click.self="sheet = ''">
      <section v-if="sheet === 'meta'" class="sheet">
        <header><strong>剧本信息</strong><button type="button" @click="sheet = ''"><X :size="17" /></button></header>
        <div class="sheet-body">
          <label class="sheet-field">
            <span>剧本 ID<i v-if="!ID_PATTERN.test(draft.id)" class="bad">格式不对</i></span>
            <input :value="draft.id" @input="setField('剧本ID', { id: ($event.target as HTMLInputElement).value })" />
            <small>用作文件名和存档中的已看记录，确定后不要再修改。以小写字母开头，可使用数字、下划线和减号。</small>
          </label>
          <label class="sheet-field">
            <span>优先级</span>
            <input type="number" min="-100" max="100" :value="draft.priority"
              @input="setField('优先级', { priority: Number(($event.target as HTMLInputElement).value) || 0 })" />
            <small>多段剧情同时触发时，数值大的优先播放。通常保持 0。</small>
          </label>
          <label class="sheet-field">
            <span>作者</span>
            <input :value="draft.metadata.author" placeholder="填写署名"
              @input="setField('作者', { metadata: { ...draft.metadata, author: ($event.target as HTMLInputElement).value } })" />
          </label>
          <label class="sheet-field">
            <span>这段剧情什么时候该播</span>
            <textarea rows="3" :value="draft.metadata.trigger_note"
              placeholder="用自然语言描述触发时机，例如：玩家首次进入农场，且已拥有绯恩"
              @input="setField('触发说明', { metadata: { ...draft.metadata, trigger_note: ($event.target as HTMLTextAreaElement).value } })" />
            <small>触发条件由维护者配置到剧本中，此处说明意图即可。</small>
          </label>
          <label class="sheet-field">
            <span>建议奖励</span>
            <textarea rows="2" :value="draft.metadata.reward_note"
              placeholder="例如：播放结束后发放 5 个橙橙果种子"
              @input="setField('奖励说明', { metadata: { ...draft.metadata, reward_note: ($event.target as HTMLTextAreaElement).value } })" />
            <small>奖励由维护者最终确定，此处填写建议。</small>
          </label>
          <label class="sheet-field">
            <span>备注</span>
            <textarea rows="2" :value="draft.metadata.note"
              @input="setField('备注', { metadata: { ...draft.metadata, note: ($event.target as HTMLTextAreaElement).value } })" />
          </label>
        </div>
      </section>

      <section v-else class="sheet">
        <header><strong>草稿箱</strong><button type="button" @click="sheet = ''"><X :size="17" /></button></header>
        <div class="sheet-body">
          <p class="sheet-hint">草稿保存在当前设备的浏览器中，更换设备或清除缓存后会丢失。完成后请导出备份。</p>
          <button type="button" class="new-draft" @click="newDraft()"><Plus :size="15" />新建剧本</button>
          <article v-for="(entry, key) in drafts" :key="key" class="draft-row" :class="{ 'is-active': key === activeKey }">
            <button type="button" class="draft-open" @click="openDraft(key)">
              <strong>{{ entry.title }}</strong>
              <small>{{ entry.id }} · {{ entry.steps.length }} 步 · {{ new Date(entry.updated_at).toLocaleString('zh-CN') }}</small>
            </button>
            <button type="button" class="draft-drop" @click="dropDraft(key)"><Trash2 :size="14" /></button>
          </article>
        </div>
      </section>
    </div>

    <StoryOverlay />
  </div>
</template>

<style scoped>
.editor {
  --ed-ground: #0c1310;
  --ed-panel: #141d18;
  --ed-well: #0e1612;
  --ed-line: #ffffff14;
  --ed-line-strong: #ffffff2e;
  --ed-cream: #ece6d9;
  --ed-muted: #7d8a80;
  --ed-gold: #d6ad63;
  --ed-clay: #d0714b;
  --ed-moss: #9cbe7c;
  --ed-alert: #e2907c;
  /* 页面高度一分为二，预览的宽度由这个半高按 16:9 推出来 */
  --half: 50dvh;

  /* 右栏由半屏高按 16:9 定宽，左栏最多占它的 2/3；装得下就整体居中 */
  --right: calc(var(--half) * 16 / 9);

  height: 100dvh;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, calc(var(--right) * 2 / 3)) var(--right);
  justify-content: center;
  color: var(--ed-cream);
  background: var(--ed-ground);
}
button, input, select, textarea { font: inherit; color: inherit; }

/* ---- 左半区 ---- */
.pane--left { display: flex; flex-direction: column; min-width: 0; min-height: 0; border-right: 1px solid var(--ed-line); background: var(--ed-panel); }
.pane--left > * { flex: 0 0 auto; }

.bar { display: flex; align-items: center; gap: 6px; padding: 7px 9px; border-bottom: 1px solid var(--ed-line); }
.drafts-button { display: grid; place-items: center; width: 28px; height: 28px; flex: 0 0 auto; padding: 0; color: var(--ed-muted); border: 1px solid var(--ed-line); border-radius: 8px 3px 8px 3px; background: transparent; cursor: pointer; }
.drafts-button:hover { color: var(--ed-cream); border-color: var(--ed-line-strong); }
.title-input {
  flex: 1 1 auto;
  min-width: 0;
  padding: 4px 8px;
  font-family: Georgia, 'Noto Serif SC', 'Songti SC', serif;
  font-size: 15px;
  border: 1px solid transparent;
  border-radius: 8px 3px 8px 3px;
  background: transparent;
  outline: none;
}
.title-input:hover { border-color: var(--ed-line); }
.title-input:focus-visible { border-color: var(--ed-gold); background: var(--ed-well); }
.bar > button {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  color: var(--ed-muted);
  border: 1px solid var(--ed-line);
  border-radius: 8px 3px 8px 3px;
  background: transparent;
  cursor: pointer;
}
.bar--tools { gap: 5px; }
.bar--tools button {
  width: auto;
  height: 27px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 8px;
  font-size: 12px;
}
.bar button:hover:not(:disabled) { color: var(--ed-cream); border-color: var(--ed-line-strong); }
.bar button:disabled { opacity: .3; cursor: not-allowed; }
.bar--tools .primary { color: var(--ed-ground); font-weight: 700; border-color: transparent; background: var(--ed-gold); }

.strip { margin: 0; padding: 6px 10px; font-size: 12px; line-height: 1.6; border-bottom: 1px solid var(--ed-line); }
.strip--ok { color: var(--ed-moss); background: #9cbe7c0d; }
.strip--alert { color: var(--ed-alert); background: #e2907c12; }
.strip a { color: var(--ed-gold); text-decoration: underline; }

/* 当前选中的这一步：标题、翻页、删除、试播 */
.step-head { display: flex; align-items: center; gap: 7px; padding: 7px 10px; border-bottom: 1px solid var(--ed-line); }
.step-head > strong { flex: 1 1 auto; min-width: 0; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-nav { display: flex; align-items: center; gap: 2px; }
.step-nav span { min-width: 42px; text-align: center; color: var(--ed-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.step-head button {
  height: 26px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 7px;
  color: var(--ed-muted);
  font-size: 12px;
  border: 1px solid var(--ed-line);
  border-radius: 7px 2px 7px 2px;
  background: transparent;
  cursor: pointer;
}
.step-nav button { padding: 0 5px; }
.step-head button:hover:not(:disabled) { color: var(--ed-cream); border-color: var(--ed-line-strong); }
.step-head button:disabled { opacity: .3; cursor: not-allowed; }
.step-drop:hover { color: var(--ed-alert) !important; border-color: #e2907c44 !important; }
.step-play { color: var(--ed-gold) !important; border-color: #d6ad6340 !important; }

/* ---- 操作列表：读起来像剧本 ---- */
.op-list { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 5px; }
.op-row {
  display: grid;
  grid-template-columns: 20px 18px minmax(0, 1fr) 20px;
  align-items: start;
  gap: 5px;
  padding: 4px 3px;
  border-left: 2px solid transparent;
  border-radius: 0 7px 7px 0;
  cursor: pointer;
}
.op-row:hover { background: #ffffff07; }
.op-row.is-active { background: #ffffff0e; border-left-color: var(--ed-gold); }
.op-row.is-over { box-shadow: inset 0 2px 0 var(--ed-gold); }
.op-index { color: #55605a; font-size: 11px; text-align: right; font-variant-numeric: tabular-nums; line-height: 1.6; }
.op-glyph { display: grid; place-items: center; width: 18px; height: 18px; border-radius: 5px 2px 5px 2px; }
.op-row--dialogue .op-glyph { color: var(--ed-gold); background: #d6ad6314; }
.op-row--background .op-glyph { color: var(--ed-clay); background: #d0714b14; }
.op-row--portrait .op-glyph { color: var(--ed-moss); background: #9cbe7c14; }
.op-body { min-width: 0; }
.op-speaker { display: block; color: var(--ed-gold); font-size: 11px; font-weight: 600; }
.op-line {
  max-width: 74ch;
  margin: 0;
  font-family: Georgia, 'Noto Serif SC', 'Songti SC', serif;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--ed-cream);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.op-line.is-aside { color: #b9c2b7; font-style: italic; }
.op-line.is-empty { color: #5c665f; font-style: italic; }
/* 舞台指示不是台词，压低一档，扫列表时自动让位给故事 */
.op-direction { margin: 0; padding-top: 1px; color: var(--ed-muted); font-size: 12px; line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.op-drop { width: 20px; height: 20px; display: grid; place-items: center; color: #5e6a62; border: 0; border-radius: 5px; background: transparent; opacity: 0; cursor: pointer; }
.op-row:hover .op-drop, .op-row.is-active .op-drop { opacity: 1; }
.op-drop:hover { color: var(--ed-alert); background: #e2907c14; }

.op-add { display: flex; gap: 4px; padding: 6px; border-top: 1px solid var(--ed-line); }
.op-add button {
  flex: 0 0 auto;
  min-width: 78px;
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  color: var(--ed-muted);
  border: 1px dashed var(--ed-line-strong);
  border-radius: 7px 2px 7px 2px;
  background: transparent;
  cursor: pointer;
}
.op-add button:hover { color: var(--ed-cream); border-color: var(--ed-gold); border-style: solid; }
.op-add .icon { min-width: 30px; }

.problems { margin: 0; padding: 6px 10px; list-style: none; border-top: 1px solid #e2907c22; background: #e2907c0d; }
.problems li { color: var(--ed-alert); font-size: 12px; line-height: 1.6; }

/* ---- 右半区：两块各占半屏，高度锁死 ---- */
.pane--right { display: grid; grid-template-rows: var(--half) var(--half); min-width: 0; min-height: 0; }
.preview { display: grid; place-items: center; min-height: 0; overflow: hidden; background: #050706; }
/* 半高按 16:9 推出宽度；面板被挤窄时保比例居中，绝不变形 */
.preview-frame { width: min(100%, calc(var(--half) * 16 / 9)); aspect-ratio: 16 / 9; cursor: pointer; user-select: none; }
.params { min-height: 0; overflow-y: auto; padding: 12px 14px; border-top: 1px solid var(--ed-line); background: var(--ed-panel); }
.params > * { max-width: 760px; }

/* ---- 抽屉 ---- */
.sheet-scrim { position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; padding: 20px; background: #05070699; backdrop-filter: blur(3px); }
.sheet { width: min(520px, 100%); max-height: min(660px, 90dvh); display: grid; grid-template-rows: auto minmax(0, 1fr); border: 1px solid var(--ed-line-strong); border-radius: 18px 5px 18px 5px; background: var(--ed-panel); box-shadow: 0 30px 90px #000a; }
.sheet header { display: flex; align-items: center; justify-content: space-between; padding: 13px 15px; border-bottom: 1px solid var(--ed-line); }
.sheet header strong { font-size: 15px; }
.sheet header button { width: 30px; height: 30px; display: grid; place-items: center; color: var(--ed-muted); border: 0; background: transparent; cursor: pointer; }
.sheet-body { overflow-y: auto; padding: 15px; display: grid; gap: 12px; }
.sheet-hint { margin: 0; color: var(--ed-muted); font-size: 12px; line-height: 1.7; }
.sheet-field { display: grid; gap: 6px; }
.sheet-field > span { display: flex; align-items: center; justify-content: space-between; color: var(--ed-muted); font-size: 12px; }
.sheet-field .bad { color: var(--ed-alert); font-style: normal; }
.sheet-field input, .sheet-field textarea {
  width: 100%;
  padding: 8px 9px;
  border: 1px solid var(--ed-line);
  border-radius: 9px 3px 9px 3px;
  background: var(--ed-well);
  outline: none;
  resize: vertical;
}
.sheet-field input:focus-visible, .sheet-field textarea:focus-visible { border-color: var(--ed-gold); }
.sheet-field small { color: #616c64; font-size: 11px; line-height: 1.7; }

.new-draft { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; color: var(--ed-gold); border: 1px dashed #d6ad6355; border-radius: 10px 3px 10px 3px; background: transparent; cursor: pointer; }
.draft-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center; padding: 4px; border: 1px solid var(--ed-line); border-radius: 11px 3px 11px 3px; }
.draft-row.is-active { border-color: var(--ed-gold); }
.draft-open { display: grid; gap: 3px; padding: 7px 9px; text-align: left; border: 0; background: transparent; cursor: pointer; }
.draft-open strong { font-size: 13px; }
.draft-open small { color: var(--ed-muted); font-size: 11px; }
.draft-drop { width: 32px; height: 32px; display: grid; place-items: center; color: #5e6a62; border: 0; border-radius: 8px; background: transparent; cursor: pointer; }
.draft-drop:hover { color: var(--ed-alert); background: #e2907c14; }

:focus-visible { outline: 2px solid var(--ed-gold); outline-offset: 1px; }

/* 登录门 / 窄屏门 */
.gate {
  height: 100dvh;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 13px;
  padding: 32px;
  text-align: center;
  color: #ece6d9;
  background: radial-gradient(circle at 50% 0, #783d2922, transparent 42%), #0c1310;
}
.gate-seal { display: grid; place-items: center; width: 68px; height: 68px; color: #d6ad63; border: 1px solid #d6ad6355; border-radius: 22px 6px 22px 6px; }
.gate h1 { margin: 4px 0 0; font: 700 25px Georgia, 'Noto Serif SC', serif; }
.gate p { max-width: 42ch; margin: 0; color: #7d8a80; font-size: 13px; line-height: 1.9; }
.gate-quiet { color: #616c64; }
.gate-login {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 0 24px;
  color: #0c1310;
  font-weight: 700;
  border-radius: 12px 4px 12px 4px;
  background: #d6ad63;
}
.gate-back { display: inline-flex; align-items: center; gap: 5px; color: #7d8a80; font-size: 12px; }
.gate-back:hover { color: #ece6d9; }
</style>

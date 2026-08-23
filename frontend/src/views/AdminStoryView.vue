<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, Check, ImageUp, Leaf, LockKeyhole, Move, Play, RefreshCw, RotateCcw, Trash2, X } from 'lucide-vue-next'

import { api, ApiError } from '@/api'
import StoryOverlay from '@/components/story/StoryOverlay.vue'
import { useStoryStore } from '@/stores/story'
import type {
  StoryAdminPayload,
  StoryAsset,
  StoryAssetKind,
  StoryAssetLayout,
  StoryMode,
  StoryPortraitSlot,
  StoryScript,
  StoryStep,
} from '@/types'

const TOKEN_KEY = 'red_leaf_town_admin_token'
const story = useStoryStore()
const token = ref(localStorage.getItem(TOKEN_KEY) || '')
const tokenInput = ref(token.value)
const authenticated = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const payload = ref<StoryAdminPayload | null>(null)
const file = ref<File | null>(null)
const fileName = ref('')
const draft = ref({ id: '', name: '', kind: 'background' as StoryAssetKind })
const layoutAsset = ref<StoryAsset | null>(null)
const layouts = ref<Record<StoryMode, StoryAssetLayout>>(blankLayouts())
const layoutSlot = ref<StoryPortraitSlot>('left')
const layoutMode = ref<StoryMode>('inline')
const layoutBackgroundId = ref('')
const layout = computed(() => layouts.value[layoutMode.value])

function blankLayouts(): Record<StoryMode, StoryAssetLayout> {
  return {
    inline: { scale: 1, offset_x: 0, offset_y: 0 },
    stage: { scale: 1, offset_x: 0, offset_y: 0 },
  }
}

const backgrounds = computed(() => (payload.value?.assets || []).filter((asset) => asset.kind === 'background'))
const portraits = computed(() => (payload.value?.assets || []).filter((asset) => asset.kind === 'portrait'))
const cdnReady = computed(() => payload.value?.options.cdn.configured !== false)
const uploadReady = computed(() => Boolean(file.value && /^[a-z][a-z0-9_-]{1,63}$/.test(draft.value.id.trim())))

function headers(json = true): Record<string, string> {
  return { 'X-Admin-Token': token.value, ...(json ? { 'Content-Type': 'application/json' } : {}) }
}

async function load() {
  error.value = ''
  try {
    payload.value = await api<StoryAdminPayload>('/api/red-leaf-town/admin/story', { headers: headers() })
    authenticated.value = true
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '后台加载失败'
    if (caught instanceof ApiError && caught.status === 403) {
      authenticated.value = false
      localStorage.removeItem(TOKEN_KEY)
    }
  }
}

async function unlock() {
  token.value = tokenInput.value.trim()
  if (!token.value) return
  localStorage.setItem(TOKEN_KEY, token.value)
  await load()
}

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0] || null
  file.value = picked
  fileName.value = picked?.name || ''
  if (picked && !draft.value.id) {
    draft.value.id = picked.name.replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9_-]/g, '-').slice(0, 60)
  }
  input.value = ''
}

async function upload() {
  if (!file.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('id', draft.value.id.trim())
    form.append('name', draft.value.name.trim() || draft.value.id.trim())
    form.append('kind', draft.value.kind)
    const response = await fetch('/api/red-leaf-town/admin/story/assets', {
      method: 'POST',
      headers: headers(false),
      body: form,
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new ApiError(body.message || '素材上传失败', response.status, body.code)
    flash(`${draft.value.id} 已转码为 WebP 并上传到 CDN`)
    file.value = null
    fileName.value = ''
    draft.value = { id: '', name: '', kind: draft.value.kind }
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '素材上传失败'
  } finally {
    busy.value = false
  }
}

async function remove(asset: StoryAsset) {
  if (busy.value || !window.confirm(`确定从素材库移除 ${asset.name}？`)) return
  busy.value = true
  error.value = ''
  try {
    await api(`/api/red-leaf-town/admin/story/assets/${encodeURIComponent(asset.id)}`, {
      method: 'DELETE',
      headers: headers(),
    })
    flash('素材已移除')
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '删除失败'
  } finally {
    busy.value = false
  }
}

async function reload() {
  busy.value = true
  error.value = ''
  try {
    const result = await api<{ script_count: number }>('/api/red-leaf-town/admin/story/reload', {
      method: 'POST',
      headers: headers(),
    })
    flash(`已重新读取 ${result.script_count} 个剧本`)
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '剧本重新加载失败'
  } finally {
    busy.value = false
  }
}

function flash(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3000)
}

function preview(script: StoryScript) {
  story.preview(script)
}

function openLayout(asset: StoryAsset) {
  layoutAsset.value = asset
  layouts.value = {
    inline: { ...blankLayouts().inline, ...(asset.layouts?.inline || asset.inline_layout) },
    stage: { ...blankLayouts().stage, ...(asset.layouts?.stage || asset.stage_layout) },
  }
  layoutBackgroundId.value = layoutBackgroundId.value || backgrounds.value[0]?.id || ''
  restartLayoutPreview()
}

function restartLayoutPreview() {
  const asset = layoutAsset.value
  if (!asset) return
  const background = backgrounds.value.find((entry) => entry.id === layoutBackgroundId.value)
  const steps: StoryStep[] = []
  if (layoutMode.value === 'stage' && background) {
    steps.push({ type: 'background', asset_id: background.id, asset: background })
  }
  steps.push({
    type: 'portrait',
    slot: layoutSlot.value,
    visible: true,
    asset_id: asset.id,
    partner_id: '',
    breakthrough: 0,
    asset: { ...asset, layouts: { ...layouts.value } },
  })
  steps.push({
    type: 'dialogue',
    speaker: asset.name,
    text: '预览用的台词，看看立绘和这行字的关系合不合适。',
    focus: layoutSlot.value,
  })
  story.preview(
    {
      id: `layout-preview-${asset.id}`,
      title: asset.name,
      mode: layoutMode.value,
      priority: 0,
      repeatable: true,
      trigger_description: '',
      steps,
    },
    { locked: true },
  )
}

function applyLayout() {
  story.setPortraitLayout(layoutSlot.value, {
    scale: layout.value.scale,
    offsetX: layout.value.offset_x,
    offsetY: layout.value.offset_y,
  })
}

function resetLayout() {
  layouts.value[layoutMode.value] = { scale: 1, offset_x: 0, offset_y: 0 }
  applyLayout()
}

function closeLayout() {
  layoutAsset.value = null
  layouts.value = blankLayouts()
  story.skip()
}

async function saveLayout() {
  const asset = layoutAsset.value
  if (!asset || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/api/red-leaf-town/admin/story/assets/${encodeURIComponent(asset.id)}`, {
      method: 'PATCH',
      headers: headers(),
      body: JSON.stringify({ inline_layout: layouts.value.inline, stage_layout: layouts.value.stage }),
    })
    flash(`${asset.name} 的立绘位置已保存`)
    closeLayout()
    await load()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '保存失败'
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
      <h1>剧情素材管理</h1>
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
        <div class="brand"><span><Leaf :size="22" /></span><div><strong>红叶镇后台</strong><small>剧情素材与剧本</small></div></div>
        <div class="header-actions">
          <span v-if="notice" class="notice"><Check :size="15" />{{ notice }}</span>
          <a href="/red-leaf-town/"><ArrowLeft :size="16" />玩家前台</a>
          <button class="save-button" :disabled="busy" @click="reload"><RefreshCw :size="16" />重新读取剧本</button>
        </div>
      </header>

      <div class="admin-body">
        <p v-if="error" class="editor-error">{{ error }}</p>

        <div class="section-heading">
          <div><small>ASSETS</small><h2>素材库</h2></div>
          <p :class="{ 'cdn-warning': !cdnReady }">
            {{ cdnReady ? '上传会统一转码为 WebP 并推送到 CDN，剧本里只写素材 ID。' : 'CDN provider 尚未配置，上传会失败。' }}
          </p>
        </div>

        <section class="form-card upload-card">
          <label class="file-drop">
            <input type="file" accept="image/png,image/jpeg,image/webp" @change="pickFile" />
            <ImageUp :size="20" />
            <strong>{{ fileName || '选择背景或立绘图片' }}</strong>
            <small>支持 JPG / PNG / WebP，背景长边压到 2560，立绘压到 1920。立绘请上传透明底 PNG，透明通道会保留</small>
          </label>
          <div class="upload-fields">
            <label><span>素材 ID</span><input v-model="draft.id" placeholder="autumn_gate" /></label>
            <label><span>显示名称</span><input v-model="draft.name" placeholder="镇口 · 黄昏" /></label>
            <label><span>类型</span>
              <select v-model="draft.kind">
                <option v-for="kind in payload?.options.kinds" :key="kind.id" :value="kind.id">{{ kind.name }}</option>
              </select>
            </label>
            <button class="upload-button" :disabled="!uploadReady || busy" @click="upload">
              <ImageUp :size="15" />上传素材
            </button>
          </div>
        </section>

        <div class="asset-columns">
          <section>
            <h3>背景 <i>{{ backgrounds.length }}</i></h3>
            <article v-for="asset in backgrounds" :key="asset.id" class="asset-card">
              <div class="asset-frame asset-frame--wide"><img v-if="asset.url" :src="asset.url" :alt="asset.name" /></div>
              <div class="asset-meta">
                <strong>{{ asset.name }}</strong>
                <small>{{ asset.id }} · {{ asset.width }}×{{ asset.height }}</small>
              </div>
              <button class="delete-button" @click="remove(asset)"><Trash2 :size="14" /></button>
            </article>
            <p v-if="!backgrounds.length" class="empty-hint">还没有背景素材。</p>
          </section>

          <section>
            <h3>立绘 <i>{{ portraits.length }}</i></h3>
            <article v-for="asset in portraits" :key="asset.id" class="asset-card">
              <div class="asset-frame"><img v-if="asset.url" :src="asset.url" :alt="asset.name" /></div>
              <div class="asset-meta">
                <strong>{{ asset.name }}</strong>
                <small>{{ asset.id }} · {{ asset.width }}×{{ asset.height }}</small>
                <em>插话 ×{{ (asset.layouts?.inline.scale ?? 1).toFixed(2) }} · 舞台 ×{{ (asset.layouts?.stage.scale ?? 1).toFixed(2) }}</em>
              </div>
              <div class="asset-actions">
                <button class="layout-button" @click="openLayout(asset)"><Move :size="14" />位置</button>
                <button class="delete-button" @click="remove(asset)"><Trash2 :size="14" /></button>
              </div>
            </article>
            <p v-if="!portraits.length" class="empty-hint">还没有立绘素材。</p>
          </section>
        </div>

        <div class="section-heading">
          <div><small>SCRIPTS</small><h2>剧本</h2></div>
          <p>剧本是手写的 JSON，放在 <code>{{ payload?.options.script_directory }}</code>。改完点上面的重新读取。</p>
        </div>

        <section class="script-list">
          <article v-for="script in payload?.scripts || []" :key="script.id" class="script-card">
            <div>
              <strong>{{ script.title }}</strong>
              <small>{{ script.id }} · {{ script.steps.length }} 步 · {{ script.trigger_description }}</small>
            </div>
            <span class="mode-chip" :class="`mode-chip--${script.mode}`">{{ script.mode === 'stage' ? '全屏舞台' : '就地插话' }}</span>
            <span v-if="script.repeatable" class="mode-chip">可重复</span>
            <button class="preview-button" @click="preview(script)"><Play :size="14" />预览</button>
          </article>
          <p v-if="!(payload?.scripts || []).length" class="empty-hint">剧本目录还是空的。</p>
        </section>
      </div>
    </template>

    <StoryOverlay />

    <Teleport to="body">
      <section v-if="layoutAsset" class="layout-panel">
        <header>
          <div><small>PORTRAIT LAYOUT</small><strong>{{ layoutAsset.name }}</strong></div>
          <button class="panel-close" @click="closeLayout"><X :size="18" /></button>
        </header>

        <div class="panel-row">
          <div class="segmented">
            <button :class="{ active: layoutSlot === 'left' }" @click="layoutSlot = 'left'; restartLayoutPreview()">左侧</button>
            <button :class="{ active: layoutSlot === 'right' }" @click="layoutSlot = 'right'; restartLayoutPreview()">右侧</button>
          </div>
          <div class="segmented">
            <button :class="{ active: layoutMode === 'inline' }" @click="layoutMode = 'inline'; restartLayoutPreview()">插话</button>
            <button :class="{ active: layoutMode === 'stage' }" @click="layoutMode = 'stage'; restartLayoutPreview()">舞台</button>
          </div>
        </div>

        <label v-if="layoutMode === 'stage' && backgrounds.length" class="panel-field">
          <span>预览背景</span>
          <select v-model="layoutBackgroundId" @change="restartLayoutPreview">
            <option v-for="background in backgrounds" :key="background.id" :value="background.id">{{ background.name }}</option>
          </select>
        </label>

        <label class="panel-field">
          <span>缩放 <i>{{ layout.scale.toFixed(2) }}</i></span>
          <input v-model.number="layout.scale" type="range" min="0.4" max="4" step="0.01" @input="applyLayout" />
        </label>
        <label class="panel-field">
          <span>横向偏移 <i>{{ layout.offset_x.toFixed(2) }}</i></span>
          <input v-model.number="layout.offset_x" type="range" min="-0.5" max="0.5" step="0.01" @input="applyLayout" />
        </label>
        <label class="panel-field">
          <span>纵向偏移 <i>{{ layout.offset_y.toFixed(2) }}</i></span>
          <input v-model.number="layout.offset_y" type="range" min="-0.5" max="0.5" step="0.01" @input="applyLayout" />
        </label>

        <p class="panel-hint">插话和舞台各存一套位置，两边分别调。参数存在素材上，剧本里只要写 slot 就会套用。</p>
        <div class="panel-actions">
          <button class="ghost" @click="resetLayout"><RotateCcw :size="14" />复位</button>
          <button class="ghost" @click="closeLayout">取消</button>
          <button class="confirm" :disabled="busy" @click="saveLayout">保存位置</button>
        </div>
      </section>
    </Teleport>
  </main>
</template>

<style scoped>
.admin-page { min-height: 100vh; color: #eee8db; background: radial-gradient(circle at 85% 0, #783d2922, transparent 28%), #0d1410; }
button, input, select, textarea { font: inherit; }
button { color: inherit; }
.unlock-card { width: min(440px, calc(100% - 32px)); margin: auto; position: absolute; inset: 50% auto auto 50%; transform: translate(-50%, -50%); padding: 40px; text-align: center; border: 1px solid #ffffff16; border-radius: 28px 8px; background: #18221c; box-shadow: 0 30px 100px #0008; }
.admin-seal { width: 70px; height: 70px; display: grid; place-items: center; margin: auto; color: #d4a95b; border: 1px solid #d4a95b66; border-radius: 22px 7px; }
.kicker { color: #d37047; font-size: 12px; font-weight: 800; letter-spacing: .2em; }
.unlock-card h1 { font: 700 30px Georgia, serif; margin: 8px 0; }.unlock-card > p:not(.kicker) { color: #98a398; font-size: 13px; }.unlock-card form { display: grid; gap: 10px; margin: 25px 0 15px; }.unlock-card input, .unlock-card button { min-height: 45px; padding: 0 14px; border-radius: 10px; }.unlock-card input { color: #eee8db; border: 1px solid #ffffff18; background: #101712; }.unlock-card button { color: #172016; font-weight: 800; border: 0; background: #a9ca87; cursor: pointer; }.unlock-card a { display: inline-flex; align-items: center; gap: 5px; margin-top: 18px; color: #89958b; font-size: 12px; }.form-error { display: block; color: #efa091; font-size: 12px; }
.admin-header { height: 72px; position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; padding: 0 28px; border-bottom: 1px solid #ffffff12; background: #0e1611ef; backdrop-filter: blur(16px); }.brand { display: flex; align-items: center; gap: 11px; }.brand > span { width: 39px; height: 39px; display: grid; place-items: center; color: #d5ad60; border: 1px solid #d5ad6044; border-radius: 13px 4px; }.brand strong,.brand small { display: block; }.brand small { color: #778278; font-size: 12px; margin-top: 2px; }.header-actions { display: flex; align-items: center; gap: 10px; }.header-actions a,.header-actions button { min-height: 37px; display: inline-flex; align-items: center; gap: 7px; padding: 0 13px; border-radius: 9px; cursor: pointer; }.header-actions a { color: #a8b2a8; border: 1px solid #ffffff14; }.save-button { color: #182116; font-weight: 800; border: 0; background: #aacb88; }.save-button:disabled { opacity: .5; cursor: not-allowed; }.notice { display: flex; align-items: center; gap: 5px; color: #aacb88; font-size: 12px; }
.admin-body { width: min(1180px, 100%); padding: 30px clamp(16px, 4vw, 54px) 90px; }
.editor-error { padding: 11px 14px; color: #f0a696; border: 1px solid #dc7c6933; border-radius: 10px; background: #dc7c6910; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin: 34px 0 15px; }.section-heading small { color: #d0714b; font-size: 12px; font-weight: 800; letter-spacing: .18em; }.section-heading h2 { margin: 4px 0 0; font-size: 19px; }.section-heading p { margin: 0; max-width: 460px; color: #7f8b81; font-size: 12px; line-height: 1.7; }.section-heading p.cdn-warning { color: #df947d; }.section-heading code { color: #b7c9ab; }
.form-card { padding: 20px; border: 1px solid #ffffff11; border-radius: 18px 6px; background: #17211b; }
.upload-card { display: grid; grid-template-columns: minmax(220px, 300px) 1fr; gap: 18px; }
.file-drop { display: grid; justify-items: center; align-content: center; gap: 7px; padding: 20px; text-align: center; color: #8fa090; border: 1px dashed #ffffff1c; border-radius: 14px 5px; background: #0f1712; cursor: pointer; }.file-drop input { display: none; }.file-drop strong { color: #dfe4d8; font-size: 13px; word-break: break-all; }.file-drop small { color: #78847b; font-size: 12px; line-height: 1.6; }
.upload-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-content: start; }.upload-fields label > span { display: block; margin-bottom: 6px; color: #818d83; font-size: 12px; }.upload-fields input,.upload-fields select { width: 100%; height: 39px; padding: 0 10px; color: #eee8db; border: 1px solid #ffffff14; border-radius: 8px; background: #0f1712; outline: none; }.upload-fields input:focus,.upload-fields select:focus { border-color: #9aba7866; }.upload-fields select:disabled { opacity: .5; }
.upload-button { grid-column: 1 / -1; min-height: 40px; display: flex; align-items: center; justify-content: center; gap: 7px; color: #bad49e; font-size: 13px; border: 1px solid #9cbe7c33; border-radius: 9px; background: #9cbe7c0d; cursor: pointer; }.upload-button:disabled { opacity: .45; cursor: not-allowed; }
.asset-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 16px; }.asset-columns h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 10px; font-size: 14px; }.asset-columns h3 i { padding: 2px 8px; color: #9db982; font-size: 12px; font-style: normal; border-radius: 99px; background: #9db98214; }
.asset-card { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; padding: 10px; margin-bottom: 8px; border: 1px solid #ffffff11; border-radius: 14px 5px; background: #17211b; }
.asset-frame { width: 54px; aspect-ratio: 9 / 16; overflow: hidden; border-radius: 8px 3px; background: #0b110d; }.asset-frame--wide { width: 96px; aspect-ratio: 16 / 9; }.asset-frame img { width: 100%; height: 100%; object-fit: contain; }
.asset-meta { min-width: 0; }.asset-meta strong,.asset-meta small,.asset-meta em { display: block; }.asset-meta small { margin-top: 3px; color: #748077; font-size: 12px; word-break: break-all; }.asset-meta em { margin-top: 4px; color: #c69349; font-size: 12px; font-style: normal; }
.delete-button { width: 34px; height: 34px; display: grid; place-items: center; color: #d98b7c; border: 1px solid #d98b7c33; border-radius: 9px; background: #d98b7c0a; cursor: pointer; }
.asset-actions { display: flex; align-items: center; gap: 6px; }
.layout-button { min-height: 34px; display: inline-flex; align-items: center; gap: 5px; padding: 0 10px; color: #bad49e; font-size: 12px; border: 1px solid #9cbe7c33; border-radius: 9px; background: #9cbe7c0d; cursor: pointer; }
.layout-panel { position: fixed; z-index: 400; right: 22px; top: 22px; width: min(320px, calc(100vw - 32px)); padding: 18px; color: #eee8db; border: 1px solid #ffffff1c; border-radius: 20px 6px; background: #131c17f2; backdrop-filter: blur(16px); box-shadow: 0 30px 90px #000a; }
.layout-panel header { display: flex; align-items: start; justify-content: space-between; margin-bottom: 14px; }.layout-panel header small { display: block; color: #d0714b; font-size: 12px; font-weight: 800; letter-spacing: .16em; }.layout-panel header strong { display: block; margin-top: 4px; font-size: 15px; }
.panel-close { width: 30px; height: 30px; display: grid; place-items: center; color: #8e9a90; border: 1px solid #ffffff12; border-radius: 8px; background: transparent; cursor: pointer; }
.panel-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
.segmented { display: flex; gap: 4px; padding: 3px; border: 1px solid #ffffff10; border-radius: 10px; background: #0a100c88; }.segmented button { flex: 1; min-height: 30px; color: #78847b; font-size: 12px; border: 0; border-radius: 7px; background: transparent; cursor: pointer; }.segmented button.active { color: #e8e6dc; background: #ffffff0e; }
.panel-field { display: block; margin-bottom: 13px; }.panel-field > span { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; color: #818d83; font-size: 12px; }.panel-field i { color: #c8d2c4; font-style: normal; }.panel-field input[type=range] { width: 100%; accent-color: #9cbe7c; }.panel-field select { width: 100%; height: 36px; padding: 0 9px; color: #eee8db; border: 1px solid #ffffff14; border-radius: 8px; background: #0f1712; }
.panel-hint { margin: 0 0 14px; color: #78847b; font-size: 12px; line-height: 1.6; }
.panel-actions { display: flex; gap: 7px; }.panel-actions button { flex: 1; min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 5px; font-size: 12px; border-radius: 9px; cursor: pointer; }.panel-actions .ghost { color: #aeb8af; border: 1px solid #ffffff14; background: transparent; }.panel-actions .confirm { color: #182116; font-weight: 800; border: 0; background: #aacb88; }.panel-actions .confirm:disabled { opacity: .5; cursor: not-allowed; }
.empty-hint { padding: 22px 10px; text-align: center; color: #657168; font-size: 12px; }
.script-list { display: grid; gap: 8px; }
.script-card { display: grid; grid-template-columns: 1fr auto auto auto; align-items: center; gap: 10px; padding: 14px; border: 1px solid #ffffff11; border-radius: 14px 5px; background: #17211b; }.script-card strong,.script-card small { display: block; }.script-card small { margin-top: 4px; color: #748077; font-size: 12px; }
.mode-chip { padding: 4px 10px; color: #9db982; font-size: 12px; border-radius: 99px; background: #9db98214; }.mode-chip--stage { color: #d99177; background: #d9917714; }
.preview-button { min-height: 34px; display: inline-flex; align-items: center; gap: 6px; padding: 0 12px; color: #cfd8c9; border: 1px solid #ffffff16; border-radius: 9px; background: transparent; cursor: pointer; }.preview-button:hover { border-color: #9cbe7c55; }
@media (max-width: 900px) { .upload-card { grid-template-columns: 1fr; }.asset-columns { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .admin-header { height: auto; min-height: 66px; padding: 10px 14px; }.brand small,.header-actions > a,.notice { display: none; }.admin-body { padding: 22px 14px 80px; }.section-heading { display: block; }.section-heading p { max-width: none; margin-top: 6px; }.upload-fields { grid-template-columns: 1fr; }.script-card { grid-template-columns: 1fr auto; }.preview-button { grid-column: 2; } }
</style>

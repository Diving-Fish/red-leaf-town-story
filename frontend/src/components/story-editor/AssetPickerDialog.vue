<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Ban, ImageUp, Loader2, Move, RotateCcw, Search, Trash2, X } from 'lucide-vue-next'

import { ApiError, api } from '@/api'
import StoryStage from '@/components/story/StoryStage.vue'
import { emptyCast, type StoryCast } from '@/lib/story-stage'
import type { StoryAsset, StoryAssetKind, StoryAssetLayout, StoryUpload, StoryUploadQuota } from '@/types'

const props = defineProps<{
  open: boolean
  kind: StoryAssetKind
  modelValue: string
  assets: StoryAsset[]
  backgrounds: StoryAsset[]
  quota: StoryUploadQuota | null
  emptyLabel?: string
}>()
const emit = defineEmits<{
  'update:modelValue': [string]
  close: []
  changed: []
}>()

const query = ref('')
const scope = ref<'all' | 'official' | 'mine'>('all')
const file = ref<File | null>(null)
const uploadName = ref('')
const busy = ref(false)
const error = ref('')

/** 调整自己上传的立绘的默认站位。null 表示当前在列表态。 */
const editing = ref<StoryAsset | null>(null)
const editName = ref('')
const editLayout = ref<StoryAssetLayout>({ scale: 1, offset_x: 0, offset_y: 0 })

const title = computed(() => (props.kind === 'background' ? '选择背景' : '选择立绘'))
const mineCount = computed(() => props.assets.filter((asset) => asset.source === 'upload').length)

const visible = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return props.assets.filter((asset) => {
    if (scope.value === 'official' && asset.source === 'upload') return false
    if (scope.value === 'mine' && asset.source !== 'upload') return false
    if (!keyword) return true
    return `${asset.name} ${asset.id}`.toLowerCase().includes(keyword)
  })
})

const remaining = computed(() => Math.max(0, (props.quota?.quota_bytes || 0) - (props.quota?.used_bytes || 0)))
const tooBig = computed(() => Boolean(file.value && props.quota && file.value.size > props.quota.max_file_bytes))
const overQuota = computed(() => Boolean(file.value && file.value.size > remaining.value))

/** 预览用真正的舞台渲染，所见即演出时所得。 */
const previewCast = computed<StoryCast>(() => {
  const asset = editing.value
  if (!asset) return emptyCast()
  return {
    left: {
      asset: { ...asset, layouts: { inline: editLayout.value, stage: editLayout.value } },
      scale: editLayout.value.scale,
      offsetX: editLayout.value.offset_x,
      offsetY: editLayout.value.offset_y,
      transition: 'cut',
      duration: 0,
      flip: false,
    },
    center: null,
    right: null,
  }
})
const PREVIEW_BACKGROUND_ID = 'town_gate_dusk'
const previewBackground = computed(() => {
  const usable = props.backgrounds.filter((entry) => entry.url)
  const background = usable.find((entry) => entry.id === PREVIEW_BACKGROUND_ID) || usable[0]
  return background ? { asset: background, transition: 'cut' as const, duration: 0 } : null
})
const previewLine = computed(() => ({
  type: 'dialogue' as const,
  speaker: editName.value || editing.value?.name || '',
  text: '预览台词：确认立绘与对话框的位置关系。',
  focus: 'left' as const,
}))

function megabytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(bytes < 1024 * 1024 ? 2 : 1)} MB`
}

watch(() => props.open, (open) => {
  if (open) return
  query.value = ''
  scope.value = 'all'
  clearFile()
  closeEditor()
  error.value = ''
})

function choose(id: string) {
  emit('update:modelValue', id)
  emit('close')
}

function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0] || null
  file.value = picked
  if (picked && !uploadName.value) uploadName.value = picked.name.replace(/\.[^.]+$/, '').slice(0, 64)
  input.value = ''
  error.value = ''
}

function clearFile() {
  file.value = null
  uploadName.value = ''
}

function openEditor(asset: StoryAsset) {
  editing.value = asset
  editName.value = asset.name
  editLayout.value = { ...(asset.layouts?.stage || { scale: 1, offset_x: 0, offset_y: 0 }) }
  error.value = ''
}

function closeEditor() {
  editing.value = null
  editName.value = ''
}

async function upload() {
  if (!file.value || busy.value || tooBig.value || overQuota.value) return
  busy.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('kind', props.kind)
    form.append('name', uploadName.value.trim() || file.value.name)
    const created = await api<StoryUpload>('/api/red-leaf-town/story/uploads', { method: 'POST', body: form })
    clearFile()
    emit('changed')
    // 背景没有站位可调，直接选用；立绘先进站位调整，调好再选用。
    if (props.kind === 'background') {
      choose(created.id)
      return
    }
    openEditor({
      id: created.id,
      name: created.name,
      asset_key: created.asset_key,
      width: created.width,
      height: created.height,
      url: created.url,
      kind: created.kind,
      source: 'upload',
      layouts: { inline: created.layout, stage: created.layout },
    })
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught.message : '上传失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

async function saveLayout(useIt: boolean) {
  const asset = editing.value
  if (!asset || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/api/red-leaf-town/story/uploads/${encodeURIComponent(asset.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name: editName.value.trim() || asset.name, layout: editLayout.value }),
    })
    emit('changed')
    closeEditor()
    if (useIt) choose(asset.id)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '保存失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

async function remove(asset: StoryAsset) {
  if (busy.value || !window.confirm(`确认删除「${asset.name}」？引用该图的步骤将变为未选图。`)) return
  busy.value = true
  error.value = ''
  try {
    await api(`/api/red-leaf-town/story/uploads/${encodeURIComponent(asset.id)}`, { method: 'DELETE' })
    if (props.modelValue === asset.id) emit('update:modelValue', '')
    emit('changed')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '删除失败，请稍后重试'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="open" class="scrim" @click.self="emit('close')">
    <section class="dialog" :class="`dialog--${kind}`">
      <header>
        <strong>{{ editing ? '调整默认站位' : title }}</strong>
        <template v-if="!editing">
          <label class="search">
            <Search :size="14" />
            <input v-model="query" placeholder="搜索名称" />
          </label>
          <div class="scope">
            <button type="button" :class="{ 'is-active': scope === 'all' }" @click="scope = 'all'">全部</button>
            <button type="button" :class="{ 'is-active': scope === 'official' }" @click="scope = 'official'">公共</button>
            <button type="button" :class="{ 'is-active': scope === 'mine' }" @click="scope = 'mine'">我的上传 {{ mineCount }}</button>
          </div>
        </template>
        <span v-else class="head-note">该站位对所有引用此图的步骤生效。单步微调请在参数面板中设置。</span>
        <button class="close" type="button" @click="editing ? closeEditor() : emit('close')"><X :size="17" /></button>
      </header>

      <!-- 站位调整 -->
      <div v-if="editing" class="editor">
        <div class="editor-stage">
          <StoryStage
            embedded
            hide-caret
            mode="stage"
            :background="previewBackground"
            :portraits="previewCast"
            :line="previewLine"
          />
        </div>
        <div class="editor-fields">
          <label class="field">
            <span>名称</span>
            <input v-model="editName" maxlength="64" placeholder="图片名称" />
          </label>
          <label class="field">
            <span>缩放<i>×{{ editLayout.scale.toFixed(2) }}</i></span>
            <input v-model.number="editLayout.scale" type="range" min="0.4" max="4" step="0.01" />
          </label>
          <label class="field">
            <span>横向偏移<i>{{ editLayout.offset_x.toFixed(2) }}</i></span>
            <input v-model.number="editLayout.offset_x" type="range" min="-0.5" max="0.5" step="0.01" />
          </label>
          <label class="field">
            <span>纵向偏移<i>{{ editLayout.offset_y.toFixed(2) }}</i></span>
            <input v-model.number="editLayout.offset_y" type="range" min="-0.5" max="0.5" step="0.01" />
          </label>
          <p class="field-note">缩放以舞台满高为基准，只改高度，脚下基线不动。</p>
        </div>
      </div>

      <!-- 图片网格 -->
      <div v-else class="grid">
        <button
          v-if="emptyLabel && scope !== 'mine'"
          type="button"
          class="tile tile--empty"
          :class="{ 'is-active': !modelValue }"
          @click="choose('')"
        ><Ban :size="16" /><span>{{ emptyLabel }}</span></button>

        <figure
          v-for="asset in visible"
          :key="asset.id"
          class="tile"
          :class="{ 'is-active': modelValue === asset.id }"
        >
          <button type="button" class="tile-pick" :title="asset.name" @click="choose(asset.id)">
            <img v-if="asset.url" :src="asset.url" :alt="asset.name" loading="lazy" draggable="false" />
            <span class="tile-name">{{ asset.name }}</span>
          </button>
          <div v-if="asset.source === 'upload'" class="tile-tools">
            <button v-if="kind === 'portrait'" type="button" title="调整默认站位" @click.stop="openEditor(asset)"><Move :size="12" /></button>
            <button type="button" title="删除此图" @click.stop="remove(asset)"><Trash2 :size="12" /></button>
          </div>
          <i v-if="asset.source === 'upload'" class="tile-tag">我的</i>
        </figure>

        <p v-if="!visible.length" class="grid-empty">
          {{ query.trim() ? `没有匹配「${query.trim()}」的结果。` : '暂无图片。请在下方上传。' }}
        </p>
      </div>

      <footer v-if="editing">
        <small v-if="error" class="bad">{{ error }}</small>
        <small v-else>调整结果实时反映在左侧预览中。保存后写入该图的默认站位。</small>
        <button type="button" class="ghost" @click="editLayout = { scale: 1, offset_x: 0, offset_y: 0 }">
          <RotateCcw :size="13" />恢复默认值
        </button>
        <button type="button" class="ghost" @click="closeEditor">返回列表</button>
        <button type="button" class="upload" :disabled="busy" @click="saveLayout(true)">
          <Loader2 v-if="busy" :size="14" class="spin" />保存并选用
        </button>
      </footer>

      <footer v-else>
        <label class="file-pick">
          <input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="pickFile" />
          <ImageUp :size="15" />
          <span>{{ file ? file.name : '选择图片' }}</span>
        </label>
        <input v-model="uploadName" class="name-input" maxlength="64" placeholder="图片名称" />
        <button type="button" class="upload" :disabled="!file || busy || tooBig || overQuota" @click="upload">
          <Loader2 v-if="busy" :size="14" class="spin" /><ImageUp v-else :size="14" />上传
        </button>
        <small v-if="error" class="bad">{{ error }}</small>
        <small v-else-if="tooBig" class="bad">单张图片不得超过 {{ megabytes(quota?.max_file_bytes || 0) }}。</small>
        <small v-else-if="overQuota" class="bad">该文件 {{ megabytes(file?.size || 0) }}，超出本小时剩余额度。</small>
        <small v-else>
          上传后转为 WebP 存入 CDN，不保留原图。立绘请使用透明底 PNG。
          本小时剩余额度 {{ megabytes(remaining) }}。上传的图片仅自己可见。
        </small>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.scrim { position: fixed; inset: 0; z-index: 250; display: grid; place-items: center; padding: 24px; background: #050706b8; backdrop-filter: blur(3px); }
.dialog {
  width: min(880px, 100%);
  height: min(660px, 88dvh);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  color: var(--ed-cream, #ece6d9);
  border: 1px solid var(--ed-line-strong, #ffffff2e);
  border-radius: 18px 5px 18px 5px;
  background: var(--ed-panel, #141d18);
  box-shadow: 0 30px 90px #000a;
}
header { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-bottom: 1px solid var(--ed-line, #ffffff14); }
header > strong { flex: 0 0 auto; font-size: 14px; }
.head-note { flex: 1 1 auto; min-width: 0; color: var(--ed-muted, #7d8a80); font-size: 12px; }
.search { flex: 1 1 auto; min-width: 0; display: flex; align-items: center; gap: 7px; padding: 0 10px; color: var(--ed-muted, #7d8a80); border: 1px solid var(--ed-line, #ffffff14); border-radius: 9px 3px 9px 3px; background: var(--ed-well, #0e1612); }
.search input { flex: 1 1 auto; min-width: 0; height: 32px; color: inherit; border: 0; background: transparent; outline: none; }
.search:focus-within { border-color: var(--ed-gold, #d6ad63); }
.scope { flex: 0 0 auto; display: flex; gap: 3px; padding: 3px; border: 1px solid var(--ed-line, #ffffff14); border-radius: 9px 3px 9px 3px; background: var(--ed-well, #0e1612); }
.scope button { min-height: 26px; padding: 0 10px; color: var(--ed-muted, #7d8a80); font-size: 12px; border: 0; border-radius: 6px; background: transparent; cursor: pointer; }
.scope button.is-active { color: #0c1310; font-weight: 600; background: var(--ed-gold, #d6ad63); }
.close { width: 30px; height: 30px; flex: 0 0 auto; display: grid; place-items: center; color: var(--ed-muted, #7d8a80); border: 0; background: transparent; cursor: pointer; }

.grid { overflow-y: auto; padding: 14px; display: grid; gap: 10px; align-content: start; }
.dialog--background .grid { grid-template-columns: repeat(auto-fill, minmax(172px, 1fr)); }
.dialog--portrait .grid { grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); }

.tile { position: relative; margin: 0; border: 1px solid var(--ed-line, #ffffff14); border-radius: 11px 3px 11px 3px; background: var(--ed-well, #0e1612); overflow: hidden; }
.tile.is-active { border-color: var(--ed-gold, #d6ad63); box-shadow: inset 0 0 0 1px var(--ed-gold, #d6ad63); }
.tile-pick { display: block; width: 100%; padding: 0; text-align: left; color: var(--ed-muted, #7d8a80); border: 0; background: transparent; cursor: pointer; }
.tile-pick img { display: block; width: 100%; background: #070b09; }
.dialog--background .tile-pick img { aspect-ratio: 16 / 9; object-fit: cover; }
.dialog--portrait .tile-pick img { aspect-ratio: 3 / 4; object-fit: cover; object-position: top center; }
.tile-name { display: block; padding: 5px 8px 7px; font-size: 11px; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tile:hover { border-color: var(--ed-line-strong, #ffffff2e); }
.tile:hover .tile-pick, .tile.is-active .tile-pick { color: var(--ed-cream, #ece6d9); }
.tile-tools { position: absolute; top: 5px; right: 5px; display: flex; gap: 3px; opacity: 0; }
.tile:hover .tile-tools { opacity: 1; }
.tile-tools button { width: 22px; height: 22px; display: grid; place-items: center; color: #e8d9c6; border: 0; border-radius: 6px; background: #0b100dd8; cursor: pointer; }
.tile-tools button:hover { color: var(--ed-gold, #d6ad63); }
.tile-tools button:last-child:hover { color: var(--ed-alert, #e2907c); }
.tile-tag { position: absolute; top: 5px; left: 5px; padding: 2px 7px; color: #0c1310; font-size: 10px; font-style: normal; border-radius: 99px; background: #9cbe7ccc; }

/* 占位格和图片格等高，内容居中，网格才对得齐 */
.tile--empty { display: grid; place-items: center; align-content: center; gap: 6px; padding: 10px; color: var(--ed-muted, #7d8a80); font-size: 12px; cursor: pointer; }
.dialog--background .tile--empty { aspect-ratio: 16 / 9; }
.dialog--portrait .tile--empty { aspect-ratio: 3 / 4; }
.tile--empty span { padding: 0; text-align: center; }
.grid-empty { grid-column: 1 / -1; margin: 0; padding: 26px 4px; text-align: center; color: var(--ed-muted, #7d8a80); font-size: 12px; }

/* 站位调整：左边真舞台预览，右边滑块——必须同屏，不然拖滑块看不见效果 */
.editor {
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(240px, 1fr);
  gap: 16px;
  align-content: start;
}
/* StoryStage 的根是 container-type: size，尺寸不由内容撑开，所以这里必须给出 16:9 的框 */
.editor-stage { width: 100%; aspect-ratio: 16 / 9; border-radius: 12px 3px 12px 3px; overflow: hidden; background: #050706; }
.editor-fields { display: grid; gap: 11px; align-content: start; }
.field { display: block; }
.field > span { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; color: var(--ed-muted, #7d8a80); font-size: 12px; }
.field i { color: var(--ed-cream, #ece6d9); font-style: normal; font-variant-numeric: tabular-nums; }
.field input[type=range] { width: 100%; accent-color: var(--ed-gold, #d6ad63); }
.field input:not([type=range]) { width: 100%; height: 32px; padding: 0 9px; color: inherit; border: 1px solid var(--ed-line, #ffffff14); border-radius: 9px 3px 9px 3px; background: var(--ed-well, #0e1612); outline: none; }
.field input:focus-visible { border-color: var(--ed-gold, #d6ad63); }
.field-note { margin: 0; color: #616c64; font-size: 11px; line-height: 1.7; }

footer { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 11px 14px; border-top: 1px solid var(--ed-line, #ffffff14); }
.file-pick { display: inline-flex; align-items: center; gap: 6px; max-width: 260px; padding: 0 11px; height: 32px; color: var(--ed-muted, #7d8a80); font-size: 12px; border: 1px dashed var(--ed-line-strong, #ffffff2e); border-radius: 9px 3px 9px 3px; cursor: pointer; }
.file-pick span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-pick:hover { color: var(--ed-cream, #ece6d9); border-color: var(--ed-gold, #d6ad63); }
.name-input { width: 200px; height: 32px; padding: 0 9px; color: inherit; border: 1px solid var(--ed-line, #ffffff14); border-radius: 9px 3px 9px 3px; background: var(--ed-well, #0e1612); outline: none; }
.name-input:focus-visible { border-color: var(--ed-gold, #d6ad63); }
.upload { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 14px; color: #0c1310; font-size: 12px; font-weight: 700; border: 0; border-radius: 9px 3px 9px 3px; background: var(--ed-gold, #d6ad63); cursor: pointer; }
.upload:disabled { opacity: .4; cursor: not-allowed; }
.ghost { display: inline-flex; align-items: center; gap: 5px; height: 32px; padding: 0 12px; color: var(--ed-muted, #7d8a80); font-size: 12px; border: 1px solid var(--ed-line, #ffffff14); border-radius: 9px 3px 9px 3px; background: transparent; cursor: pointer; }
.ghost:hover { color: var(--ed-cream, #ece6d9); border-color: var(--ed-line-strong, #ffffff2e); }
footer small { flex: 1 1 240px; min-width: 0; color: #616c64; font-size: 11px; line-height: 1.6; }
footer small.bad { color: var(--ed-alert, #e2907c); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
</style>

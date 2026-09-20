<script setup lang="ts">
import { computed, ref } from 'vue'
import { Ban, FlipHorizontal2, ImageOff, Images, RotateCcw } from 'lucide-vue-next'

import AssetPickerDialog from '@/components/story-editor/AssetPickerDialog.vue'
import { blankLayout, MAX_SPEAKER, MAX_TEXT, stepAsset, type DraftStep, type ResourceIndex } from '@/lib/story-draft'
import type { StoryUploadQuota } from '@/types'

const props = defineProps<{
  step: DraftStep
  resources: ResourceIndex
  speakers: string[]
  quota: StoryUploadQuota | null
}>()
const emit = defineEmits<{
  patch: [label: string, patch: Record<string, unknown>]
  resourcesChanged: []
}>()

const SLOTS = [{ id: 'left', name: '左侧' }, { id: 'center', name: '居中' }, { id: 'right', name: '右侧' }] as const

const SLOT_NAMES: Record<string, string> = { left: '左侧', center: '居中', right: '右侧' }

const picking = ref(false)
const chosen = computed(() => stepAsset(props.step, props.resources))

function set(label: string, patch: Record<string, unknown>) {
  emit('patch', label, patch)
}

const dialogue = computed(() => (props.step.type === 'dialogue' ? props.step : null))
const background = computed(() => (props.step.type === 'background' ? props.step : null))
const portrait = computed(() => (props.step.type === 'portrait' ? props.step : null))

const portraitSource = computed(() => (portrait.value?.partner_id ? 'partner' : 'asset'))
const selectedPartner = computed(() =>
  props.resources.partners.find((entry) => entry.id === portrait.value?.partner_id) || null,
)
/** 站位默认跟着素材走，勾了才在这一步单独覆盖。 */
const layout = computed(() => portrait.value?.layout)
const assetDefaults = computed(() => {
  const source = portrait.value?.asset_id ? props.resources.assets.get(portrait.value.asset_id) : null
  return source?.layouts?.stage || blankLayout()
})

function chooseSource(kind: 'asset' | 'partner') {
  if (kind === portraitSource.value) return
  set('立绘来源', kind === 'asset'
    ? { asset_id: '', partner_id: '', breakthrough: 0 }
    : { asset_id: '', partner_id: props.resources.partners[0]?.id || '', breakthrough: 0 })
}

function toggleLayout(enabled: boolean) {
  set('立绘站位', { layout: enabled ? { ...assetDefaults.value } : null })
}

function patchLayout(key: 'scale' | 'offset_x' | 'offset_y', value: number) {
  set(`立绘${key}`, { layout: { ...(layout.value || assetDefaults.value), [key]: value } })
}
</script>

<template>
  <div class="inspector">
    <!-- 对话 -->
    <template v-if="dialogue">
      <div class="row row--split">
        <label class="field">
          <span class="field-label">说话人</span>
          <input
            :value="dialogue.speaker"
            list="story-editor-speakers"
            :maxlength="MAX_SPEAKER"
            placeholder="留空为旁白"
            @input="set('说话人', { speaker: ($event.target as HTMLInputElement).value })"
          />
        </label>
        <div class="field">
          <span class="field-label">名牌位置</span>
          <div class="segmented" :class="{ 'is-disabled': !dialogue.speaker }">
            <button
              v-for="option in [{ id: 'left', name: '靠左' }, { id: 'right', name: '靠右' }]"
              :key="option.id"
              type="button"
              :class="{ 'is-active': (dialogue.focus === 'right' ? 'right' : 'left') === option.id }"
              :disabled="!dialogue.speaker"
              @click="set('名牌位置', { focus: option.id })"
            >{{ option.name }}</button>
          </div>
        </div>
      </div>
      <label class="field">
        <span class="field-label">
          台词
          <i :class="{ 'is-over': dialogue.text.length > MAX_TEXT }">{{ dialogue.text.length }} / {{ MAX_TEXT }}</i>
        </span>
        <textarea
          class="line-input"
          :value="dialogue.text"
          rows="4"
          :placeholder="dialogue.speaker ? `${dialogue.speaker}的台词` : '旁白内容'"
          @input="set('台词', { text: ($event.target as HTMLTextAreaElement).value })"
        />
      </label>
      <p v-if="!dialogue.speaker" class="hint">留空说话人即为旁白：文本以斜体显示，不绘制名牌。</p>
    </template>

    <!-- 背景 -->
    <template v-else-if="background">
      <div class="field">
        <span class="field-label">背景素材</span>
        <button type="button" class="chosen chosen--wide" @click="picking = true">
          <img v-if="chosen?.url" :src="chosen.url" :alt="chosen.name" />
          <span v-else class="chosen-blank"><Ban v-if="!background.asset_id" :size="18" /><ImageOff v-else :size="18" /></span>
          <span class="chosen-meta">
            <strong>{{ chosen?.name || (background.asset_id ? '图片已不存在' : '不使用背景') }}</strong>
            <small><Images :size="12" />点击选择，共 {{ resources.backgrounds.length }} 张可用</small>
          </span>
        </button>
      </div>
      <div class="row row--split">
        <div class="field">
          <span class="field-label">转场</span>
          <div class="segmented">
            <button
              v-for="option in [{ id: 'fade', name: '淡入' }, { id: 'cut', name: '直切' }]"
              :key="option.id"
              type="button"
              :class="{ 'is-active': background.transition === option.id }"
              @click="set('背景转场', { transition: option.id })"
            >{{ option.name }}</button>
          </div>
        </div>
        <label class="field" :class="{ 'is-muted': background.transition === 'cut' }">
          <span class="field-label">时长 <i>{{ background.duration.toFixed(2) }}s</i></span>
          <input
            type="range" min="0" max="3" step="0.05"
            :value="background.duration"
            :disabled="background.transition === 'cut'"
            @input="set('背景时长', { duration: Number(($event.target as HTMLInputElement).value) })"
          />
        </label>
      </div>
      <p v-if="!background.asset_id" class="hint">不选素材表示移除当前背景，画面转为黑场。剧本至少需要一个已选图的背景步骤，否则不会全屏演出。</p>
    </template>

    <!-- 立绘 -->
    <template v-else-if="portrait">
      <div class="row row--triple">
        <div class="field">
          <span class="field-label">这一步</span>
          <div class="segmented">
            <button type="button" :class="{ 'is-active': portrait.visible }" @click="set('立绘显隐', { visible: true })">出场</button>
            <button type="button" :class="{ 'is-active': !portrait.visible }" @click="set('立绘显隐', { visible: false })">退场</button>
          </div>
        </div>
        <div class="field">
          <span class="field-label">站位</span>
          <div class="segmented">
            <button
              v-for="option in SLOTS"
              :key="option.id"
              type="button"
              :class="{ 'is-active': portrait.slot === option.id }"
              @click="set('立绘槽位', { slot: option.id })"
            >{{ option.name }}</button>
          </div>
        </div>
        <div v-if="portrait.visible" class="field">
          <span class="field-label">朝向</span>
          <button
            type="button"
            class="toggle"
            :class="{ 'is-active': portrait.flip }"
            @click="set('立绘翻转', { flip: !portrait.flip })"
          ><FlipHorizontal2 :size="14" />{{ portrait.flip ? '已水平翻转' : '原图朝向' }}</button>
        </div>
      </div>

      <p v-if="!portrait.visible" class="hint">
        退场步骤仅收起{{ SLOT_NAMES[portrait.slot] }}立绘。淡出时长沿用该立绘出场时的转场设置。
      </p>

      <template v-else>
        <div class="field">
          <span class="field-label">
            图片来源
            <span class="source-switch">
              <button type="button" :class="{ 'is-active': portraitSource === 'asset' }" @click="chooseSource('asset')">素材库</button>
              <button type="button" :class="{ 'is-active': portraitSource === 'partner' }" @click="chooseSource('partner')">伙伴插画</button>
            </span>
          </span>
          <button v-if="portraitSource === 'asset'" type="button" class="chosen chosen--tall" @click="picking = true">
            <img v-if="chosen?.url" :src="chosen.url" :alt="chosen.name" />
            <span v-else class="chosen-blank"><ImageOff :size="18" /></span>
            <span class="chosen-meta">
              <strong>{{ chosen?.name || '未选择图片' }}</strong>
              <small><Images :size="12" />点击选择，共 {{ resources.portraits.length }} 张可用</small>
            </span>
          </button>
          <div v-else class="partner-row">
            <select
              :value="portrait.partner_id"
              @change="set('立绘伙伴', { partner_id: ($event.target as HTMLSelectElement).value, breakthrough: 0 })"
            >
              <option v-for="entry in resources.partners" :key="entry.id" :value="entry.id">{{ entry.name }}</option>
            </select>
            <div class="segmented">
              <button
                v-for="artwork in selectedPartner?.artworks || []"
                :key="artwork.breakthrough"
                type="button"
                :class="{ 'is-active': portrait.breakthrough === artwork.breakthrough }"
                @click="set('立绘突破', { breakthrough: artwork.breakthrough })"
              >{{ artwork.breakthrough === 0 ? '初始' : `${artwork.breakthrough} 破` }}</button>
            </div>
          </div>
        </div>

        <div class="row row--split">
          <div class="field">
            <span class="field-label">转场</span>
            <div class="segmented">
              <button
                v-for="option in [{ id: 'fade', name: '淡入' }, { id: 'slide', name: '滑入' }, { id: 'cut', name: '直切' }]"
                :key="option.id"
                type="button"
                :class="{ 'is-active': portrait.transition === option.id }"
                @click="set('立绘转场', { transition: option.id })"
              >{{ option.name }}</button>
            </div>
          </div>
          <label class="field" :class="{ 'is-muted': portrait.transition === 'cut' }">
            <span class="field-label">时长 <i>{{ portrait.duration.toFixed(2) }}s</i></span>
            <input
              type="range" min="0" max="3" step="0.02"
              :value="portrait.duration"
              :disabled="portrait.transition === 'cut'"
              @input="set('立绘时长', { duration: Number(($event.target as HTMLInputElement).value) })"
            />
          </label>
        </div>

        <div class="field">
          <span class="field-label">
            位置与缩放
            <span class="source-switch">
              <button type="button" :class="{ 'is-active': !layout }" @click="toggleLayout(false)">沿用素材默认</button>
              <button type="button" :class="{ 'is-active': Boolean(layout) }" @click="toggleLayout(true)">本步单独调整</button>
            </span>
          </span>
          <div v-if="layout" class="sliders">
            <label>
              <span>缩放 <i>×{{ layout.scale.toFixed(2) }}</i></span>
              <input type="range" min="0.2" max="4" step="0.01" :value="layout.scale" @input="patchLayout('scale', Number(($event.target as HTMLInputElement).value))" />
            </label>
            <label>
              <span>横向 <i>{{ layout.offset_x.toFixed(2) }}</i></span>
              <input type="range" min="-1.5" max="1.5" step="0.01" :value="layout.offset_x" @input="patchLayout('offset_x', Number(($event.target as HTMLInputElement).value))" />
            </label>
            <label>
              <span>纵向 <i>{{ layout.offset_y.toFixed(2) }}</i></span>
              <input type="range" min="-0.8" max="0.8" step="0.01" :value="layout.offset_y" @input="patchLayout('offset_y', Number(($event.target as HTMLInputElement).value))" />
            </label>
            <button type="button" class="reset" @click="set('立绘站位', { layout: { ...assetDefaults } })">
              <RotateCcw :size="13" />恢复素材默认值
            </button>
          </div>
          <p v-else class="hint">
            当前沿用该素材的默认站位（×{{ assetDefaults.scale.toFixed(2) }}）。选择「本步单独调整」后仅影响当前步骤，横向偏移可将立绘移出画面。
          </p>
        </div>
      </template>
    </template>

    <datalist id="story-editor-speakers">
      <option v-for="name in speakers" :key="name" :value="name" />
    </datalist>

    <AssetPickerDialog
      v-if="step.type !== 'dialogue'"
      :open="picking"
      :kind="step.type === 'background' ? 'background' : 'portrait'"
      :model-value="step.asset_id"
      :assets="step.type === 'background' ? resources.backgrounds : resources.portraits"
      :backgrounds="resources.backgrounds"
      :quota="quota"
      :empty-label="step.type === 'background' ? '撤掉背景' : undefined"
      @update:model-value="set(step.type === 'background' ? '背景素材' : '立绘素材', step.type === 'background' ? { asset_id: $event } : { asset_id: $event, partner_id: '' })"
      @changed="emit('resourcesChanged')"
      @close="picking = false"
    />
  </div>
</template>

<style scoped>
.inspector { display: grid; align-content: start; gap: 11px; }
.row { display: grid; gap: 10px; }
.row--split { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.row--triple { grid-template-columns: repeat(3, minmax(0, 1fr)); }

.field { display: block; min-width: 0; }
.field.is-muted { opacity: .45; }
.field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 5px;
  color: var(--ed-muted);
  font-size: 12px;
}
.field-label i { color: var(--ed-cream); font-style: normal; font-variant-numeric: tabular-nums; }
.field-label i.is-over { color: var(--ed-alert); }

input[type=text], input:not([type]), select, textarea {
  width: 100%;
  padding: 7px 9px;
  color: var(--ed-cream);
  border: 1px solid var(--ed-line);
  border-radius: 9px 3px 9px 3px;
  background: var(--ed-well);
  outline: none;
}
input:not([type]):focus-visible, select:focus-visible, textarea:focus-visible { border-color: var(--ed-gold); }
.line-input { font-family: Georgia, 'Noto Serif SC', 'Songti SC', serif; font-size: 14px; line-height: 1.85; resize: vertical; }
select { height: 32px; padding: 0 8px; }
input[type=range] { width: 100%; accent-color: var(--ed-gold); }

.segmented { display: flex; gap: 3px; padding: 3px; border: 1px solid var(--ed-line); border-radius: 9px 3px 9px 3px; background: var(--ed-well); }
.segmented button {
  flex: 1;
  min-height: 25px;
  padding: 0 6px;
  color: var(--ed-muted);
  font-size: 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}
.segmented button.is-active { color: var(--ed-ground); background: var(--ed-gold); font-weight: 600; }
.segmented.is-disabled { opacity: .4; }
.segmented button:disabled { cursor: not-allowed; }

.toggle {
  width: 100%;
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--ed-muted);
  font-size: 12px;
  border: 1px solid var(--ed-line);
  border-radius: 9px 3px 9px 3px;
  background: var(--ed-well);
  cursor: pointer;
}
.toggle.is-active { color: var(--ed-gold); border-color: var(--ed-gold); }

.source-switch { display: inline-flex; gap: 3px; }
.source-switch button {
  padding: 3px 9px;
  color: var(--ed-muted);
  font-size: 11px;
  border: 1px solid transparent;
  border-radius: 99px;
  background: transparent;
  cursor: pointer;
}
.source-switch button.is-active { color: var(--ed-gold); border-color: var(--ed-line-strong); background: var(--ed-well); }

.partner-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 8px; }

.sliders { display: grid; gap: 9px; }
.sliders label { display: block; }
.sliders label > span { display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px; color: var(--ed-muted); font-size: 12px; }
.sliders i { color: var(--ed-cream); font-style: normal; font-variant-numeric: tabular-nums; }
.reset {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  color: var(--ed-muted);
  font-size: 12px;
  border: 1px solid var(--ed-line);
  border-radius: 99px;
  background: transparent;
  cursor: pointer;
}
.reset:hover { color: var(--ed-cream); border-color: var(--ed-line-strong); }

.hint { margin: 0; color: var(--ed-muted); font-size: 12px; line-height: 1.7; }

/* 当前选中的图：缩略图 + 名字，点开才是完整的选图弹窗 */
.chosen {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 7px;
  text-align: left;
  border: 1px solid var(--ed-line);
  border-radius: 11px 3px 11px 3px;
  background: var(--ed-well);
  cursor: pointer;
}
.chosen:hover { border-color: var(--ed-gold); }
.chosen img, .chosen-blank {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 8px 2px 8px 2px;
  background: #070b09;
  object-fit: cover;
  color: var(--ed-muted);
}
.chosen--wide img, .chosen--wide .chosen-blank { width: 104px; aspect-ratio: 16 / 9; }
.chosen--tall img, .chosen--tall .chosen-blank { width: 58px; aspect-ratio: 3 / 4; object-position: top center; }
.chosen-meta { min-width: 0; }
.chosen-meta strong { display: block; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chosen-meta small { display: flex; align-items: center; gap: 5px; margin-top: 4px; color: var(--ed-muted); font-size: 11px; }

@media (max-width: 900px) {
  .row--split, .row--triple, .partner-row { grid-template-columns: 1fr; }
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Check, ImageUp, Leaf, LockKeyhole, Plus, Save, Trash2 } from 'lucide-vue-next'

import { api, ApiError } from '@/api'
import PartnerAvatar from '@/components/PartnerAvatar.vue'
import PartnerGrantPanel from '@/components/admin/PartnerGrantPanel.vue'
import ImageCropper from '@/components/ImageCropper.vue'
import type {
  CropRect,
  GrowthCurveId,
  IndustryId,
  PartnerAdminOptions,
  PartnerAdminPayload,
  PartnerArtwork,
  PartnerDefinition,
} from '@/types'

interface PendingArtwork {
  stage: number
  file: File
  objectUrl: string
  imageWidth: number
  imageHeight: number
  x: number
  y: number
  w: number
  h: number
}

const TOKEN_KEY = 'red_leaf_town_admin_token'
const token = ref(localStorage.getItem(TOKEN_KEY) || '')
const tokenInput = ref(token.value)
const authenticated = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const partners = ref<PartnerDefinition[]>([])
const options = ref<PartnerAdminOptions | null>(null)
const selectedId = ref('')
const editor = ref<PartnerDefinition>(blankPartner())
const uploadingStage = ref<number | null>(null)
const pendingArtwork = ref<PendingArtwork | null>(null)
const activeAvatarStage = ref(0)
const adminSection = ref<'cards' | 'grants'>('cards')

const selectedExists = computed(() => partners.value.some((partner) => partner.id === editor.value.id))
const activeAvatarArtwork = computed(() => artworkFor(activeAvatarStage.value))
const activeAvatarCrop = computed<CropRect>({
  get() {
    const crop = editor.value.avatar_crops.find((entry) => entry.breakthrough === activeAvatarStage.value)
    return crop ? { x: crop.x, y: crop.y, w: crop.w, h: crop.h } : { x: 0, y: 0, w: 1, h: 1 }
  },
  set(value) {
    const crop = editor.value.avatar_crops.find((entry) => entry.breakthrough === activeAvatarStage.value)
    if (crop) Object.assign(crop, value)
  },
})
const pendingArtworkCrop = computed<CropRect>({
  get() {
    const pending = pendingArtwork.value
    return pending ? { x: pending.x, y: pending.y, w: pending.w, h: pending.h } : { x: 0, y: 0, w: 9, h: 16 }
  },
  set(value) {
    if (pendingArtwork.value) Object.assign(pendingArtwork.value, value)
  },
})
const artworkCropError = computed(() => {
  const crop = pendingArtwork.value
  if (!crop) return ''
  const values = [crop.x, crop.y, crop.w, crop.h]
  if (values.some((value) => !Number.isInteger(value))) return '裁剪坐标必须是整数'
  if (crop.x < 0 || crop.y < 0 || crop.w <= 0 || crop.h <= 0) return '裁剪坐标超出允许范围'
  if (crop.x + crop.w > crop.imageWidth || crop.y + crop.h > crop.imageHeight) return '裁剪框不能超出原图边界'
  if (crop.w * 16 !== crop.h * 9) return '裁剪框必须严格保持 9:16'
  return ''
})

function blankPartner(): PartnerDefinition {
  return {
    id: '',
    name: '',
    rarity: 3,
    description: '',
    growth_curve: 'linear',
    tendencies: [{ industry: 'farming', level_1: 10, level_60: 60 }],
    trait_codes: [],
    artworks: [],
    avatar_crops: [0, 1, 2].map((breakthrough) => ({ breakthrough, x: 0, y: 0, w: 1, h: 1 })),
    ascensions: [],
  }
}

function headers(json = true): Record<string, string> {
  return {
    'X-Admin-Token': token.value,
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  }
}

async function loadCatalog(selectId = selectedId.value) {
  error.value = ''
  try {
    const payload = await api<PartnerAdminPayload>('/api/red-leaf-town/admin/partners', { headers: headers() })
    partners.value = payload.partners
    options.value = payload.options
    authenticated.value = true
    if (selectId && payload.partners.some((partner) => partner.id === selectId)) selectPartner(selectId)
    else if (payload.partners.length) selectPartner(payload.partners[0].id)
    else createNew()
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
  await loadCatalog()
}

function selectPartner(id: string) {
  const partner = partners.value.find((entry) => entry.id === id)
  if (!partner) return
  selectedId.value = id
  editor.value = JSON.parse(JSON.stringify(partner)) as PartnerDefinition
  error.value = ''
}

function createNew() {
  selectedId.value = ''
  editor.value = blankPartner()
  error.value = ''
}

function tendencyFor(industry: IndustryId) {
  return editor.value.tendencies.find((entry) => entry.industry === industry)
}

function toggleTendency(industry: IndustryId, checked: boolean) {
  if (checked) {
    if (!tendencyFor(industry) && editor.value.tendencies.length < 3) {
      editor.value.tendencies.push({ industry, level_1: 10, level_60: 60 })
    }
  } else if (editor.value.tendencies.length > 1) {
    editor.value.tendencies = editor.value.tendencies.filter((entry) => entry.industry !== industry)
  }
}

function toggleTrait(code: string, checked: boolean) {
  if (checked && !editor.value.trait_codes.includes(code)) editor.value.trait_codes.push(code)
  if (!checked) editor.value.trait_codes = editor.value.trait_codes.filter((entry) => entry !== code)
}

function artworkFor(stage: number): PartnerArtwork | undefined {
  return editor.value.artworks.find((artwork) => artwork.breakthrough === stage)
}

function initialArtworkFor(partner: PartnerDefinition) {
  return partner.artworks.find((artwork) => artwork.breakthrough === 0)
}

function initialAvatarCropFor(partner: PartnerDefinition) {
  return partner.avatar_crops.find((crop) => crop.breakthrough === 0)
}

function cleanPayload(): PartnerDefinition {
  return {
    id: editor.value.id.trim(),
    name: editor.value.name.trim(),
    rarity: editor.value.rarity,
    description: editor.value.description.trim(),
    growth_curve: editor.value.growth_curve as GrowthCurveId,
    tendencies: editor.value.tendencies.map((entry) => ({
      industry: entry.industry,
      level_1: Number(entry.level_1),
      level_60: Number(entry.level_60),
    })),
    trait_codes: [...editor.value.trait_codes],
    artworks: editor.value.artworks.map(({ breakthrough, asset_key, width, height, content_type }) => ({
      breakthrough, asset_key, width, height, content_type,
    })),
    avatar_crops: editor.value.avatar_crops.map((crop) => ({
      breakthrough: Number(crop.breakthrough),
      x: Number(crop.x),
      y: Number(crop.y),
      w: Number(crop.w),
      h: Number(crop.h),
    })),
    ascensions: editor.value.ascensions || [],
  }
}

async function save(): Promise<boolean> {
  if (busy.value) return false
  busy.value = true
  error.value = ''
  try {
    const payload = cleanPayload()
    const exists = partners.value.some((partner) => partner.id === payload.id)
    const path = exists
      ? `/api/red-leaf-town/admin/partners/${encodeURIComponent(payload.id)}`
      : '/api/red-leaf-town/admin/partners'
    const saved = await api<PartnerDefinition>(path, {
      method: exists ? 'PUT' : 'POST',
      headers: headers(),
      body: JSON.stringify(payload),
    })
    selectedId.value = saved.id
    notice.value = '伙伴卡片已保存'
    await loadCatalog(saved.id)
    window.setTimeout(() => (notice.value = ''), 2200)
    return true
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '保存失败'
    return false
  } finally {
    busy.value = false
  }
}

async function chooseArtwork(stage: number, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  error.value = ''
  const objectUrl = URL.createObjectURL(file)
  try {
    const image = new window.Image()
    image.src = objectUrl
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('无法读取所选图片'))
    })
    const unit = Math.min(Math.floor(image.naturalWidth / 9), Math.floor(image.naturalHeight / 16))
    if (unit < 1) throw new Error('图片尺寸太小，无法裁剪为 9:16')
    const w = unit * 9
    const h = unit * 16
    pendingArtwork.value = {
      stage,
      file,
      objectUrl,
      imageWidth: image.naturalWidth,
      imageHeight: image.naturalHeight,
      x: Math.floor((image.naturalWidth - w) / 2),
      y: Math.floor((image.naturalHeight - h) / 2),
      w,
      h,
    }
  } catch (caught) {
    URL.revokeObjectURL(objectUrl)
    error.value = caught instanceof Error ? caught.message : '无法读取所选图片'
  }
}

function closeArtworkCrop() {
  if (pendingArtwork.value) URL.revokeObjectURL(pendingArtwork.value.objectUrl)
  pendingArtwork.value = null
}

async function confirmArtworkUpload() {
  const pending = pendingArtwork.value
  if (!pending || artworkCropError.value) return
  if (!selectedExists.value && !(await save())) return
  uploadingStage.value = pending.stage
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', pending.file)
    form.append('x', String(pending.x))
    form.append('y', String(pending.y))
    form.append('w', String(pending.w))
    form.append('h', String(pending.h))
    const response = await fetch(
      `/api/red-leaf-town/admin/partners/${encodeURIComponent(editor.value.id)}/artworks/${pending.stage}`,
      { method: 'POST', headers: headers(false), body: form },
    )
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new ApiError(body.message || '图片上传失败', response.status, body.code)
    notice.value = `突破阶段 ${pending.stage} 的插画已裁剪为 WebP 并上传到 CDN`
    activeAvatarStage.value = pending.stage
    closeArtworkCrop()
    await loadCatalog(editor.value.id)
    window.setTimeout(() => (notice.value = ''), 2600)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '图片上传失败'
  } finally {
    uploadingStage.value = null
  }
}

async function removePartner() {
  if (!selectedExists.value || !window.confirm(`确认删除伙伴“${editor.value.name}”吗？`)) return
  busy.value = true
  try {
    await api<unknown>(`/api/red-leaf-town/admin/partners/${encodeURIComponent(editor.value.id)}`, {
      method: 'DELETE',
      headers: headers(),
    })
    notice.value = '伙伴卡片已删除'
    await loadCatalog()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '删除失败'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  if (token.value) loadCatalog()
})
</script>

<template>
  <main class="admin-page">
    <section v-if="!authenticated" class="unlock-card">
      <div class="admin-seal"><LockKeyhole :size="34" /></div>
      <p class="kicker">RED LEAF TOWN ADMIN</p>
      <h1>伙伴卡片管理</h1>
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
        <div class="brand"><span><Leaf :size="22" /></span><div><strong>红叶镇后台</strong><small>伙伴卡片管理</small></div></div>
        <nav class="admin-section-tabs" aria-label="后台功能">
          <button :class="{ active: adminSection === 'cards' }" @click="adminSection = 'cards'">卡片配置</button>
          <button :class="{ active: adminSection === 'grants' }" @click="adminSection = 'grants'">玩家存档</button>
        </nav>
        <div class="header-actions">
          <span v-if="notice" class="notice"><Check :size="15" />{{ notice }}</span>
          <RouterLink :to="{ name: 'admin-crops' }">作物数值</RouterLink>
          <RouterLink :to="{ name: 'admin-mail' }">镇邮局</RouterLink>
          <a href="/red-leaf-town/"><ArrowLeft :size="16" />玩家前台</a>
          <button v-if="adminSection === 'cards'" class="save-button" :disabled="busy" @click="save"><Save :size="16" />保存卡片</button>
        </div>
      </header>

      <div v-if="adminSection === 'cards'" class="admin-layout">
        <aside class="partner-list">
          <div class="list-heading"><div><small>PARTNER CATALOG</small><strong>伙伴列表</strong></div><button @click="createNew"><Plus :size="18" /></button></div>
          <button
            v-for="partner in partners"
            :key="partner.id"
            class="partner-list-item"
            :class="{ active: selectedId === partner.id }"
            @click="selectPartner(partner.id)"
          >
            <PartnerAvatar
              class="mini-avatar"
              :artwork="initialArtworkFor(partner)"
              :crop="initialAvatarCropFor(partner)"
              :name="partner.name"
              :size="38"
            >
              <Leaf :size="17" />
            </PartnerAvatar>
            <span><strong>{{ partner.name }}</strong><small>{{ partner.id }} · {{ partner.rarity }} 星</small></span>
            <i :class="{ complete: partner.complete }">{{ partner.complete ? '完整' : '缺图' }}</i>
          </button>
          <div v-if="!partners.length" class="empty-list">还没有伙伴卡片</div>
        </aside>

        <section class="editor-panel">
          <div class="editor-title">
            <div><p class="kicker">CARD DEFINITION</p><h1>{{ selectedExists ? editor.name || '未命名伙伴' : '新建伙伴' }}</h1></div>
            <button v-if="selectedExists" class="delete-button" :disabled="busy" @click="removePartner"><Trash2 :size="16" />删除</button>
          </div>
          <p v-if="error" class="editor-error">{{ error }}</p>

          <div class="form-card basic-grid">
            <label><span>稳定 ID</span><input v-model="editor.id" :disabled="selectedExists" placeholder="maple_sprite" /></label>
            <label><span>名称</span><input v-model="editor.name" placeholder="伙伴名称" /></label>
            <label><span>星级</span><select v-model.number="editor.rarity"><option v-for="rarity in options?.rarities" :key="rarity" :value="rarity">{{ rarity }} 星</option></select></label>
            <label><span>成长曲线</span><select v-model="editor.growth_curve"><option v-for="curve in options?.growth_curves" :key="curve.id" :value="curve.id">{{ curve.name }}</option></select></label>
            <label class="wide"><span>简介</span><textarea v-model="editor.description" rows="3" placeholder="伙伴的定位或设计备注" /></label>
          </div>

          <div class="section-heading"><div><small>TENDENCIES & GROWTH</small><h2>产业倾向与能力</h2></div><p>最多三项；等级上限随突破阶段依次为 20 / 40 / 60。</p></div>
          <div class="tendency-grid">
            <article v-for="industry in options?.industries" :key="industry.id" :class="{ enabled: tendencyFor(industry.id) }">
              <label class="industry-toggle"><input type="checkbox" :checked="!!tendencyFor(industry.id)" @change="toggleTendency(industry.id, ($event.target as HTMLInputElement).checked)" /><span>{{ industry.name }}</span></label>
              <template v-if="tendencyFor(industry.id)">
                <label><span>1 级能力</span><input v-model.number="tendencyFor(industry.id)!.level_1" type="number" min="0" /></label>
                <label><span>60 级能力</span><input v-model.number="tendencyFor(industry.id)!.level_60" type="number" min="0" /></label>
                <div class="ability-preview">
                  <span v-for="level in [1, 20, 40, 60]" :key="level">Lv.{{ level }}<strong>{{ editor.ability_preview?.[industry.id]?.[String(level)] ?? '保存后预览' }}</strong></span>
                </div>
              </template>
            </article>
          </div>

          <div class="section-heading"><div><small>PYTHON TRAITS</small><h2>特性代号</h2></div><p>配置仅保存代号；具体效果由 Python 注册并在结算阶段执行。</p></div>
          <div class="trait-grid">
            <label v-for="trait in options?.traits" :key="trait.code" :class="{ checked: editor.trait_codes.includes(trait.code) }">
              <input type="checkbox" :checked="editor.trait_codes.includes(trait.code)" @change="toggleTrait(trait.code, ($event.target as HTMLInputElement).checked)" />
              <strong>{{ trait.name }}</strong><span>{{ trait.description }}</span><i>{{ trait.implemented ? '已实现' : '待接入' }}</i>
            </label>
          </div>

          <div class="section-heading"><div><small>9:16 ARTWORKS</small><h2>突破插画</h2></div><p :class="{ 'cdn-warning': !options?.cdn.configured }">{{ options?.cdn.configured ? `当前使用 ${options.cdn.provider} CDN provider，应用服务器不直接分发原图。` : '当前 CDN provider 未配置，图片暂时无法上传。' }}</p></div>
          <div class="artwork-grid">
            <article v-for="stage in [0, 1, 2]" :key="stage" class="artwork-card">
              <div class="artwork-frame">
                <img v-if="artworkFor(stage)?.url" :src="artworkFor(stage)?.url || ''" :alt="`突破阶段 ${stage}`" />
                <div v-else><ImageUp :size="30" /><span>9 : 16</span></div>
              </div>
              <div class="artwork-meta"><strong>{{ stage === 0 ? '初始形态' : `${stage} 次突破` }}</strong><small>等级上限 {{ options?.breakthrough_level_caps[stage] }}</small></div>
              <label class="upload-button" :class="{ disabled: uploadingStage !== null }">
                <ImageUp :size="15" />{{ uploadingStage === stage ? '上传中…' : artworkFor(stage) ? '替换并裁剪' : '选择并裁剪' }}
                <input type="file" accept="image/png,image/jpeg,image/webp" :disabled="uploadingStage !== null" @change="chooseArtwork(stage, $event)" />
              </label>
            </article>
          </div>

          <div class="section-heading"><div><small>AVATAR CROPS</small><h2>各突破阶段头像</h2></div><p>每个形态独立保存裁剪框；在图片上拖动选区和四角即可调整。</p></div>
          <div class="avatar-crop-card">
            <div class="avatar-stage-tabs">
              <button v-for="stage in [0, 1, 2]" :key="stage" :class="{ active: activeAvatarStage === stage }" @click="activeAvatarStage = stage">
                <span>{{ stage === 0 ? '初始形态' : `${stage} 次突破` }}</span>
                <small>{{ artworkFor(stage) ? '独立裁剪' : '请先上传插画' }}</small>
              </button>
            </div>
            <div v-if="activeAvatarArtwork?.url" class="avatar-crop-workspace">
              <ImageCropper
                v-model="activeAvatarCrop"
                :image-url="activeAvatarArtwork.url || ''"
                :image-width="activeAvatarArtwork.width"
                :image-height="activeAvatarArtwork.height"
                :aspect-width="1"
                :aspect-height="1"
              />
              <div class="avatar-crop-summary">
                <strong>{{ activeAvatarStage === 0 ? '初始形态' : `${activeAvatarStage} 次突破` }}头像</strong>
                <span>选区 {{ activeAvatarCrop.w }} × {{ activeAvatarCrop.h }}</span>
                <p>裁剪坐标会随“保存卡片”写入配置，不生成额外头像文件。</p>
              </div>
            </div>
            <div v-else class="avatar-crop-empty"><ImageUp :size="28" /><strong>这个阶段还没有插画</strong><span>请先在上方上传并裁剪对应突破插画。</span></div>
          </div>
        </section>
      </div>

      <div v-if="pendingArtwork" class="artwork-crop-backdrop" @click.self="closeArtworkCrop">
        <section class="artwork-crop-dialog">
          <div class="artwork-crop-heading">
            <div><p class="kicker">ARTWORK CROP</p><h2>裁剪{{ pendingArtwork.stage === 0 ? '初始形态' : `${pendingArtwork.stage} 次突破` }}插画</h2></div>
            <button aria-label="关闭" @click="closeArtworkCrop">×</button>
          </div>
          <p class="artwork-crop-hint">原图 {{ pendingArtwork.imageWidth }} × {{ pendingArtwork.imageHeight }}。最终区域必须为 9:16；服务端会缩小到最高 1080 × 1920，并统一编码为 WebP。</p>
          <p v-if="error" class="crop-server-error">{{ error }}</p>
          <div class="artwork-crop-body">
            <ImageCropper
              v-model="pendingArtworkCrop"
              :image-url="pendingArtwork.objectUrl"
              :image-width="pendingArtwork.imageWidth"
              :image-height="pendingArtwork.imageHeight"
              :aspect-width="9"
              :aspect-height="16"
            />
            <div class="artwork-crop-actions">
              <span>输出选区 {{ pendingArtwork.w }} × {{ pendingArtwork.h }}</span>
              <button @click="closeArtworkCrop">取消</button>
              <button class="confirm-crop-button" :disabled="!!artworkCropError || uploadingStage !== null" @click="confirmArtworkUpload">
                <ImageUp :size="16" />{{ uploadingStage !== null ? '处理中…' : '裁剪并上传' }}
              </button>
            </div>
          </div>
        </section>
      </div>
      <PartnerGrantPanel v-else :admin-token="token" :partners="partners" />
    </template>
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
.admin-header { height: 72px; position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; padding: 0 28px; border-bottom: 1px solid #ffffff12; background: #0e1611eF; backdrop-filter: blur(16px); }.brand { display: flex; align-items: center; gap: 11px; }.brand > span { width: 39px; height: 39px; display: grid; place-items: center; color: #d5ad60; border: 1px solid #d5ad6044; border-radius: 13px 4px; }.brand strong,.brand small { display: block; }.brand small { color: #778278; font-size: 12px; margin-top: 2px; }.header-actions { display: flex; align-items: center; gap: 10px; }.header-actions a,.header-actions button { min-height: 37px; display: inline-flex; align-items: center; gap: 7px; padding: 0 13px; border-radius: 9px; cursor: pointer; }.header-actions a { color: #a8b2a8; border: 1px solid #ffffff14; }.save-button { color: #182116; font-weight: 800; border: 0; background: #aacb88; }.notice { display: flex; align-items: center; gap: 5px; color: #aacb88; font-size: 12px; }
.admin-section-tabs { display: flex; gap: 5px; padding: 4px; border: 1px solid #ffffff10; border-radius: 11px; background: #080d0a55; }.admin-section-tabs button { min-height: 32px; padding: 0 13px; color: #78847b; font-size: 12px; border: 0; border-radius: 7px; background: transparent; cursor: pointer; }.admin-section-tabs button.active { color: #e8e6dc; background: #ffffff0e; box-shadow: inset 0 0 0 1px #ffffff0a; }
.admin-layout { height: calc(100vh - 72px); display: grid; grid-template-columns: 265px minmax(0, 1fr); overflow: hidden; }.partner-list { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 20px 14px; border-right: 1px solid #ffffff10; background: #111a15; }.list-heading { position: sticky; top: -20px; z-index: 1; display: flex; align-items: center; justify-content: space-between; padding: 5px 7px 18px; background: #111a15; }.list-heading small,.list-heading strong { display: block; }.list-heading small { color: #657168; font-size: 12px; letter-spacing: .18em; }.list-heading strong { margin-top: 3px; }.list-heading button { width: 34px; height: 34px; display: grid; place-items: center; color: #aacb88; border: 1px solid #aacb8833; border-radius: 9px; background: #aacb880c; cursor: pointer; }.partner-list-item { width: 100%; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 9px; padding: 10px; margin-bottom: 5px; text-align: left; border: 1px solid transparent; border-radius: 12px; background: transparent; cursor: pointer; }.partner-list-item.active { border-color: #8fad7133; background: #8fad7114; }.mini-avatar { color: #9db982; }.mini-avatar img { width: 100%; height: 100%; object-fit: cover; }.partner-list-item strong,.partner-list-item small { display: block; }.partner-list-item small { color: #748077; font-size: 12px; margin-top: 3px; }.partner-list-item i { padding: 3px 6px; color: #d99177; font-size: 12px; font-style: normal; border-radius: 99px; background: #d9917712; }.partner-list-item i.complete { color: #9dc27e; background: #9dc27e12; }.empty-list { padding: 35px 10px; text-align: center; color: #657168; font-size: 12px; }
.editor-panel { width: min(1180px, 100%); min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 34px clamp(20px, 4vw, 54px) 80px; }.editor-title { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 22px; }.editor-title p { margin: 0; }.editor-title h1 { margin: 5px 0 0; font: 700 31px Georgia, 'Noto Serif SC', serif; }.delete-button { display: flex; align-items: center; gap: 6px; min-height: 35px; padding: 0 11px; color: #d98b7c; border: 1px solid #d98b7c33; border-radius: 9px; background: #d98b7c0a; cursor: pointer; }.editor-error { padding: 11px 14px; color: #f0a696; border: 1px solid #dc7c6933; border-radius: 10px; background: #dc7c6910; }
.form-card { padding: 20px; border: 1px solid #ffffff11; border-radius: 18px 6px; background: #17211b; }.basic-grid { display: grid; grid-template-columns: 1.4fr 1.4fr .7fr .8fr; gap: 15px; }.basic-grid .wide { grid-column: 1 / -1; }.form-card label > span,.tendency-grid article > label:not(.industry-toggle) > span { display: block; margin-bottom: 6px; color: #818d83; font-size: 12px; }.form-card input,.form-card select,.form-card textarea,.tendency-grid input[type=number] { width: 100%; color: #eee8db; border: 1px solid #ffffff14; border-radius: 8px; background: #0f1712; outline: none; }.form-card input,.form-card select,.tendency-grid input[type=number] { height: 39px; padding: 0 10px; }.form-card textarea { padding: 10px; resize: vertical; }.form-card input:focus,.form-card select:focus,.form-card textarea:focus { border-color: #9aba7866; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin: 40px 0 15px; }.section-heading small { color: #d0714b; font-size: 12px; font-weight: 800; letter-spacing: .18em; }.section-heading h2 { margin: 4px 0 0; font-size: 19px; }.section-heading p { margin: 0; color: #7f8b81; font-size: 12px; }
.section-heading p.cdn-warning { color: #df947d; }
.tendency-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; }.tendency-grid article { min-height: 72px; padding: 14px; border: 1px dashed #ffffff12; border-radius: 13px 5px; background: #ffffff05; }.tendency-grid article.enabled { min-height: 190px; border-style: solid; border-color: #91b47233; background: #19251d; }.industry-toggle { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-weight: 700; cursor: pointer; }.industry-toggle input,.trait-grid input { accent-color: #99bb79; }.tendency-grid article > label:not(.industry-toggle) { display: block; margin-top: 9px; }.ability-preview { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px; margin-top: 12px; }.ability-preview span { color: #647067; text-align: center; font-size: 12px; }.ability-preview strong { display: block; color: #c8d2c4; font-size: 12px; margin-top: 2px; }
.trait-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }.trait-grid label { position: relative; min-height: 105px; display: grid; grid-template-columns: auto 1fr; align-content: start; gap: 4px 8px; padding: 14px; border: 1px solid #ffffff11; border-radius: 13px 5px; background: #151e19; cursor: pointer; }.trait-grid label.checked { border-color: #c693493f; background: #c693490d; }.trait-grid strong { font-size: 13px; }.trait-grid span { grid-column: 2; color: #79857c; font-size: 12px; line-height: 1.45; }.trait-grid i { position: absolute; right: 10px; bottom: 9px; color: #737f76; font-size: 12px; font-style: normal; }
.artwork-grid { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 14px; }.artwork-card { display: grid; grid-template-columns: 112px 1fr; grid-template-rows: 1fr auto; gap: 12px; padding: 13px; border: 1px solid #ffffff11; border-radius: 17px 6px; background: #17211b; }.artwork-frame { width: 112px; aspect-ratio: 9 / 16; overflow: hidden; grid-row: 1 / 3; display: grid; place-items: center; color: #77837a; border: 1px dashed #ffffff16; border-radius: 11px 4px; background: #0d1410; }.artwork-frame img { width: 100%; height: 100%; object-fit: cover; }.artwork-frame > div { display: grid; place-items: center; gap: 5px; font-size: 12px; }.artwork-meta { align-self: end; }.artwork-meta strong,.artwork-meta small { display: block; }.artwork-meta small { color: #78847a; font-size: 12px; margin-top: 4px; }.upload-button { min-height: 35px; display: flex; align-items: center; justify-content: center; gap: 6px; align-self: end; color: #bad49e; font-size: 12px; border: 1px solid #9cbe7c33; border-radius: 8px; background: #9cbe7c0d; cursor: pointer; }.upload-button input { display: none; }.upload-button.disabled { opacity: .5; pointer-events: none; }
.avatar-crop-card { padding: 18px; border: 1px solid #ffffff11; border-radius: 18px 6px; background: #17211b; }.avatar-stage-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 18px; }.avatar-stage-tabs button { min-height: 54px; padding: 8px 12px; text-align: left; color: #9ca79e; border: 1px solid #ffffff10; border-radius: 10px; background: #101813; cursor: pointer; }.avatar-stage-tabs button.active { color: #eae6d9; border-color: #9cbe7b55; background: #9cbe7b12; }.avatar-stage-tabs span,.avatar-stage-tabs small { display: block; }.avatar-stage-tabs small { margin-top: 3px; color: #718078; font-size: 12px; }.avatar-crop-workspace { display: grid; grid-template-columns: minmax(280px, 440px) 1fr; gap: 28px; align-items: center; }.avatar-crop-summary { padding: 20px; border-left: 1px solid #ffffff0e; }.avatar-crop-summary strong,.avatar-crop-summary span { display: block; }.avatar-crop-summary strong { font-size: 17px; }.avatar-crop-summary span { margin-top: 7px; color: #b7c9ab; font-size: 12px; }.avatar-crop-summary p { max-width: 320px; color: #7d8980; font-size: 12px; line-height: 1.7; }.avatar-crop-empty { min-height: 230px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #6f7b73; border: 1px dashed #ffffff12; border-radius: 13px; }.avatar-crop-empty strong { color: #98a49a; }.avatar-crop-empty span { font-size: 12px; }
.artwork-crop-backdrop { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; padding: 18px; background: #050906d9; backdrop-filter: blur(7px); }.artwork-crop-dialog { width: min(760px, 100%); max-height: calc(100vh - 36px); overflow: auto; padding: 24px; border: 1px solid #ffffff18; border-radius: 24px 8px; background: #18231c; box-shadow: 0 35px 100px #000b; }.artwork-crop-heading { display: flex; align-items: start; justify-content: space-between; }.artwork-crop-heading p { margin: 0; }.artwork-crop-heading h2 { margin: 5px 0 0; font-size: 21px; }.artwork-crop-heading > button { width: 34px; height: 34px; color: #8e9a90; font-size: 24px; line-height: 1; border: 1px solid #ffffff12; border-radius: 9px; background: transparent; cursor: pointer; }.artwork-crop-hint { margin: 12px 0 20px; color: #89958b; font-size: 12px; line-height: 1.7; }.artwork-crop-body :deep(.image-cropper) { max-width: 440px; margin: 0 auto; }.artwork-crop-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 20px; }.artwork-crop-actions > span { margin-right: auto; color: #839087; font-size: 12px; }.artwork-crop-actions button { min-height: 39px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 14px; color: #aeb8af; border: 1px solid #ffffff14; border-radius: 9px; background: transparent; cursor: pointer; }.artwork-crop-actions .confirm-crop-button { color: #172016; font-weight: 800; border: 0; background: #a9cb87; }.artwork-crop-actions button:disabled { opacity: .45; cursor: not-allowed; }
.crop-server-error { padding: 9px 11px; margin: -8px 0 16px; color: #efa08f; font-size: 12px; border: 1px solid #dc806d33; border-radius: 8px; background: #dc806d0d; }
@media (max-width: 1050px) { .tendency-grid,.trait-grid { grid-template-columns: repeat(2, 1fr); }.artwork-grid { grid-template-columns: 1fr; }.artwork-card { grid-template-columns: 90px 1fr; }.artwork-frame { width: 90px; }.basic-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 760px) { .admin-header { height: auto; min-height: 66px; padding: 10px 14px; }.brand small,.header-actions > a,.notice { display: none; }.admin-section-tabs button { padding: 0 9px; }.admin-layout { height: auto; display: block; overflow: visible; }.partner-list { overflow-y: visible; border-right: 0; border-bottom: 1px solid #ffffff10; }.list-heading { position: static; }.editor-panel { overflow-y: visible; }.partner-list-item { display: inline-grid; width: min(240px, 75vw); margin-right: 5px; }.editor-panel { padding: 24px 14px 70px; }.basic-grid { grid-template-columns: 1fr 1fr; }.tendency-grid,.trait-grid { grid-template-columns: 1fr 1fr; }.section-heading { align-items: start; }.section-heading p { max-width: 48%; }.avatar-crop-workspace { grid-template-columns: 1fr; justify-items: center; }.avatar-crop-summary { width: 100%; border-left: 0; border-top: 1px solid #ffffff0e; }.artwork-crop-dialog { padding: 18px; }.artwork-crop-actions { margin-top: 20px; } }
@media (max-width: 460px) { .tendency-grid,.trait-grid,.basic-grid { grid-template-columns: 1fr; }.basic-grid .wide { grid-column: auto; }.section-heading { display: block; }.section-heading p { max-width: none; margin-top: 6px; }.avatar-stage-tabs { grid-template-columns: 1fr; }.artwork-crop-actions { flex-wrap: wrap; }.artwork-crop-actions > span { width: 100%; margin-right: 0; } }
</style>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, BarChart3, Check, LockKeyhole, Save, Sprout } from 'lucide-vue-next'

import { api, ApiError } from '@/api'
import { loginAsAdmin, clearLegacyAdminToken } from '@/composables/adminAuth'
import ExpectedProfitChart, { type ProfitSeries } from '@/components/admin/ExpectedProfitChart.vue'
import type { CropAdminDefinition, CropAdminPayload, QualityGradeDefinition } from '@/types'

clearLegacyAdminToken()
const authenticated = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const crops = ref<CropAdminDefinition[]>([])
const baselineCrops = ref<CropAdminDefinition[]>([])
const grades = ref<QualityGradeDefinition[]>([])
const abilityMax = ref(220)
const activeCropId = ref('')
const chartAbilityMax = computed(() => Math.min(1000, Math.max(20, Math.floor(Number(abilityMax.value) || 20))))

const chartCrops = computed(() => crops.value.filter((crop) => crop.chart_enabled && crop.seed_price !== null))
const activeCrop = computed(() => crops.value.find((crop) => crop.id === activeCropId.value) || crops.value[0] || null)
const dirtyCropIds = computed(() => new Set(crops.value
  .filter((crop) => cropSnapshot(crop) !== cropSnapshot(baselineCrops.value.find((entry) => entry.id === crop.id)))
  .map((crop) => crop.id)))
const hasUnsavedChanges = computed(() => dirtyCropIds.value.size > 0)
const chartSeries = computed<ProfitSeries[]>(() => chartCrops.value.flatMap((crop) => {
  const baseline = baselineCrops.value.find((entry) => entry.id === crop.id)
  const changed = Boolean(baseline && dirtyCropIds.value.has(crop.id))
  const draftSeries: ProfitSeries = {
    id: `${crop.id}-draft`,
    label: changed ? `${crop.name} · 编辑值` : crop.name,
    color: crop.accent,
    width: changed ? 3 : 2.5,
    points: profitPoints(crop),
  }
  if (!changed || !baseline || !baseline.chart_enabled || baseline.seed_price === null) return [draftSeries]
  return [{
    id: `${crop.id}-baseline`,
    label: `${crop.name} · 保存值`,
    color: fadedColor(crop.accent),
    dash: [7, 5],
    width: 2,
    points: profitPoints(baseline),
  }, draftSeries]
}))

const winnerBands = computed(() => {
  const result: Array<{ ability: number; crop: string }> = []
  let previous = ''
  for (let ability = 0; ability <= chartAbilityMax.value; ability += 1) {
    const winner = chartCrops.value.reduce<CropAdminDefinition | null>((best, crop) => {
      if (!best || hourlyProfit(crop, ability) > hourlyProfit(best, ability)) return crop
      return best
    }, null)
    if (winner && winner.id !== previous) {
      result.push({ ability, crop: winner.name })
      previous = winner.id
    }
  }
  return result
})

function headers(): Record<string, string> {
  return { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' }
}

function clonePayload(payload: CropAdminPayload) {
  crops.value = JSON.parse(JSON.stringify(payload.crops)) as CropAdminDefinition[]
  baselineCrops.value = JSON.parse(JSON.stringify(payload.crops)) as CropAdminDefinition[]
  grades.value = payload.quality_grades
  if (!crops.value.some((crop) => crop.id === activeCropId.value)) {
    activeCropId.value = crops.value.find((crop) => crop.chart_enabled)?.id || crops.value[0]?.id || ''
  }
}

function cropSnapshot(crop: CropAdminDefinition | undefined) {
  if (!crop) return ''
  return JSON.stringify({
    seed_price: crop.seed_price,
    produce_sell_price: crop.produce_sell_price,
    growth_seconds: crop.growth_seconds,
    minimum_duration_seconds: crop.minimum_duration_seconds,
    time_difficulty: crop.time_difficulty,
    yield_min: crop.yield_min,
    yield_max: crop.yield_max,
    stamina_cost: crop.stamina_cost,
    plant_xp: crop.plant_xp,
    harvest_xp: crop.harvest_xp,
    quality: crop.quality,
  })
}

function fadedColor(color: string) {
  return /^#[0-9a-f]{6}$/i.test(color) ? `${color}66` : color
}

function profitPoints(crop: CropAdminDefinition) {
  return Array.from({ length: chartAbilityMax.value + 1 }, (_, ability) => ({
    x: ability,
    y: hourlyProfit(crop, ability),
  }))
}

async function load() {
  error.value = ''
  try {
    const payload = await api<CropAdminPayload>('/api/red-leaf-town/admin/crops', { headers: headers() })
    clonePayload(payload)
    authenticated.value = true
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '作物配置加载失败'
    if (caught instanceof ApiError && caught.status === 403) {
      authenticated.value = false

    }
  }
}


function sigmoid(value: number) {
  if (value >= 0) {
    const inverse = Math.exp(-value)
    return 1 / (1 + inverse)
  }
  const direct = Math.exp(value)
  return direct / (1 + direct)
}

function qualityProbabilities(crop: CropAdminDefinition, ability: number) {
  const [t2, t3, t4, t5] = crop.quality.thresholds
  const width = Math.max(0.0001, crop.quality.width)
  const [g2, g3, g4] = [t2, t3, t4].map((threshold) => sigmoid((ability - threshold) / width))
  const g5 = crop.quality.miracle_eligible
    ? Math.min(g4, crop.quality.miracle_probability_cap * sigmoid((ability - t5) / width))
    : 0
  return [1 - g2, g2 - g3, g3 - g4, g4 - g5, g5]
}

function hourlyProfit(crop: CropAdminDefinition, ability: number) {
  if (crop.seed_price === null) return 0
  const probabilities = qualityProbabilities(crop, ability)
  const expectedUnitPrice = grades.value.reduce((sum, grade, index) => (
    sum + (probabilities[index] || 0) * Math.floor(crop.produce_sell_price * grade.sale_multiplier + 0.5)
  ), 0)
  const expectedQuantity = (Number(crop.yield_min) + Number(crop.yield_max)) / 2
  const difficulty = Math.max(0.0001, Number(crop.time_difficulty))
  const efficiency = 1 + (2 * ability) / (ability + difficulty)
  const durationSeconds = Math.max(
    Number(crop.minimum_duration_seconds) || 1,
    Math.ceil(Number(crop.growth_seconds) / efficiency),
  )
  const durationHours = Math.max(1, durationSeconds) / 3600
  return (expectedQuantity * expectedUnitPrice - Number(crop.seed_price)) / durationHours
}

function growthHours(crop: CropAdminDefinition) {
  return crop.growth_seconds / 3600
}

function setGrowthHours(crop: CropAdminDefinition, value: string) {
  crop.growth_seconds = Math.max(1, Math.round(Number(value || 0) * 3600))
}

function minimumHours(crop: CropAdminDefinition) {
  return crop.minimum_duration_seconds / 3600
}

function setMinimumHours(crop: CropAdminDefinition, value: string) {
  crop.minimum_duration_seconds = Math.max(1, Math.round(Number(value || 0) * 3600))
}

function miraclePercent(crop: CropAdminDefinition) {
  return crop.quality.miracle_probability_cap * 100
}

function setMiraclePercent(crop: CropAdminDefinition, value: string) {
  crop.quality.miracle_probability_cap = Math.max(0, Number(value || 0) / 100)
}

function savePayload() {
  return crops.value.map((crop) => ({
    id: crop.id,
    seed_price: crop.seed_price,
    produce_sell_price: Number(crop.produce_sell_price),
    growth_seconds: Number(crop.growth_seconds),
    minimum_duration_seconds: Number(crop.minimum_duration_seconds),
    time_difficulty: Number(crop.time_difficulty),
    yield_min: Number(crop.yield_min),
    yield_max: Number(crop.yield_max),
    stamina_cost: Number(crop.stamina_cost),
    plant_xp: Number(crop.plant_xp),
    harvest_xp: Number(crop.harvest_xp),
    quality: {
      thresholds: crop.quality.thresholds.map(Number),
      width: Number(crop.quality.width),
      miracle_probability_cap: Number(crop.quality.miracle_probability_cap),
      miracle_eligible: crop.quality.miracle_eligible,
    },
  }))
}

async function save() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const payload = await api<CropAdminPayload>('/api/red-leaf-town/admin/crops', {
      method: 'PUT',
      headers: headers(),
      body: JSON.stringify({ crops: savePayload() }),
    })
    clonePayload(payload)
    notice.value = '作物数值已保存并热更新'
    window.setTimeout(() => (notice.value = ''), 2400)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '保存失败'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <main class="admin-page">
    <section v-if="!authenticated" class="unlock-card">
      <div class="admin-seal"><LockKeyhole :size="34" /></div>
      <p class="kicker">RED LEAF TOWN ADMIN</p>
      <h1>作物数值工作台</h1>
      <p>请使用已获得管理员权限的水鱼账号登录。</p>
      <form @submit.prevent="loginAsAdmin">
        <button type="submit">水鱼账号登录</button>
      </form>
      <span v-if="error" class="form-error">{{ error }}</span>
      <a href="/red-leaf-town/"><ArrowLeft :size="15" />返回红叶镇</a>
    </section>

    <template v-else>
      <header class="admin-header">
        <div class="brand"><span><BarChart3 :size="22" /></span><div><strong>红叶镇后台</strong><small>作物数值工作台</small></div></div>
        <nav class="admin-links">
          <RouterLink :to="{ name: 'admin-partners' }">伙伴管理</RouterLink>
          <RouterLink :to="{ name: 'admin-story' }">剧情素材</RouterLink>
          <RouterLink :to="{ name: 'admin-mail' }">镇邮局</RouterLink>
          <RouterLink :to="{ name: 'admin-codes' }">激活码</RouterLink>
        </nav>
        <div class="header-actions">
          <span v-if="hasUnsavedChanges" class="unsaved-notice">有未保存改动</span>
          <span v-if="notice" class="notice"><Check :size="15" />{{ notice }}</span>
          <a href="/red-leaf-town/"><ArrowLeft :size="16" />玩家前台</a>
          <button class="save-button" :disabled="busy || !hasUnsavedChanges" @click="save"><Save :size="16" />{{ busy ? '保存中' : '保存配置' }}</button>
        </div>
      </header>

      <div class="admin-body">
        <p v-if="error" class="editor-error">{{ error }}</p>

        <section class="balance-workbench">
          <div class="chart-card">
            <div class="chart-heading">
              <div><small>EXPECTED PROFIT</small><h1>每小时预期净收益</h1></div>
              <label><span>能力上限</span><input v-model.number="abilityMax" type="number" min="20" max="1000" step="10" /></label>
            </div>
            <p class="chart-note">已扣除种子成本；按平均产量计算。能力同时改变品质概率，并按正式规则缩短成熟时间。</p>
            <div v-if="hasUnsavedChanges" class="comparison-note"><i />实线为编辑值，虚线为保存值</div>
            <ExpectedProfitChart :series="chartSeries" />
            <div class="winner-bands">
              <span v-for="band in winnerBands" :key="`${band.ability}-${band.crop}`"><b>能力 {{ band.ability }}</b> 起：{{ band.crop }}</span>
            </div>
          </div>

          <aside class="editor-column">
            <div class="crop-tabs" role="tablist" aria-label="选择作物">
              <button
                v-for="crop in crops"
                :key="crop.id"
                role="tab"
                :aria-selected="activeCropId === crop.id"
                :class="{ active: activeCropId === crop.id, dirty: dirtyCropIds.has(crop.id) }"
                @click="activeCropId = crop.id"
              >
                {{ crop.name }}<i v-if="dirtyCropIds.has(crop.id)" />
              </button>
            </div>

            <article v-for="crop in activeCrop ? [activeCrop] : []" :key="crop.id" class="crop-card" :style="{ '--crop-accent': crop.accent }">
              <header>
                <span class="crop-icon"><Sprout :size="20" /></span>
                <div><h3>{{ crop.name }}</h3><small>{{ crop.id }}</small></div>
                <i v-if="!crop.chart_enabled">剧情限定 · 不进入曲线</i>
              </header>
              <p class="editor-note">修改会即时进入左侧预览；只有点击保存才会写入游戏配置。</p>

              <div class="field-grid economy-fields">
                <label><span>种子价格</span><input v-model.number="crop.seed_price" type="number" min="0" :disabled="crop.seed_price === null" /></label>
                <label><span>产物基础售价</span><input v-model.number="crop.produce_sell_price" type="number" min="0" /></label>
                <label><span>基础时间（小时）</span><input :value="growthHours(crop)" type="number" min="0.01" step="0.25" @input="setGrowthHours(crop, ($event.target as HTMLInputElement).value)" /></label>
                <label><span>时间下限（小时）</span><input :value="minimumHours(crop)" type="number" min="0.01" step="0.25" @input="setMinimumHours(crop, ($event.target as HTMLInputElement).value)" /></label>
                <label><span>时间难度</span><input v-model.number="crop.time_difficulty" type="number" min="1" /></label>
                <label><span>最小产量</span><input v-model.number="crop.yield_min" type="number" min="1" /></label>
                <label><span>最大产量</span><input v-model.number="crop.yield_max" type="number" min="1" /></label>
                <label><span>播种经验（收获时发放）</span><input v-model.number="crop.plant_xp" type="number" min="0" /></label>
                <label><span>收获经验</span><input v-model.number="crop.harvest_xp" type="number" min="0" /></label>
              </div>

              <div class="quality-heading"><strong>品质曲线</strong><small>达到阈值时，“至少该品质”的概率为 50%</small></div>
              <div class="threshold-grid">
                <label v-for="(name, index) in ['良品 T2', '上品 T3', '臻品 T4', '奇迹 T5']" :key="name">
                  <span>{{ name }}</span><input v-model.number="crop.quality.thresholds[index]" type="number" />
                </label>
              </div>
              <div class="field-grid quality-fields">
                <label><span>曲线宽度</span><input v-model.number="crop.quality.width" type="number" min="0.1" step="0.5" /></label>
                <label><span>奇迹概率上限（%）</span><input :value="miraclePercent(crop)" type="number" min="0" max="1" step="0.05" @input="setMiraclePercent(crop, ($event.target as HTMLInputElement).value)" /></label>
                <label class="check-field"><input v-model="crop.quality.miracle_eligible" type="checkbox" /><span>允许出现奇迹品质</span></label>
              </div>
            </article>
          </aside>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.admin-page { min-height: 100vh; color: #eee8db; background: radial-gradient(circle at 85% 0, #783d2922, transparent 28%), #0d1410; }
.unlock-card { width: min(430px, calc(100% - 32px)); margin: 0 auto; padding-top: 16vh; text-align: center; }
.admin-seal { width: 70px; height: 70px; display: grid; place-items: center; margin: auto; color: #d4a95b; border: 1px solid #d4a95b66; border-radius: 22px 7px; }
.kicker { margin: 24px 0 8px; color: #78857b; font-size: 11px; letter-spacing: .22em; }.unlock-card h1 { margin: 0; font-size: 30px; }.unlock-card > p:not(.kicker) { color: #879188; }.unlock-card form { display: flex; gap: 8px; margin: 28px 0 12px; }.unlock-card input { flex: 1; }.unlock-card button { padding: 0 20px; color: #172016; font-weight: 800; border: 0; border-radius: 9px; background: #aacb88; }.unlock-card > a { display: inline-flex; align-items: center; gap: 5px; margin-top: 18px; color: #879188; font-size: 13px; }
.admin-header { min-height: 72px; position: sticky; top: 0; z-index: 10; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 18px; padding: 10px 28px; border-bottom: 1px solid #ffffff12; background: #0e1611ef; backdrop-filter: blur(16px); }
.brand { display: flex; align-items: center; gap: 11px; }.brand > span { width: 39px; height: 39px; display: grid; place-items: center; color: #d5ad60; border: 1px solid #d5ad6044; border-radius: 13px 4px; }.brand strong,.brand small { display: block; }.brand small { color: #778278; font-size: 12px; margin-top: 2px; }
.admin-links { display: flex; gap: 5px; padding: 4px; border: 1px solid #ffffff10; border-radius: 11px; background: #080d0a55; }.admin-links a { padding: 8px 12px; color: #8f9a91; font-size: 12px; border-radius: 7px; }.admin-links a:hover { color: #e8e6dc; background: #ffffff0e; }
.header-actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }.header-actions a,.header-actions button { min-height: 37px; display: inline-flex; align-items: center; gap: 7px; padding: 0 13px; border-radius: 9px; cursor: pointer; }.header-actions a { color: #a8b2a8; border: 1px solid #ffffff14; }.save-button { color: #182116; font-weight: 800; border: 0; background: #aacb88; }.save-button:disabled { opacity: .42; cursor: not-allowed; }.notice { display: flex; align-items: center; gap: 5px; color: #aacb88; font-size: 12px; }.unsaved-notice { color: #d8b46f; font-size: 12px; }
.admin-body { width: min(1440px, 100%); margin: 0 auto; padding: 30px clamp(16px, 4vw, 54px) 90px; }.editor-error,.form-error { display: block; padding: 10px 12px; color: #efad9d; font-size: 13px; border: 1px solid #d36f5733; border-radius: 9px; background: #d36f570d; }
.balance-workbench { display: grid; grid-template-columns: minmax(0, 2fr) minmax(340px, 1fr); align-items: start; gap: 16px; }.chart-card { position: sticky; top: 92px; min-width: 0; padding: clamp(18px, 2.5vw, 28px); border: 1px solid #ffffff12; border-radius: 18px; background: #111a15; box-shadow: 0 18px 55px #00000024; }.chart-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; }.chart-heading small { color: #758178; font-size: 11px; letter-spacing: .18em; }.chart-heading h1 { margin: 4px 0 0; }.chart-heading label { display: flex; align-items: center; gap: 9px; color: #8d998f; font-size: 12px; }.chart-heading input { width: 92px; }.chart-note { margin: 10px 0 8px; color: #7e8a81; font-size: 13px; }.comparison-note { display: flex; align-items: center; gap: 7px; width: max-content; margin-bottom: 10px; padding: 5px 8px; color: #d8b46f; font-size: 11px; border-radius: 99px; background: #d8b46f0c; }.comparison-note i { width: 20px; border-top: 2px dashed currentColor; }.winner-bands { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }.winner-bands span { padding: 6px 9px; color: #99a69b; font-size: 12px; border: 1px solid #ffffff0d; border-radius: 99px; background: #ffffff05; }.winner-bands b { color: #d6ddd3; }
.editor-column { min-width: 0; border: 1px solid #ffffff12; border-radius: 18px; overflow: hidden; background: #111a15; box-shadow: 0 18px 55px #00000018; }.crop-tabs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px; padding: 8px; border-bottom: 1px solid #ffffff0d; background: #0b120e; }.crop-tabs button { position: relative; min-height: 36px; padding: 0 10px; color: #7f8a82; font-size: 12px; border: 1px solid transparent; border-radius: 8px; background: transparent; cursor: pointer; }.crop-tabs button:hover { color: #c5ccc3; background: #ffffff08; }.crop-tabs button.active { color: #edf0e7; border-color: #aacb8828; background: #aacb8810; }.crop-tabs button i { position: absolute; top: 6px; right: 7px; width: 6px; height: 6px; border-radius: 50%; background: #d8b46f; box-shadow: 0 0 0 3px #d8b46f18; }
.crop-card { padding: 20px; border: 0; background: linear-gradient(145deg, color-mix(in srgb, var(--crop-accent) 7%, #111a15), #101813 45%); }.crop-card > header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }.crop-icon { width: 39px; height: 39px; display: grid; place-items: center; color: var(--crop-accent); border-radius: 11px; background: color-mix(in srgb, var(--crop-accent) 13%, transparent); }.crop-card h3,.crop-card header small { display: block; margin: 0; }.crop-card header small { margin-top: 2px; color: #6f7b72; }.crop-card header i { margin-left: auto; padding: 5px 8px; color: #d1ad70; font-size: 11px; font-style: normal; border-radius: 99px; background: #d1ad7011; }.editor-note { margin: 0 0 17px; color: #748078; font-size: 11px; line-height: 1.55; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.field-grid label,.threshold-grid label { display: grid; min-width: 0; gap: 6px; }.field-grid span,.threshold-grid span { color: #879389; font-size: 11px; }.quality-heading { display: grid; gap: 3px; margin: 20px 0 10px; padding-top: 16px; border-top: 1px solid #ffffff0c; }.quality-heading strong { font-size: 13px; }.quality-heading small { color: #6d786f; font-size: 11px; line-height: 1.45; }.threshold-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.quality-fields { margin-top: 10px; }.check-field { display: flex !important; grid-column: 1 / -1; align-items: center; align-self: end; min-height: 39px; padding: 0 11px; border: 1px solid #ffffff12; border-radius: 8px; background: #080d0a88; }.check-field input { width: auto; }.check-field span { font-size: 12px; }
input { width: 100%; min-height: 39px; padding: 0 10px; color: #e8e9df; border: 1px solid #ffffff12; border-radius: 8px; outline: none; background: #080d0a88; }.crop-card input:focus,.chart-heading input:focus,.unlock-card input:focus { border-color: #aacb8866; }.crop-card input:disabled { color: #687168; cursor: not-allowed; }
@media (max-width: 1100px) { .admin-header { grid-template-columns: 1fr auto; }.admin-links { display: none; }.balance-workbench { grid-template-columns: 1fr; }.chart-card { position: static; }.editor-column { width: 100%; }.crop-tabs { grid-template-columns: repeat(5, minmax(90px, 1fr)); overflow-x: auto; }.crop-card { max-width: none; }.field-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }.threshold-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }.quality-fields { grid-template-columns: 1fr 1fr 2fr; }.check-field { grid-column: auto; } }
@media (max-width: 700px) { .admin-header { padding: 10px 14px; }.brand small,.header-actions > a,.notice,.unsaved-notice { display: none; }.admin-body { padding: 20px 12px 70px; }.chart-heading { align-items: start; }.crop-tabs { grid-template-columns: repeat(5, 110px); }.field-grid,.threshold-grid,.quality-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }.check-field { grid-column: 1 / -1; } }
</style>

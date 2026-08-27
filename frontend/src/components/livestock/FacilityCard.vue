<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Coins, Egg, HeartHandshake, PackageOpen, Sprout } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import AnimalRow from '@/components/livestock/AnimalRow.vue'
import GameIcon from '@/components/GameIcon.vue'
import ItemGridTile from '@/components/ItemGridTile.vue'
import NameAnimalDialog from '@/components/livestock/NameAnimalDialog.vue'
import PartnerPicker from '@/components/PartnerPicker.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import { useCountdown } from '@/composables/useCountdown'
import { formatDuration } from '@/lib/format'
import { qualityName } from '@/lib/quality'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { LivestockFacilityState, LivestockState, SlotState } from '@/types'

const props = defineProps<{
  facility: LivestockFacilityState
  livestock: LivestockState
  feedSlot: SlotState
}>()

const game = useGameStore()
const ui = useUiStore()

const selected = ref<string[]>([])

const accent = computed(() => props.facility.accent)
const species = computed(() => props.facility.species[0] || null)
const room = computed(() => props.facility.capacity - props.facility.used)
const pairing = computed(() => species.value?.breeding.mode === 'pair')

const { label: cycleLabel, progress: cycleProgress } = useCountdown(
  () => props.facility.last_settled_at + props.facility.next_cycle_seconds,
  () => props.livestock.cycle_seconds,
)

/** 能当种蛋的库存：品质就是基因载体，所以按品质分格展示，让人挑。 */
const eggs = computed(() => {
  const target = props.facility.species.find((entry) => entry.breeding.mode === 'incubate')
  if (!target) return []
  return game.state?.inventory
    .filter((entry) => entry.item_id === target.breeding.incubate_item_id && entry.quality)
    .map((entry) => ({
      quality: entry.quality || 1,
      quantity: entry.quantity,
      icon: entry.icon,
      name: entry.name,
      base: target.breeding.quality_gene_base[(entry.quality || 1) - 1],
    })) || []
})

const breeding = computed(() => species.value?.breeding || null)

const adults = computed(() =>
  props.facility.animals.filter((animal) => animal.stage === 'adult' && animal.breeding_cooldown <= 0),
)

// 栏里的动物换了之后，选中的亲本可能已经卖掉或还在冷却里。
watch(
  () => props.facility.animals.map((animal) => animal.animal_id).join(','),
  () => {
    const alive = new Set(adults.value.map((animal) => animal.animal_id))
    selected.value = selected.value.filter((entry) => alive.has(entry))
  },
)

const breedReason = computed(() => {
  if (!breeding.value) return '这里不配种'
  if (selected.value.length !== 2) return '选两只成年牲畜'
  if (room.value <= 0) return '栏里没有空位'
  if (props.feedSlot.quality_score < breeding.value.min_feed_score) {
    return `饲料槽品质分要到 ${breeding.value.min_feed_score}`
  }
  if (props.feedSlot.units < breeding.value.feed_units) return '饲料不足'
  return undefined
})

function incubateReason(quality: number) {
  if (!breeding.value) return '这里不孵蛋'
  if (room.value <= 0) return '栏里没有空位'
  if (props.feedSlot.units < breeding.value.feed_units) return '饲料不足'
  return undefined
}

type Naming =
  | { kind: 'buy'; speciesId: string }
  | { kind: 'incubate'; quality: number }
  | { kind: 'breed' }

const naming = ref<Naming | null>(null)

/** 买入、孵化、配种都会多出一只牲畜，起名的时机就是这三处。 */
const namingDialog = computed(() => {
  const request = naming.value
  if (!request) return null
  if (request.kind === 'buy') {
    const entry = props.facility.species.find((item) => item.id === request.speciesId)
    if (!entry) return null
    return {
      title: `买入幼${entry.name}`,
      subtitle: `${entry.purchase_price} 红叶币`,
      icon: entry.icon,
      speciesName: entry.name,
      quality: null,
      actionKey: `livestock:${props.facility.facility_id}:buy:${entry.id}`,
      confirmLabel: '买入',
      lines: [
        { label: '成年', value: `${entry.growth_cycles} 个周期` },
        { label: '饲料', value: `${entry.feed_per_cycle} 份 / 周期` },
        { label: '产出', value: entry.produce_item.name },
      ],
    }
  }
  if (request.kind === 'incubate') {
    const egg = eggs.value.find((item) => item.quality === request.quality)
    const target = props.facility.species.find((item) => item.breeding.mode === 'incubate')
    if (!egg || !target) return null
    return {
      title: '孵化',
      subtitle: `${qualityName(egg.quality)}${egg.name}`,
      icon: target.icon,
      speciesName: target.name,
      quality: egg.quality,
      actionKey: `livestock:${props.facility.facility_id}:incubate:${egg.quality}`,
      confirmLabel: '放入窝中',
      lines: [
        { label: '基因起点', value: `${egg.base}（品种上限 ${props.facility.gene_cap}）` },
        { label: '破壳', value: `${target.breeding.incubate_cycles} 个周期` },
        { label: '饲料', value: `${target.breeding.feed_units} 份` },
      ],
    }
  }
  const target = species.value
  if (!target) return null
  return {
    title: '配种',
    subtitle: `已选 ${selected.value.length} 只亲本`,
    icon: target.icon,
    speciesName: target.name,
    quality: null,
    actionKey: `livestock:${props.facility.facility_id}:breed`,
    confirmLabel: '配种',
    lines: [
      { label: '成年', value: `${target.growth_cycles} 个周期` },
      { label: '双亲冷却', value: `${target.breeding.cooldown_cycles} 个周期` },
      { label: '饲料', value: `${target.breeding.feed_units} 份` },
    ],
  }
})

async function confirmNaming(nickname: string) {
  const request = naming.value
  if (!request) return
  const facilityId = props.facility.facility_id
  const result =
    request.kind === 'buy'
      ? await game.buyAnimal(facilityId, request.speciesId, nickname)
      : request.kind === 'incubate'
        ? await game.incubateEgg(facilityId, request.quality, nickname)
        : await game.breedAnimals(facilityId, selected.value, nickname)
  if (result) naming.value = null
}

function toggle(animalId: string) {
  if (!pairing.value) return
  const animal = props.facility.animals.find((entry) => entry.animal_id === animalId)
  if (!animal || animal.stage !== 'adult' || animal.breeding_cooldown > 0) return
  const index = selected.value.indexOf(animalId)
  if (index >= 0) selected.value.splice(index, 1)
  else if (selected.value.length < 2) selected.value.push(animalId)
  else selected.value = [selected.value[1], animalId]
}

async function sell(animalId: string) {
  const animal = props.facility.animals.find((entry) => entry.animal_id === animalId)
  if (!animal) return
  const accepted = await ui.confirm({
    title: `卖掉这只${animal.name}？`,
    description: `品质基因 ${animal.quality_gene}、产量基因 ${animal.yield_gene}。回收价随基因提高，但低于买入价，售出后不可撤销。`,
    confirmLabel: '卖掉',
    tone: 'danger',
  })
  if (accepted) game.sellAnimal(animalId)
}
</script>

<template>
  <article class="facility surface-card" :style="{ '--facility-accent': accent }">
    <header>
      <div>
        <h3>{{ facility.name }}</h3>
        <small>{{ facility.description }}</small>
      </div>
      <span class="facility-count">{{ facility.used }}<i>/{{ facility.capacity }}</i></span>
    </header>

    <p v-if="facility.stalled" class="facility-alert">
      <AlertTriangle :size="15" /> 饲料槽已空，本栏暂停运转：不产出、不成长，也不能孵蛋配种，待收产出不会减少。
    </p>

    <div class="cycle">
      <div class="cycle-line">
        <span>下一周期</span>
        <strong>{{ cycleLabel }}</strong>
        <em>周期恒为 {{ formatDuration(livestock.cycle_seconds) }}</em>
      </div>
      <ProgressBar :value="cycleProgress" color="var(--facility-accent)" :height="8" />
    </div>

    <dl class="facility-stats">
      <div>
        <dt>品质系数</dt>
        <dd>×{{ facility.quality_multiplier }}</dd>
      </div>
      <div>
        <dt>溢出上限</dt>
        <dd>{{ facility.overflow_cycles }} 个周期</dd>
      </div>
      <div>
        <dt>品种上限</dt>
        <dd>{{ facility.gene_cap }}</dd>
      </div>
      <div>
        <dt>畜牧能力</dt>
        <dd>{{ facility.ability }}</dd>
      </div>
    </dl>

    <PartnerPicker
      industry="livestock"
      :action-key="`livestock:${facility.facility_id}:partner`"
      :assigned="facility.assigned_partners[0] || null"
      placeholder="安排一位伙伴照看"
      dialog-title="畜牧驻场"
      solo-label="自己照看"
      @select="(partnerId) => game.assignLivestockPartner(facility.facility_id, partnerId)"
    />

    <ul v-if="facility.animals.length" class="facility-animals">
      <AnimalRow
        v-for="animal in facility.animals"
        :key="animal.animal_id"
        :animal="animal"
        :cycle-seconds="livestock.cycle_seconds"
        :selectable="pairing && animal.stage === 'adult' && animal.breeding_cooldown <= 0"
        :selected="selected.includes(animal.animal_id)"
        @toggle="toggle(animal.animal_id)"
        @sell="sell(animal.animal_id)"
      />
    </ul>
    <p v-else class="facility-empty">
      <Sprout :size="18" />
      这里还空着。买入的幼崽养满 {{ species?.growth_cycles || 3 }} 个周期后成年，此后每个周期产出一次。
    </p>

    <ActionButton
      v-if="facility.pending_total || facility.pending_special"
      :action-key="`livestock:${facility.facility_id}:collect`"
      @click="game.collectLivestock(facility.facility_id)"
    >
      <PackageOpen :size="15" /> 全部收取（{{ facility.pending_total + facility.pending_special }}）
    </ActionButton>

    <section v-for="entry in facility.species" :key="entry.id" class="buy">
      <div class="buy-line">
        <GameIcon :name="entry.icon" :size="18" />
        <div>
          <strong>买一只小{{ entry.name }}</strong>
          <small>
            {{ entry.growth_cycles }} 个周期成年 · 每周期吃 {{ entry.feed_per_cycle }} 份 ·
            产出{{ entry.produce_item.name }}
          </small>
        </div>
        <span class="buy-price" :class="{ short: !entry.affordable }"><Coins :size="14" />{{ entry.purchase_price }}</span>
      </div>
      <ActionButton
        :action-key="`livestock:${facility.facility_id}:buy:${entry.id}`"
        variant="secondary"
        :disabled="!entry.unlocked || !entry.affordable || room <= 0"
        :reason="!entry.unlocked ? `居民等级 ${entry.min_level} 解锁` : (room <= 0 ? '栏里没有空位' : (!entry.affordable ? '红叶币不足' : undefined))"
        @click="naming = { kind: 'buy', speciesId: entry.id }"
      >
        买入幼崽
      </ActionButton>
    </section>

    <section v-if="breeding?.mode === 'incubate'" class="hatch">
      <h4><Egg :size="15" /> 孵蛋</h4>
      <p>
        放一枚蛋入窝，占用一个位置并扣 {{ breeding.feed_units }} 份饲料，{{ breeding.incubate_cycles }} 个周期后破壳。
        蛋的品质决定幼崽的基因起点，基因不超过本设施的品种上限。
      </p>
      <div v-if="eggs.length" class="hatch-grid">
        <ItemGridTile
          v-for="egg in eggs"
          :key="egg.quality"
          :icon="egg.icon"
          :name="egg.name"
          :quality="egg.quality"
          :badge="egg.quantity"
          :dimmed="Boolean(incubateReason(egg.quality))"
          @click="naming = { kind: 'incubate', quality: egg.quality }"
        >
          <template #tooltip>
            <strong>{{ qualityName(egg.quality) }}{{ egg.name }}</strong>
            <span>基因起点 {{ egg.base }} · 品种上限 {{ facility.gene_cap }}</span>
            <span>{{ incubateReason(egg.quality) || `仓库 ${egg.quantity} 枚` }}</span>
          </template>
        </ItemGridTile>
      </div>
      <p v-else class="hatch-empty">仓库里还没有可以孵的蛋。</p>
    </section>

    <section v-if="breeding?.mode === 'pair'" class="breed">
      <h4><HeartHandshake :size="15" /> 配种</h4>
      <p>
        选两只成年牲畜，占用一个位置并扣 {{ breeding.feed_units }} 份饲料，要求饲料槽品质分不低于
        {{ breeding.min_feed_score }}，双亲各进入 {{ breeding.cooldown_cycles }} 个周期冷却。
        子代基因取双亲均值并随机浮动，不超过本设施的品种上限。
      </p>
      <p class="breed-picked">
        已选 {{ selected.length }} / 2
        <span v-if="adults.length < 2">（可选的成年牲畜不足）</span>
      </p>
      <ActionButton
        :action-key="`livestock:${facility.facility_id}:breed`"
        variant="secondary"
        :disabled="Boolean(breedReason)"
        :reason="breedReason"
        @click="naming = { kind: 'breed' }"
      >
        配种
      </ActionButton>
    </section>

    <NameAnimalDialog
      v-if="namingDialog"
      :open="Boolean(namingDialog)"
      :title="namingDialog.title"
      :subtitle="namingDialog.subtitle"
      :icon="namingDialog.icon"
      :species-name="namingDialog.speciesName"
      :quality="namingDialog.quality"
      :action-key="namingDialog.actionKey"
      :confirm-label="namingDialog.confirmLabel"
      :lines="namingDialog.lines"
      @close="naming = null"
      @confirm="confirmNaming"
    />
  </article>
</template>

<style scoped>
.facility { --facility-accent: #d7ad58; display: flex; flex-direction: column; gap: 14px; padding: 18px; }
.facility header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.facility h3 { margin: 0; font: 600 17px Georgia, 'Noto Serif SC', serif; }
.facility header small { display: block; margin-top: 5px; color: #849087; line-height: 1.55; }
.facility-count { font-size: 20px; color: var(--facility-accent); white-space: nowrap; }
.facility-count i { font-style: normal; font-size: 13px; color: #77837a; }

.facility-alert { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 11px 12px; color: #cf8c80; font-size: 12px; line-height: 1.6; border: 1px solid rgba(207, 140, 128, .2); border-radius: 12px; background: rgba(207, 140, 128, .05); }

.cycle-line { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; font-size: 12px; }
.cycle-line span { color: #849087; }
.cycle-line strong { font-size: 14px; }
.cycle-line em { margin-left: auto; font-style: normal; color: #6f7a72; font-size: 11px; }

.facility-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 0; }
.facility-stats dt { color: #7d887f; font-size: 11px; }
.facility-stats dd { margin: 3px 0 0; font-size: 13px; }

.facility-animals { display: grid; gap: 9px; margin: 0; padding: 0; }
.facility-empty { display: flex; align-items: center; gap: 9px; margin: 0; padding: 16px; color: #7d887f; font-size: 12px; line-height: 1.6; border: 1px dashed var(--line); border-radius: 13px; }

.buy { display: flex; flex-direction: column; gap: 9px; padding: 12px; border: 1px dashed var(--line); border-radius: 13px; }
.buy-line { display: flex; align-items: center; gap: 10px; }
.buy-line strong { font-size: 13px; }
.buy-line small { display: block; margin-top: 3px; color: #7d887f; font-size: 11.5px; line-height: 1.5; }
.buy-price { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; color: var(--gold); white-space: nowrap; }
.buy-price.short { color: #b4635a; }

.hatch, .breed { display: flex; flex-direction: column; gap: 9px; padding: 13px; border: 1px solid var(--line); border-radius: 13px; background: #ffffff04; }
.hatch h4, .breed h4 { display: flex; align-items: center; gap: 7px; margin: 0; font: 600 14px Georgia, 'Noto Serif SC', serif; }
.hatch p, .breed p { margin: 0; color: #7d887f; font-size: 11.5px; line-height: 1.75; }
.hatch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(74px, 1fr)); gap: 9px; }
.hatch-empty { color: #6f7a72; }
.breed-picked { color: var(--gold) !important; }

@media (max-width: 620px) {
  .facility-stats { grid-template-columns: repeat(2, 1fr); }
}
</style>

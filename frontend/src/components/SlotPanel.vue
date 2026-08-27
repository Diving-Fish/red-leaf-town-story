<script setup lang="ts">
import { computed, ref } from 'vue'
import { Trash2, Wheat } from 'lucide-vue-next'

import ItemGridTile from '@/components/ItemGridTile.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import SlotDepositDialog from '@/components/SlotDepositDialog.vue'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { SlotInputEntry, SlotState } from '@/types'

const props = withDefaults(
  defineProps<{
    slot: SlotState
    description?: string
    emptyHint?: string
    dumpTitle?: string
    dumpDescription?: string
  }>(),
  {
    description: '鱼塘与畜栏都从这里扣饲料，槽内耗尽则一起停摆。饲料的品质分越高，产出的品质越好。',
    emptyHint: '仓库中暂时没有可投入的饲料。牧草可在商店购买，柔韧牧草来自采集，杂鱼与各类作物也都能投入。',
    dumpTitle: '倒空饲料槽？',
    dumpDescription: '槽内饲料将全部丢弃，不返还任何物品。',
  },
)

const game = useGameStore()
const ui = useUiStore()

const picked = ref<SlotInputEntry | null>(null)
const dialogOpen = ref(false)

const room = computed(() => Math.max(0, props.slot.capacity - props.slot.units))

function open(entry: SlotInputEntry) {
  picked.value = entry
  dialogOpen.value = true
}

function tileBadge(entry: SlotInputEntry) {
  return entry.quantity > 99 ? '99+' : entry.quantity
}

/** 一眼看出这一格能顶多少份：图标格没地方写字，这个数字最值得占位置。 */
function tooBig(entry: SlotInputEntry) {
  return entry.units > room.value
}

async function deposit(payload: { itemId: string; quality: number; count: number }) {
  const result = await game.depositFeed(payload.itemId, payload.quality, payload.count)
  if (result) dialogOpen.value = false
}

async function dump() {
  const accepted = await ui.confirm({
    title: props.dumpTitle,
    description: props.dumpDescription,
    confirmLabel: '倒空',
    tone: 'danger',
  })
  if (accepted) game.dumpFeed()
}
</script>

<template>
  <section class="slot surface-card">
    <header>
      <div>
        <h2><Wheat :size="17" /> {{ slot.name }}</h2>
        <small>{{ description }}</small>
      </div>
      <button class="dump-button" :disabled="!slot.units" @click="dump">
        <Trash2 :size="14" /> 倒空
      </button>
    </header>

    <div class="slot-gauge">
      <div class="slot-line">
        <strong>{{ Math.floor(slot.units) }}</strong>
        <span>/ {{ slot.capacity }} 份</span>
        <em>品质分 {{ slot.quality_score.toFixed(1) }}</em>
      </div>
      <ProgressBar :value="(slot.units / slot.capacity) * 100" color="var(--leaf-bright)" :height="8" />
      <small>
        <template v-if="slot.hourly_rate">
          当前每小时约 {{ slot.hourly_rate }} 份，可维持 {{ formatDuration(slot.runtime_seconds) }}。
        </template>
        <template v-else>目前没有消耗饲料的设施。</template>
      </small>
    </div>

    <p v-if="!slot.inputs.length" class="slot-hint">{{ emptyHint }}</p>

    <div v-else class="slot-grid">
      <ItemGridTile
        v-for="entry in slot.inputs"
        :key="`${entry.item_id}:${entry.quality || 0}`"
        :icon="entry.item.icon"
        :name="entry.item.name"
        :quality="entry.quality"
        :badge="tileBadge(entry)"
        :dimmed="tooBig(entry)"
        @click="open(entry)"
      >
        <template #tooltip>
          <strong>{{ entry.item.name }}</strong>
          <span>{{ entry.units }} 份 / 个 · 单位品质分 {{ entry.unit_score }}</span>
          <span>仓库 {{ entry.quantity }} 个</span>
        </template>
      </ItemGridTile>
    </div>

    <SlotDepositDialog
      :open="dialogOpen"
      :slot="slot"
      :entry="picked"
      :action-key="`aquatic:feed:${picked?.item_id}:${picked?.quality || 0}`"
      @close="dialogOpen = false"
      @deposit="deposit"
    />
  </section>
</template>

<style scoped>
.slot { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
.slot header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.slot h2 { display: flex; align-items: center; gap: 8px; margin: 0; font: 600 17px Georgia, 'Noto Serif SC', serif; }
.slot header small { display: block; margin-top: 5px; color: #849087; line-height: 1.55; }
.dump-button { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 0 11px; color: #cf8c80; border: 1px solid rgba(207, 140, 128, .2); border-radius: 9px; background: rgba(207, 140, 128, .05); cursor: pointer; white-space: nowrap; }

.slot-line { display: flex; align-items: baseline; gap: 7px; margin-bottom: 7px; }
.slot-line strong { font-size: 22px; }
.slot-line span { color: #77837a; font-size: 12px; }
.slot-line em { margin-left: auto; color: var(--leaf-bright); font-style: normal; font-weight: 700; }
.slot-gauge small { display: block; margin-top: 7px; color: #6f7a72; font-size: 11px; }

.slot-hint { margin: 0; padding: 14px; color: #7d887f; font-size: 12px; line-height: 1.7; border: 1px dashed var(--line); border-radius: 12px; }

.slot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(74px, 1fr)); gap: 9px; max-height: 340px; overflow: auto; }
</style>

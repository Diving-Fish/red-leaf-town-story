<script setup lang="ts">
import { computed, ref } from 'vue'
import { Trash2, Wheat } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import GameIcon from '@/components/GameIcon.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import QualityTag from '@/components/QualityTag.vue'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { FeedSlotState } from '@/types'

const props = defineProps<{ feedSlot: FeedSlotState }>()

const game = useGameStore()
const ui = useUiStore()
const counts = ref<Record<string, number>>({})

function key(itemId: string, quality: number | null) {
  return `${itemId}:${quality || 0}`
}

function countFor(itemId: string, quality: number | null) {
  return counts.value[key(itemId, quality)] || 1
}

function setCount(itemId: string, quality: number | null, value: number) {
  counts.value[key(itemId, quality)] = Math.max(1, Math.floor(value) || 1)
}

const room = computed(() => props.feedSlot.capacity - props.feedSlot.units)

/** 投进去之后分数变成多少 —— 稀释与提纯的取舍必须是明示的。 */
function previewScore(units: number, unitScore: number, count: number) {
  const added = units * count
  const total = props.feedSlot.units + added
  if (total <= 0) return 0
  return (props.feedSlot.units * props.feedSlot.quality_score + added * unitScore) / total
}

function deposit(itemId: string, quality: number | null) {
  game.depositFeed(itemId, quality || 0, countFor(itemId, quality))
}

async function dump() {
  const accepted = await ui.confirm({
    title: '倒空饲料槽？',
    description: '槽内饲料将全部丢弃，不返还任何物品。仅在品质分被低档饲料稀释得过低时才建议这么做。',
    confirmLabel: '倒空',
    tone: 'danger',
  })
  if (accepted) game.dumpFeed()
}
</script>

<template>
  <section class="feed surface-card">
    <header>
      <div>
        <h2><Wheat :size="17" /> {{ feedSlot.name }}</h2>
        <small>鱼塘每走完一个繁殖周期从这里扣一次饲料，与周期长短无关；槽内耗尽则停摆，买不起的周期不会推进。饲料的品质分越高，鱼塘产出的品质越好。</small>
      </div>
      <button class="dump-button" :disabled="!feedSlot.units" @click="dump">
        <Trash2 :size="14" /> 倒空
      </button>
    </header>

    <div class="feed-gauge">
      <div class="feed-line">
        <strong>{{ Math.floor(feedSlot.units) }}</strong>
        <span>/ {{ feedSlot.capacity }} 份</span>
        <em>品质分 {{ feedSlot.quality_score.toFixed(1) }}</em>
      </div>
      <ProgressBar :value="(feedSlot.units / feedSlot.capacity) * 100" color="var(--leaf-bright)" :height="8" />
      <small>
        <template v-if="feedSlot.hourly_rate">
          按当前周期折算每小时约 {{ feedSlot.hourly_rate }} 份，可维持 {{ formatDuration(feedSlot.runtime_seconds) }}。
        </template>
        <template v-else>目前没有消耗饲料的设施。</template>
      </small>
    </div>

    <p v-if="!feedSlot.inputs.length" class="feed-hint">
      仓库中暂时没有可投入的饲料。牧草可在商店购买，柔韧牧草来自采集，杂鱼与各类作物也都能投入。
    </p>

    <ul v-else class="feed-inputs">
      <li v-for="entry in feedSlot.inputs" :key="key(entry.item_id, entry.quality)">
        <div class="feed-item">
          <GameIcon :name="entry.item.icon" :size="19" />
          <div>
            <strong>
              {{ entry.item.name }}
              <QualityTag v-if="entry.quality" :quality="entry.quality" :name="entry.quality_name" plain />
            </strong>
            <small>{{ entry.units }} 份 / 个 · 单位品质分 {{ entry.unit_score }} · 仓库 {{ entry.quantity }}</small>
          </div>
        </div>
        <div class="feed-controls">
          <input
            :value="countFor(entry.item_id, entry.quality)"
            type="number"
            min="1"
            :max="entry.quantity"
            @input="setCount(entry.item_id, entry.quality, Number(($event.target as HTMLInputElement).value))"
          >
          <ActionButton
            :action-key="`aquatic:feed:${entry.item_id}:${entry.quality || 0}`"
            variant="secondary"
            :disabled="entry.units * countFor(entry.item_id, entry.quality) > room"
            :reason="entry.units * countFor(entry.item_id, entry.quality) > room ? '槽里装不下这一批' : undefined"
            @click="deposit(entry.item_id, entry.quality)"
          >
            投入
          </ActionButton>
        </div>
        <small class="feed-preview">
          投入后 {{ entry.units * countFor(entry.item_id, entry.quality) }} 份 ·
          品质分 {{ feedSlot.quality_score.toFixed(1) }} →
          {{ previewScore(entry.units, entry.unit_score, countFor(entry.item_id, entry.quality)).toFixed(1) }}
        </small>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.feed { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
.feed header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.feed h2 { display: flex; align-items: center; gap: 8px; margin: 0; font: 600 17px Georgia, 'Noto Serif SC', serif; }
.feed header small { display: block; margin-top: 5px; color: #849087; line-height: 1.55; }
.dump-button { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 0 11px; color: #cf8c80; border: 1px solid rgba(207, 140, 128, .2); border-radius: 9px; background: rgba(207, 140, 128, .05); cursor: pointer; white-space: nowrap; }

.feed-line { display: flex; align-items: baseline; gap: 7px; margin-bottom: 7px; }
.feed-line strong { font-size: 22px; }
.feed-line span { color: #77837a; font-size: 12px; }
.feed-line em { margin-left: auto; color: var(--leaf-bright); font-style: normal; font-weight: 700; }
.feed-gauge small { display: block; margin-top: 7px; color: #6f7a72; font-size: 11px; }

.feed-hint { margin: 0; padding: 14px; color: #7d887f; font-size: 12px; line-height: 1.7; border: 1px dashed var(--line); border-radius: 12px; }

.feed-inputs { display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; max-height: 420px; overflow: auto; }
.feed-inputs li { display: grid; grid-template-columns: 1fr auto; gap: 9px; padding: 11px 12px; border: 1px solid var(--line); border-radius: 13px; background: #ffffff04; }
.feed-item { display: flex; align-items: center; gap: 10px; min-width: 0; }
.feed-item strong { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.feed-item small { display: block; margin-top: 3px; color: #7d887f; }
.feed-controls { display: flex; align-items: center; gap: 8px; }
.feed-controls input { width: 68px; height: 32px; padding: 0 9px; color: inherit; border: 1px solid var(--line); border-radius: 8px; background: #ffffff06; }
.feed-preview { grid-column: 1 / -1; color: #6f7a72; font-size: 11px; }

@media (max-width: 620px) {
  .feed-inputs li { grid-template-columns: 1fr; }
  .feed-controls { justify-content: flex-end; }
}
</style>

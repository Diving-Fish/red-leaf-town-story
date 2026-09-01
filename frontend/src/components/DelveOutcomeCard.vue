<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, CheckCircle2, Footprints, Heart, PackageOpen, XCircle } from 'lucide-vue-next'

import type { DelveBattleActionResult } from '@/types'

/** 一场战斗打完之后的结算。留在战斗卡原来的位置，不要把玩家的视线甩到页顶。 */
const props = defineProps<{ result: DelveBattleActionResult; standalone?: boolean }>()

const emit = defineEmits<{ (event: 'next'): void }>()

const title = computed(() => {
  if (props.result.outcome === 'victory') return '战斗胜利'
  if (props.result.outcome === 'fled') return '成功脱离'
  return '队伍失去了战斗力'
})

const nextLabel = computed(() => {
  if (props.result.outcome === 'wiped') return '回到路线列表'
  return props.result.completed ? '查看路线终点' : '继续深入'
})
</script>

<template>
  <article class="outcome-card surface-card" :class="result.outcome">
    <span class="outcome-mark">
      <component :is="result.outcome === 'wiped' ? XCircle : CheckCircle2" :size="24" />
    </span>
    <div class="outcome-copy">
      <small class="ui-kicker">战斗结束</small>
      <h2 class="ui-section-title">{{ title }}</h2>
      <p class="ui-description">{{ result.logs[result.logs.length - 1]?.text }}</p>
      <div class="outcome-drops">
        <span v-for="drop in result.drops || []" :key="`${drop.item_id}:${drop.quality}`">
          <PackageOpen :size="14" /> {{ drop.quality_name }}{{ drop.item?.name || drop.item_id }} ×{{ drop.quantity }}
        </span>
        <span v-if="result.outcome === 'wiped'">
          <Heart :size="14" /> 冻结的战利品全部损失，装备和伙伴没有受损
        </span>
        <span v-else-if="result.outcome === 'fled'">
          <Footprints :size="14" /> 跳过了这一节点的战利品
        </span>
      </div>
    </div>
    <button class="primary-button outcome-next" @click="emit('next')">
      {{ nextLabel }} <ArrowRight :size="16" />
    </button>
  </article>
</template>

<style scoped>
.outcome-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  border-left: 3px solid var(--leaf-bright);
}
.outcome-card.wiped { border-left-color: var(--danger); }
.outcome-card.fled { border-left-color: var(--quality-3); }
.outcome-mark { width: 44px; height: 44px; display: grid; place-items: center; color: var(--leaf-bright); border-radius: 14px 5px 14px 5px; background: #a8c98514; }
.outcome-card.wiped .outcome-mark { color: var(--danger); background: #e38b7b14; }
.outcome-card.fled .outcome-mark { color: var(--quality-3); background: #70afd614; }
.outcome-copy { min-width: 0; }
.outcome-copy .ui-section-title { margin: 2px 0 4px; }
.outcome-drops { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 9px; }
.outcome-drops span { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; color: #b9c5ba; font-size: var(--font-caption); border-radius: 99px; background: #ffffff07; }
.outcome-next { display: inline-flex; align-items: center; gap: 6px; }
@media (max-width: 720px) {
  .outcome-card { grid-template-columns: auto minmax(0, 1fr); }
  .outcome-next { grid-column: 1 / -1; justify-content: center; }
}
</style>

<script setup lang="ts">
import { computed } from 'vue'

import ModalSheet from '@/components/ModalSheet.vue'
import type { DelveBattleLog } from '@/types'

/** 战斗记录：默认收起，需要复盘时再点开。 */
const props = defineProps<{ open: boolean; logs: DelveBattleLog[]; partyKeys: string[] }>()

const emit = defineEmits<{ (event: 'close'): void }>()

const rounds = computed(() => {
  const grouped: Array<{ round: number; entries: DelveBattleLog[] }> = []
  for (const entry of props.logs) {
    const last = grouped[grouped.length - 1]
    if (last && last.round === entry.round) last.entries.push(entry)
    else grouped.push({ round: entry.round, entries: [entry] })
  }
  return grouped.reverse()
})

function friendly(entry: DelveBattleLog) {
  return props.partyKeys.includes(entry.actor)
}

function mark(entry: DelveBattleLog) {
  if (entry.action === 'item') return '恢复'
  if (entry.action === 'advantage') return '备战'
  if (entry.action === 'flee') return entry.hit ? '脱离' : '未脱离'
  if (entry.critical) return '会心'
  return entry.hit ? '命中' : '未中'
}
</script>

<template>
  <ModalSheet
    :open="open"
    title="战斗记录"
    :subtitle="logs.length ? `共 ${logs.length} 次行动 · 从最近一回合往回看` : ''"
    elevated
    @close="emit('close')"
  >
    <div class="log-rounds">
      <section v-for="group in rounds" :key="group.round" class="log-round">
        <h3><i />第 {{ group.round }} 回合</h3>
        <p
          v-for="(entry, index) in group.entries"
          :key="`${group.round}:${index}`"
          class="log-entry"
          :class="[friendly(entry) ? 'ours' : 'theirs', { crit: entry.critical, miss: entry.hit === false }]"
        >
          <b>{{ mark(entry) }}</b>
          <span>{{ entry.text }}</span>
          <em v-if="entry.roll !== null">d20 {{ entry.roll }}<template v-if="entry.total !== null"> → {{ entry.total }}</template></em>
        </p>
      </section>

      <p v-if="!logs.length" class="log-empty">这场战斗还没有行动记录。</p>
    </div>
  </ModalSheet>
</template>

<style scoped>
.log-rounds { display: grid; gap: 14px; }
.log-round h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 7px; color: #8b978c; font: 600 var(--font-caption)/1 var(--font-display); letter-spacing: .1em; }
.log-round h3 i { flex: 1; height: 1px; background: var(--line); }
.log-entry {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 3px 9px;
  margin: 0 0 6px;
  padding: 8px 10px;
  border-left: 2px solid var(--entry-tone, var(--leaf-bright));
  border-radius: 3px 10px 10px 3px;
  background: #ffffff05;
}
.log-entry.ours { --entry-tone: var(--leaf-bright); }
.log-entry.theirs { --entry-tone: var(--autumn); }
.log-entry.crit { --entry-tone: var(--gold); }
.log-entry.miss { --entry-tone: #6f7c72; }
.log-entry b { color: var(--entry-tone); font-size: var(--font-caption); }
.log-entry span { color: #b3bfb3; font-size: var(--font-copy); line-height: 1.6; }
.log-entry em { grid-column: 2; color: #7d8a80; font-size: var(--font-caption); font-style: normal; font-variant-numeric: tabular-nums; }
.log-empty { margin: 18px 0; color: #78857b; font-size: var(--font-copy); text-align: center; }
</style>

<script setup lang="ts">
import { computed } from 'vue'
import { Menu } from 'lucide-vue-next'

import { NAV_ITEMS, type NavItem } from '@/lib/navigation'
import { useGameStore } from '@/stores/game'

const props = defineProps<{ variant: 'rail' | 'bar' }>()
const emit = defineEmits<{ (event: 'navigate'): void; (event: 'more'): void }>()
const game = useGameStore()

const items = computed(() => (props.variant === 'bar' ? NAV_ITEMS.filter((item) => item.primary) : NAV_ITEMS))
const hiddenReady = computed(() =>
  NAV_ITEMS.filter((item) => !item.primary).reduce(
    (total, item) => total + (item.readyGroup ? game.readyCounts[item.readyGroup] : 0),
    0,
  ),
)

function badge(item: NavItem) {
  return item.readyGroup ? game.readyCounts[item.readyGroup] : 0
}
</script>

<template>
  <nav class="app-nav" :class="`app-nav--${variant}`">
    <RouterLink v-for="item in items" :key="item.to" :to="item.to" @click="emit('navigate')">
      <span class="nav-icon">
        <component :is="item.icon" :size="20" />
        <i v-if="badge(item)" class="nav-badge">{{ badge(item) }}</i>
      </span>
      <span class="nav-label">{{ item.label }}</span>
    </RouterLink>
    <button v-if="variant === 'bar'" type="button" @click="emit('more')">
      <span class="nav-icon">
        <Menu :size="20" />
        <i v-if="hiddenReady" class="nav-badge">{{ hiddenReady }}</i>
      </span>
      <span class="nav-label">更多</span>
    </button>
  </nav>
</template>

<style scoped>
.nav-icon { position: relative; display: grid; place-items: center; }
.nav-badge {
  position: absolute;
  right: -9px;
  top: -6px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  display: grid;
  place-items: center;
  color: #1d2419;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
  border-radius: 99px;
  background: var(--gold);
}
.app-nav--rail { display: grid; gap: 6px; }
.app-nav--rail a {
  display: flex;
  align-items: center;
  gap: 13px;
  min-height: 48px;
  padding: 0 14px;
  color: #abb6ab;
  border-radius: 12px;
  transition: .2s;
}
.app-nav--rail a:hover { color: var(--cream); background: #ffffff0a; }
.app-nav--rail a.router-link-active {
  color: #f6efe1;
  background: linear-gradient(90deg, rgba(119, 153, 91, .2), rgba(119, 153, 91, .07));
  box-shadow: inset 3px 0 var(--leaf);
}
.app-nav--bar { display: none; }
@media (max-width: 760px) {
  .app-nav--bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 60;
    display: flex;
    padding: 6px 4px calc(6px + env(safe-area-inset-bottom));
    border-top: 1px solid var(--line);
    background-color: #151e19;
  }
  .app-nav--bar a, .app-nav--bar button {
    flex: 1 1 0;
    min-width: 0;
    min-height: 52px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    color: #7e8a81;
    font-size: 12px;
    border: 0;
    background: transparent;
  }
  .app-nav--bar a.router-link-active { color: var(--leaf-bright); }
}
</style>

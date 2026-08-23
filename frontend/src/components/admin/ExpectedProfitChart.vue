<script setup lang="ts">
import Chart from 'chart.js/auto'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface ProfitSeries {
  id: string
  label: string
  color: string
  dash?: number[]
  width?: number
  points: Array<{ x: number; y: number }>
}

const props = defineProps<{ series: ProfitSeries[] }>()
const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart<'line', Array<{ x: number; y: number }>> | null = null

function datasets() {
  return props.series.map((entry) => ({
    label: entry.label,
    data: entry.points,
    parsing: false as const,
    borderColor: entry.color,
    backgroundColor: entry.color,
    borderWidth: entry.width ?? 2.5,
    borderDash: entry.dash || [],
    pointRadius: 0,
    pointHitRadius: 10,
    tension: 0.18,
  }))
}

function render() {
  if (!canvas.value) return
  chart = new Chart(canvas.value, {
    type: 'line',
    data: { datasets: datasets() },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 180 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          align: 'start',
          labels: { color: '#cbd3ca', usePointStyle: true, boxWidth: 8, boxHeight: 8 },
        },
        tooltip: {
          backgroundColor: '#111914f2',
          borderColor: '#ffffff22',
          borderWidth: 1,
          titleColor: '#f1ede3',
          bodyColor: '#cbd3ca',
          callbacks: {
            title: (items) => `能力 ${items[0]?.parsed.x ?? 0}`,
            label: (context) => `${context.dataset.label}：${Number(context.parsed.y || 0).toFixed(2)} / 小时`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: '农作能力', color: '#8f9b91' },
          ticks: { color: '#738078', maxTicksLimit: 11 },
          grid: { color: '#ffffff0a' },
          border: { color: '#ffffff14' },
        },
        y: {
          title: { display: true, text: '每小时预期净收益', color: '#8f9b91' },
          ticks: { color: '#738078' },
          grid: { color: '#ffffff0a' },
          border: { color: '#ffffff14' },
        },
      },
    },
  })
}

watch(
  () => props.series,
  () => {
    if (!chart) return
    chart.data.datasets = datasets()
    chart.update()
  },
  { deep: true },
)

onMounted(render)
onBeforeUnmount(() => chart?.destroy())
</script>

<template><div class="profit-chart"><canvas ref="canvas" /></div></template>

<style scoped>
.profit-chart { position: relative; width: 100%; height: clamp(360px, 48vw, 560px); }
</style>

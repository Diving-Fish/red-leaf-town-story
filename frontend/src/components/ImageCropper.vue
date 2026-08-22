<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Maximize2 } from 'lucide-vue-next'

import type { CropRect } from '@/types'

const props = withDefaults(defineProps<{
  imageUrl: string
  imageWidth: number
  imageHeight: number
  modelValue: CropRect
  aspectWidth?: number
  aspectHeight?: number
}>(), {
  aspectWidth: 1,
  aspectHeight: 1,
})

const emit = defineEmits<{ 'update:modelValue': [value: CropRect] }>()
const surface = ref<HTMLElement | null>(null)

type Corner = 'nw' | 'ne' | 'sw' | 'se'
type DragState =
  | { mode: 'move'; pointerX: number; pointerY: number; crop: CropRect }
  | { mode: 'resize'; corner: Corner; anchorX: number; anchorY: number; signX: number; signY: number }

let drag: DragState | null = null

const crop = computed(() => normalize(props.modelValue))
const surfaceStyle = computed(() => ({ aspectRatio: `${props.imageWidth} / ${props.imageHeight}` }))
const selectionStyle = computed(() => ({
  left: `${crop.value.x / props.imageWidth * 100}%`,
  top: `${crop.value.y / props.imageHeight * 100}%`,
  width: `${crop.value.w / props.imageWidth * 100}%`,
  height: `${crop.value.h / props.imageHeight * 100}%`,
}))

function sameCrop(left: CropRect, right: CropRect) {
  return left.x === right.x && left.y === right.y && left.w === right.w && left.h === right.h
}

function normalize(value: CropRect): CropRect {
  const aspectWidth = Math.max(1, Math.round(props.aspectWidth))
  const aspectHeight = Math.max(1, Math.round(props.aspectHeight))
  const maxUnit = Math.max(1, Math.min(
    Math.floor(props.imageWidth / aspectWidth),
    Math.floor(props.imageHeight / aspectHeight),
  ))
  const requestedUnit = Math.max(1, Math.round(Math.min(
    Number(value?.w || aspectWidth) / aspectWidth,
    Number(value?.h || aspectHeight) / aspectHeight,
  )))
  const unit = Math.min(maxUnit, requestedUnit)
  const w = unit * aspectWidth
  const h = unit * aspectHeight
  return {
    x: Math.max(0, Math.min(Math.round(Number(value?.x || 0)), props.imageWidth - w)),
    y: Math.max(0, Math.min(Math.round(Number(value?.y || 0)), props.imageHeight - h)),
    w,
    h,
  }
}

function largestCenteredCrop(): CropRect {
  const aspectWidth = Math.max(1, Math.round(props.aspectWidth))
  const aspectHeight = Math.max(1, Math.round(props.aspectHeight))
  const unit = Math.max(1, Math.min(
    Math.floor(props.imageWidth / aspectWidth),
    Math.floor(props.imageHeight / aspectHeight),
  ))
  const w = unit * aspectWidth
  const h = unit * aspectHeight
  return {
    x: Math.floor((props.imageWidth - w) / 2),
    y: Math.floor((props.imageHeight - h) / 2),
    w,
    h,
  }
}

function pointInImage(event: PointerEvent) {
  const bounds = surface.value?.getBoundingClientRect()
  if (!bounds) return { x: 0, y: 0 }
  return {
    x: Math.max(0, Math.min(props.imageWidth, (event.clientX - bounds.left) / bounds.width * props.imageWidth)),
    y: Math.max(0, Math.min(props.imageHeight, (event.clientY - bounds.top) / bounds.height * props.imageHeight)),
  }
}

function beginMove(event: PointerEvent) {
  if ((event.target as HTMLElement).classList.contains('crop-handle')) return
  const point = pointInImage(event)
  drag = { mode: 'move', pointerX: point.x, pointerY: point.y, crop: { ...crop.value } }
  beginDragListeners()
  event.preventDefault()
}

function beginResize(corner: Corner, event: PointerEvent) {
  const current = crop.value
  const east = corner.endsWith('e')
  const south = corner.startsWith('s')
  drag = {
    mode: 'resize',
    corner,
    anchorX: east ? current.x : current.x + current.w,
    anchorY: south ? current.y : current.y + current.h,
    signX: east ? 1 : -1,
    signY: south ? 1 : -1,
  }
  beginDragListeners()
  event.preventDefault()
  event.stopPropagation()
}

function beginDragListeners() {
  window.addEventListener('pointermove', continueDrag)
  window.addEventListener('pointerup', endDrag, { once: true })
  window.addEventListener('pointercancel', endDrag, { once: true })
}

function continueDrag(event: PointerEvent) {
  if (!drag) return
  const point = pointInImage(event)
  if (drag.mode === 'move') {
    const x = drag.crop.x + point.x - drag.pointerX
    const y = drag.crop.y + point.y - drag.pointerY
    emit('update:modelValue', {
      ...drag.crop,
      x: Math.round(Math.max(0, Math.min(x, props.imageWidth - drag.crop.w))),
      y: Math.round(Math.max(0, Math.min(y, props.imageHeight - drag.crop.h))),
    })
    return
  }

  const aspectWidth = Math.max(1, Math.round(props.aspectWidth))
  const aspectHeight = Math.max(1, Math.round(props.aspectHeight))
  const ratio = aspectWidth / aspectHeight
  const requestedWidth = Math.max(
    Math.abs(point.x - drag.anchorX),
    Math.abs(point.y - drag.anchorY) * ratio,
  )
  const horizontalLimit = drag.signX > 0 ? props.imageWidth - drag.anchorX : drag.anchorX
  const verticalLimit = drag.signY > 0 ? props.imageHeight - drag.anchorY : drag.anchorY
  const maxWidth = Math.min(horizontalLimit, verticalLimit * ratio)
  const maxUnit = Math.max(1, Math.floor(maxWidth / aspectWidth))
  const unit = Math.max(1, Math.min(maxUnit, Math.round(requestedWidth / aspectWidth)))
  const w = unit * aspectWidth
  const h = unit * aspectHeight
  emit('update:modelValue', {
    x: Math.round(drag.signX > 0 ? drag.anchorX : drag.anchorX - w),
    y: Math.round(drag.signY > 0 ? drag.anchorY : drag.anchorY - h),
    w,
    h,
  })
}

function endDrag() {
  drag = null
  window.removeEventListener('pointermove', continueDrag)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('pointercancel', endDrag)
}

function resetCrop() {
  emit('update:modelValue', largestCenteredCrop())
}

watch(
  () => [props.imageUrl, props.imageWidth, props.imageHeight, props.aspectWidth, props.aspectHeight, props.modelValue] as const,
  () => {
    const normalized = normalize(props.modelValue)
    if (!sameCrop(normalized, props.modelValue)) emit('update:modelValue', normalized)
  },
  { immediate: true, deep: true },
)

onBeforeUnmount(endDrag)
</script>

<template>
  <div class="image-cropper">
    <div ref="surface" class="crop-surface" :style="surfaceStyle">
      <img :src="imageUrl" alt="裁剪原图" draggable="false" />
      <div class="crop-selection" :style="selectionStyle" @pointerdown="beginMove">
        <i class="crop-grid crop-grid--v1" /><i class="crop-grid crop-grid--v2" />
        <i class="crop-grid crop-grid--h1" /><i class="crop-grid crop-grid--h2" />
        <button v-for="corner in (['nw', 'ne', 'sw', 'se'] as Corner[])" :key="corner" type="button" class="crop-handle" :class="`crop-handle--${corner}`" :aria-label="`缩放 ${corner}`" @pointerdown="beginResize(corner, $event)" />
      </div>
    </div>
    <div class="cropper-footer">
      <span>拖动选区调整位置，拖动四角缩放</span>
      <button type="button" @click="resetCrop"><Maximize2 :size="14" />最大居中</button>
    </div>
  </div>
</template>

<style scoped>
.image-cropper { width: 100%; }
.crop-surface { position: relative; width: 100%; overflow: hidden; touch-action: none; user-select: none; border: 1px solid #ffffff18; border-radius: 14px 5px; background: #0b110d; }
.crop-surface > img { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.crop-selection { position: absolute; cursor: move; touch-action: none; border: 2px solid #f5df9a; box-shadow: 0 0 0 9999px #020503a8, 0 0 0 1px #0008 inset; }
.crop-grid { position: absolute; display: block; pointer-events: none; background: #fff6; }.crop-grid--v1,.crop-grid--v2 { top: 0; bottom: 0; width: 1px; }.crop-grid--v1 { left: 33.333%; }.crop-grid--v2 { left: 66.666%; }.crop-grid--h1,.crop-grid--h2 { left: 0; right: 0; height: 1px; }.crop-grid--h1 { top: 33.333%; }.crop-grid--h2 { top: 66.666%; }
.crop-handle { position: absolute; width: 18px; height: 18px; padding: 0; border: 3px solid #f5df9a; border-radius: 50%; background: #253421; box-shadow: 0 2px 8px #0008; touch-action: none; }.crop-handle--nw { left: -10px; top: -10px; cursor: nwse-resize; }.crop-handle--ne { right: -10px; top: -10px; cursor: nesw-resize; }.crop-handle--sw { left: -10px; bottom: -10px; cursor: nesw-resize; }.crop-handle--se { right: -10px; bottom: -10px; cursor: nwse-resize; }
.cropper-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 9px; color: #7f8b82; font-size: 12px; }.cropper-footer button { min-height: 30px; display: inline-flex; align-items: center; gap: 5px; padding: 0 9px; white-space: nowrap; color: #bcc9b8; border: 1px solid #ffffff16; border-radius: 8px; background: #ffffff05; cursor: pointer; }
</style>

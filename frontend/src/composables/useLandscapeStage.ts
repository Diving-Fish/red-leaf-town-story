import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 舞台剧情按 16:9 横屏排版。桌面端什么都不用做；
 * 触摸设备优先请求全屏并锁定横屏，锁不上（iOS Safari 不支持）时由调用方显示旋转提示。
 */
export function useLandscapeStage() {
  const isPortrait = ref(false)
  const isTouch = ref(false)
  const orientationQuery = window.matchMedia('(orientation: portrait)')
  const pointerQuery = window.matchMedia('(pointer: coarse)')

  function sync() {
    isPortrait.value = orientationQuery.matches
    isTouch.value = pointerQuery.matches
  }

  async function lockLandscape(element: HTMLElement | null) {
    if (!isTouch.value) return
    try {
      await (element || document.documentElement).requestFullscreen?.()
    } catch {
      // 没有用户手势或浏览器不允许全屏时继续尝试锁定方向。
    }
    try {
      await (screen.orientation as ScreenOrientation & { lock?: (value: string) => Promise<void> })?.lock?.('landscape')
    } catch {
      // iOS Safari 不支持方向锁定，只能提示玩家自己把手机横过来。
    }
  }

  async function releaseLandscape() {
    try {
      screen.orientation?.unlock?.()
    } catch {
      // 没锁上就不需要解锁。
    }
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
    } catch {
      // 已经退出全屏。
    }
  }

  onMounted(() => {
    sync()
    orientationQuery.addEventListener('change', sync)
    pointerQuery.addEventListener('change', sync)
  })
  onBeforeUnmount(() => {
    orientationQuery.removeEventListener('change', sync)
    pointerQuery.removeEventListener('change', sync)
  })

  return { isPortrait, isTouch, lockLandscape, releaseLandscape }
}

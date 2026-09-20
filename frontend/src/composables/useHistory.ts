import { ref, shallowRef, toRaw, type Ref } from 'vue'

const LIMIT = 120
/** 同一类连续操作（比如连着打字）在这个窗口内并成一次撤销。 */
const COALESCE_MS = 700

/**
 * 快照式撤销栈。每次改动前把当前状态存一份，
 * 相邻的同类改动会合并，所以打一句台词是一次撤销，而不是一个字一次。
 *
 * state 是**深层**响应式的：步骤是就地增删改的，模板和 computed 要能跟着动。
 * 用 shallowRef + triggerRef 会让"返回同一个数组"的 computed 短路，下游全部收不到通知。
 */
export function useHistory<T extends object>(initial: T) {
  const state = ref(initial) as Ref<T>
  // 快照本身不需要响应式，只有长度要驱动按钮的禁用态，所以整包替换。
  const past = shallowRef<T[]>([])
  const future = shallowRef<T[]>([])
  let lastLabel = ''
  let lastAt = 0

  function snapshot(): T {
    return JSON.parse(JSON.stringify(toRaw(state.value))) as T
  }

  function mutate(label: string, apply: (draft: T) => void) {
    const now = Date.now()
    const merge = label === lastLabel && now - lastAt < COALESCE_MS
    if (!merge) past.value = [...past.value, snapshot()].slice(-LIMIT)
    future.value = []
    lastLabel = label
    lastAt = now
    apply(state.value)
  }

  function undo() {
    if (!past.value.length) return
    const previous = past.value[past.value.length - 1]
    past.value = past.value.slice(0, -1)
    future.value = [...future.value, snapshot()]
    state.value = previous
    lastLabel = ''
  }

  function redo() {
    if (!future.value.length) return
    const next = future.value[future.value.length - 1]
    future.value = future.value.slice(0, -1)
    past.value = [...past.value, snapshot()]
    state.value = next
    lastLabel = ''
  }

  /** 换一份草稿：历史从头开始，不能撤销回上一份草稿。 */
  function reset(value: T) {
    state.value = value
    past.value = []
    future.value = []
    lastLabel = ''
  }

  return { state, past, future, mutate, undo, redo, reset }
}

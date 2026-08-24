<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronLeft, Inbox, Mail, MailOpen, Megaphone, Paperclip, X } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import RewardChips from '@/components/RewardChips.vue'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { MailEntry } from '@/types'

const game = useGameStore()
const ui = useUiStore()

const entries = ref<MailEntry[]>([])
const openedId = ref('')
const loaded = ref(false)

const opened = computed(() => entries.value.find((entry) => entry.mail_id === openedId.value) || null)
const unreadCount = computed(() => entries.value.filter((entry) => !entry.read).length)
// 手机上列表和信纸是同一条轨道上的两屏，选中一封就整体推到第二屏。
const readingPane = computed(() => Boolean(openedId.value))

watch(
  () => ui.mailOpen,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
    if (open) {
      document.addEventListener('keydown', onKeydown)
      load()
    } else {
      document.removeEventListener('keydown', onKeydown)
      openedId.value = ''
    }
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  // 手机上的返回键语义：先退回列表，再退出收件箱。
  if (openedId.value && window.matchMedia('(max-width: 760px)').matches) openedId.value = ''
  else ui.mailOpen = false
}

async function load() {
  const mailbox = await game.loadMailbox()
  if (!mailbox) return
  entries.value = mailbox.entries
  loaded.value = true
  await nextTick()
  // 宽屏进来就摊开最新一封，窄屏保持列表，等用户自己点。
  if (!openedId.value && !window.matchMedia('(max-width: 760px)').matches && entries.value.length) {
    openLetter(entries.value[0])
  }
}

async function openLetter(entry: MailEntry) {
  openedId.value = entry.mail_id
  if (entry.read) return
  entry.read = true
  await game.readMail(entry.mail_id)
}

async function claim(entry: MailEntry | null) {
  if (!entry) return
  const result = await game.claimMail(entry.mail_id)
  if (!result) return
  entry.claimed = true
  entry.claimable = false
}

function postmark(seconds: number) {
  const date = new Date(seconds * 1000)
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

function stampYear(seconds: number) {
  return new Date(seconds * 1000).getFullYear()
}

function scopeLabel(entry: MailEntry) {
  return entry.scope === 'global' ? '镇公告' : '亲展'
}
</script>

<template>
  <Teleport to="body">
    <Transition name="postbox">
      <div v-if="ui.mailOpen" class="postbox-backdrop" @click.self="ui.mailOpen = false">
        <section class="postbox" role="dialog" aria-modal="true" aria-label="收件箱">
          <header class="postbox-heading">
            <span class="postbox-seal"><Inbox :size="19" /></span>
            <div>
              <p class="eyebrow">TOWN POST OFFICE</p>
              <h2>收件箱</h2>
            </div>
            <small v-if="loaded">{{ entries.length }} 封 · {{ unreadCount }} 封未读</small>
            <button class="icon-button" aria-label="关闭收件箱" @click="ui.mailOpen = false"><X :size="19" /></button>
          </header>

          <div class="postbox-body" :class="{ reading: readingPane }">
            <aside class="letter-rail">
              <div v-if="loaded && !entries.length" class="rail-empty" aria-label="信箱是空的"><Inbox :size="30" /></div>
              <p v-else-if="!loaded" class="rail-loading">正在打开信箱……</p>
              <button
                v-for="entry in entries"
                :key="entry.mail_id"
                class="letter-card"
                :class="{ unread: !entry.read, active: entry.mail_id === openedId }"
                @click="openLetter(entry)"
              >
                <span class="letter-icon"><Mail v-if="!entry.read" :size="17" /><MailOpen v-else :size="17" /></span>
                <span class="letter-copy">
                  <b>{{ entry.title }}</b>
                  <em>{{ entry.sender }}</em>
                </span>
                <span class="letter-meta">
                  <i class="scope-stamp" :class="entry.scope">{{ scopeLabel(entry) }}</i>
                  <time>{{ postmark(entry.created_at) }}</time>
                </span>
                <Paperclip v-if="entry.claimable" class="clip" :size="14" />
              </button>
            </aside>

            <article class="letter-pane">
              <template v-if="opened">
                <button class="back-button" @click="openedId = ''"><ChevronLeft :size="17" />返回信件列表</button>

                <div class="letter-scroll">
                  <div class="paper">
                    <div class="postmark" aria-hidden="true">
                      <b>{{ postmark(opened.created_at) }}</b>
                      <i>{{ stampYear(opened.created_at) }}</i>
                    </div>
                    <p class="paper-scope">
                      <Megaphone v-if="opened.scope === 'global'" :size="13" />
                      <Mail v-else :size="13" />
                      {{ opened.scope === 'global' ? '致红叶镇全体居民' : '亲启' }}
                    </p>
                    <h3>{{ opened.title }}</h3>
                    <div class="paper-body">{{ opened.body }}</div>
                    <p class="signature"><span class="signet">{{ opened.sender.slice(0, 1) }}</span>—— {{ opened.sender }}</p>
                  </div>
                </div>

                <footer v-if="!opened.attachments.empty" class="letter-tray">
                  <div>
                    <small><Paperclip :size="13" />随信附上</small>
                    <RewardChips :reward="opened.attachments" />
                  </div>
                  <ActionButton
                    v-if="opened.claimable"
                    :action-key="`mail:claim:${opened.mail_id}`"
                    @click="claim(opened)"
                  >
                    领取附件
                  </ActionButton>
                  <span v-else class="claimed-mark">已领取</span>
                </footer>
              </template>

              <div v-else-if="loaded" class="pane-empty" aria-hidden="true"><MailOpen :size="42" /></div>
            </article>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.postbox-backdrop { position: fixed; inset: 0; z-index: 75; display: grid; place-items: center; padding: 22px; background: rgba(5, 8, 6, .74); backdrop-filter: blur(6px); }
.postbox {
  display: flex;
  flex-direction: column;
  width: min(940px, 100%);
  height: min(660px, calc(100dvh - 44px));
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 26px 8px 26px 8px;
  background: #16201a;
  box-shadow: 0 40px 110px #000a;
}

.postbox-heading { display: grid; grid-template-columns: auto 1fr auto auto; align-items: center; gap: 13px; padding: 16px 18px; border-bottom: 1px solid var(--line); background: #1a251e; }
.postbox-seal { width: 40px; height: 40px; display: grid; place-items: center; color: var(--gold); border: 1px solid #d7ad5840; border-radius: 14px 5px 14px 5px; background: #d7ad580d; }
.postbox-heading h2 { margin: 3px 0 0; font: 700 19px Georgia, 'Noto Serif SC', serif; }
.postbox-heading > small { color: #7f8a80; }
.postbox-body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 290px) minmax(0, 1fr); }

/* 左栏：一摞信封 */
.letter-rail { min-height: 0; overflow: auto; padding: 11px; display: flex; flex-direction: column; gap: 7px; border-right: 1px solid var(--line); background: #121a15; }
.rail-loading { margin: 20px 0; color: #78837a; text-align: center; }
.rail-empty,.pane-empty { flex: 1; display: grid; place-items: center; color: #3f4a43; }
.letter-card {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px 11px;
  text-align: left;
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  border-radius: 12px 4px 12px 4px;
  background: #ffffff05;
  cursor: pointer;
  transition: background .16s, border-color .16s;
}
.letter-card:hover { background: #ffffff0b; }
.letter-card.active { border-color: #d7ad5836; border-left-color: var(--gold); background: #d7ad580e; }
.letter-icon { width: 32px; height: 32px; display: grid; place-items: center; color: #7d8a7f; border-radius: 50%; background: #ffffff07; }
.letter-card.unread .letter-icon { color: var(--autumn); background: #dc74451a; }
.letter-copy { min-width: 0; display: grid; gap: 3px; }
.letter-copy b { overflow: hidden; color: #a3ada4; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.letter-card.unread .letter-copy b { color: var(--cream); font-weight: 700; }
.letter-copy em { overflow: hidden; color: #758077; font-size: 12px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }
.letter-meta { display: grid; justify-items: end; gap: 4px; }
.letter-meta time { color: #6d786f; font-size: 11px; }
.scope-stamp { padding: 2px 6px; font-size: 10px; font-style: normal; letter-spacing: .08em; border: 1px solid currentColor; border-radius: 3px; }
.scope-stamp.global { color: #b08154; }
.scope-stamp.player { color: #9a8348; }
.clip { position: absolute; left: -3px; top: -3px; color: var(--gold); transform: rotate(-24deg); }

/* 右栏：摊开的信纸 */
.letter-pane { min-width: 0; min-height: 0; display: flex; flex-direction: column; padding: 16px; }
.back-button { display: none; }
.letter-scroll { flex: 1; min-height: 0; overflow: auto; padding: 4px 2px 8px; }
.paper {
  position: relative;
  padding: 34px 32px 30px;
  color: #35382c;
  border-radius: 2px;
  /* 泛黄的信纸：暖色底 + 两道极淡的纤维纹，落在深色面板上像真的放了一张纸。 */
  background:
    repeating-linear-gradient(90deg, #00000005 0 1px, transparent 1px 4px),
    repeating-linear-gradient(0deg, #00000004 0 1px, transparent 1px 5px),
    linear-gradient(168deg, #ece2ca, #ded2b6);
  box-shadow: 0 16px 38px #0007, inset 0 0 60px #a68d5c1f;
}
.postmark {
  position: absolute;
  right: 26px;
  top: 22px;
  width: 62px;
  height: 62px;
  display: grid;
  place-content: center;
  gap: 2px;
  text-align: center;
  color: #9d4b32;
  border: 1.5px solid currentColor;
  border-radius: 50%;
  opacity: .42;
  transform: rotate(-11deg);
}
.postmark b { font-size: 12px; letter-spacing: .02em; }
.postmark i { display: block; padding-top: 2px; border-top: 1px solid currentColor; font-size: 9px; font-style: normal; letter-spacing: .1em; }
.paper-scope { display: inline-flex; align-items: center; gap: 5px; margin: 0; color: #7d6a45; font-size: 12px; letter-spacing: .1em; }
.paper h3 { max-width: calc(100% - 76px); margin: 10px 0 18px; color: #2b2f24; font: 700 24px Georgia, 'Noto Serif SC', serif; line-height: 1.4; }
.paper-body { padding-top: 17px; border-top: 1px dashed #8a7a5566; font-family: Georgia, 'Noto Serif SC', serif; font-size: 15px; line-height: 2.15; white-space: pre-wrap; word-break: break-word; }
.signature { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin: 26px 0 0; color: #4a4436; font-family: Georgia, 'Noto Serif SC', serif; font-size: 15px; }
.signet { width: 30px; height: 30px; display: grid; place-items: center; color: #f0e7d2; font-size: 15px; font-weight: 700; background: #9d4b32d9; border-radius: 3px; transform: rotate(4deg); }

.letter-tray { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 14px; margin-top: 14px; padding: 13px 15px; border: 1px solid var(--line); border-radius: 13px 4px 13px 4px; background: #101812; }
.letter-tray small { display: flex; align-items: center; gap: 5px; margin-bottom: 8px; color: #7f8a80; }
.claimed-mark { color: #6f7a71; font-size: 12px; white-space: nowrap; }

.postbox-enter-active, .postbox-leave-active { transition: opacity .2s ease; }
.postbox-enter-active .postbox, .postbox-leave-active .postbox { transition: transform .22s ease; }
.postbox-enter-from, .postbox-leave-to { opacity: 0; }
.postbox-enter-from .postbox, .postbox-leave-to .postbox { transform: translateY(16px) scale(.98); }

@media (max-width: 760px) {
  .postbox-backdrop { padding: 0; }
  .postbox { width: 100%; height: 100dvh; border: 0; border-radius: 0; }
  .postbox-heading { padding: calc(14px + env(safe-area-inset-top)) 15px 14px; }
  .postbox-heading > small { display: none; }
  /* 两屏一轨：列表在左，信纸在右，选中就整体推过去。 */
  .postbox-body { grid-template-columns: 100% 100%; transition: transform .26s ease; }
  .postbox-body.reading { transform: translateX(-100%); }
  .letter-rail { border-right: 0; }
  .letter-pane { padding: 12px 13px calc(13px + env(safe-area-inset-bottom)); }
  .back-button { display: flex; align-items: center; gap: 4px; align-self: flex-start; margin-bottom: 11px; padding: 7px 11px 7px 7px; color: #97a398; border: 1px solid var(--line); border-radius: 99px; background: #ffffff05; cursor: pointer; }
  .paper { padding: 26px 20px 24px; }
  .postmark { right: 16px; top: 16px; width: 54px; height: 54px; }
  .paper h3 { max-width: calc(100% - 62px); font-size: 21px; }
  .paper-body { font-size: 14px; line-height: 2; }
  .letter-tray { grid-template-columns: 1fr; }
  .postbox-enter-from .postbox, .postbox-leave-to .postbox { transform: translateY(100%); }
}
</style>

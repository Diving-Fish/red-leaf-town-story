<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Anchor, Check, Compass, Fish, Lock, Package, Sailboat, Waves } from 'lucide-vue-next'
import ActionButton from '@/components/ActionButton.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import StateBlock from '@/components/StateBlock.vue'
import PartnerAvatar from '@/components/PartnerAvatar.vue'
import { useCountdown } from '@/composables/useCountdown'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'
import type { OwnedPartner } from '@/types'

const game = useGameStore()
const sailing = computed(() => game.state?.sailing)
const selectedRoute = ref('reed_bay')
const selectedSupply = ref('none')
const party = ref<string[]>([])
const requestId = ref(crypto.randomUUID())
const route = computed(() => sailing.value?.routes.find(r => r.id === selectedRoute.value))
const supply = computed(() => sailing.value?.supplies.find(s => s.id === selectedSupply.value))
const run = computed(() => sailing.value?.active_run)
const journal = computed(() => run.value ? (elapsed.value ? run.value : null) : sailing.value?.last_run)
const { label, progress, elapsed } = useCountdown(() => run.value?.ready_at, () => run.value ? run.value.ready_at - run.value.started_at : 0)
const attributeNames: Record<string, string> = { strength: '力量', agility: '敏捷', intelligence: '智力', luck: '幸运' }
const blockedReason = computed(() => {
  if (!route.value?.unlocked) return '这条航线尚未开放'
  if (!party.value.length) return '请至少选择一名伙伴'
  if (party.value.some(id => unavailable(game.state!.partners.find(p => p.partner_id === id)!))) return '队伍中有忙碌的伙伴'
  if ((game.player?.coins || 0) < route.value.coins) return '红叶币不足'
  if (game.liveStamina < route.value.stamina) return '体力不足'
  if (supply.value && supply.value.owned < supply.value.quantity) return '额外补给不足'
  return ''
})

function unavailable(partner: OwnedPartner | undefined) {
  return !partner || partner.missing || (partner.locked && (partner.locked_until || 0) > game.serverNow)
    || Boolean(game.state?.exploration.active_run?.partner_ids.includes(partner.partner_id))
}

function tendencyText(partner: OwnedPartner) {
  return (partner.tendencies || []).filter(t => ['aquatic', 'exploration'].includes(t.industry))
    .map(t => `${t.industry === 'aquatic' ? '水产' : '探索'} ${t.effective_ability}`).join(' · ') || '可协助航海检定'
}

function togglePartner(id: string) {
  party.value = party.value.includes(id) ? party.value.filter(p => p !== id) : [...party.value, id].slice(0, 3)
}

watch([selectedRoute, selectedSupply, party], () => { requestId.value = crypto.randomUUID() })
watch(elapsed, ready => { if (ready) void game.refresh(true) })

async function start() {
  const result = await game.startSailing(selectedRoute.value, party.value, selectedSupply.value, requestId.value)
  if (result) requestId.value = crypto.randomUUID()
}
</script>

<template>
  <section class="sailing-view" aria-label="旧港出海">
    <StateBlock v-if="!sailing" title="旧港尚未开放" description="出海目前仅对内测玩家开放。" />
    <StateBlock v-else-if="!sailing.unlocked" :title="`居民 ${sailing.min_level} 级开放出海`" description="码头已备好第一艘船，达到等级后即可试航。" />
    <template v-else>
      <article class="harbor-banner">
        <div class="harbor-copy">
          <div class="harbor-eyebrow"><span class="harbor-label">{{ run ? (elapsed ? 'WELCOME HOME' : 'OUT AT SEA') : 'THE OLD HARBOR' }}</span><span class="harbor-status">{{ run ? (elapsed ? '等待领取' : '航行中') : '准备离港' }}</span></div>
          <h2>{{ run ? (elapsed ? '船已回港，收获在等你' : `正在驶向${run.route_name}`) : '初帆号，向海风出发' }}</h2>
          <p>{{ run ? '航行途中无需操作，回港后伙伴自动恢复自由。收获会一直保留。' : '安排伙伴、带上补给。海上的故事会在归航时，一起装进你的航海日志。' }}</p>
          <div v-if="!run" class="harbor-destination">
            <span>本次目的地</span><strong>{{ route?.name }}</strong><span>{{ sailing.trial_available ? '60 秒试航' : formatDuration(route?.duration || 0) }}</span>
          </div>
          <div class="harbor-facts"><span><Sailboat :size="16" /> 初帆号</span><span>{{ sailing.completed_voyages }} 次归航</span><span>{{ sailing.discoveries.filter(d => d.discovered).length }} / {{ sailing.discoveries.length }} 种见闻</span></div>
        </div>
        <div class="boat-scene" aria-hidden="true">
          <svg viewBox="0 0 320 230" fill="none">
            <circle cx="175" cy="107" r="87" stroke="#9BCBC2" stroke-opacity=".16" />
            <circle cx="175" cy="107" r="105" stroke="#9BCBC2" stroke-opacity=".12" stroke-dasharray="3 9" />
            <path d="M175 0V18M175 196V214M68 107H87M262 107H281" stroke="#C4DDCA" stroke-opacity=".45" />
            <circle cx="218" cy="59" r="26" fill="#E4C993" fill-opacity=".18" />
            <path d="M14 144L52 127L89 144L118 136L149 150L203 129L251 147L303 135" stroke="#76AEA6" stroke-opacity=".28" />
            <path d="M172 35V162" stroke="#E6D4AF" stroke-width="3" stroke-linecap="round" />
            <path d="M164 45L112 139H164V45Z" fill="#E9DCBC" fill-opacity=".95" />
            <path d="M181 73L224 139H181V73Z" fill="#B2CCC0" />
            <path d="M105 155H237L221 176H126L105 155Z" fill="#AC7951" />
            <path d="M118 160H224" stroke="#EACDA0" stroke-opacity=".65" />
            <path d="M75 185C106 178 127 191 159 185C190 179 218 190 256 182M103 202C132 196 151 209 183 201C205 196 221 200 235 198" stroke="#A5D4CC" stroke-opacity=".6" stroke-linecap="round" />
            <path d="M37 83L43 79L50 83M63 60L70 56L77 60" stroke="#AFCCC0" stroke-opacity=".5" stroke-linecap="round" />
          </svg>
        </div>
      </article>

      <article v-if="run" class="sailing-panel voyage-status" aria-live="polite">
        <div class="panel-heading"><h2><Waves :size="20" /> {{ run.route_name }}{{ run.trial ? ' · 首次试航' : '' }}</h2><strong>{{ elapsed ? '已回港' : label }}</strong></div>
        <ProgressBar :value="progress" color="#80c8cb" :height="8" />
        <p>{{ run.partner_ids.map(id => game.state?.partners.find(p => p.partner_id === id)?.name || id).join('、') }} · 出航能力 {{ run.ability }}</p>
        <ActionButton action-key="sailing:collect" :disabled="!elapsed" @click="game.collectSailing(run.run_id)">{{ elapsed ? '领取航海收获' : '伙伴正在航行' }}</ActionButton>
      </article>

      <template v-else>
        <div v-if="sailing.trial_available" class="trial-note"><Compass :size="20" /><div><strong>你的第一次航行，只需 60 秒</strong><p>芦苇海湾试航消耗 20 红叶币、1 体力，带回少量物产。完成后恢复正常航程。</p></div></div>
        <section class="route-selection" aria-label="选择航线">
        <div class="section-title"><span>01</span><h2>选择航线</h2><small>一次旅程，一处新发现</small></div>
        <div class="sailing-route-grid">
          <button v-for="r in sailing.routes" :key="r.id" class="route-card" :class="{ selected: selectedRoute === r.id, unavailable: !r.unlocked }" :disabled="!r.unlocked" :aria-pressed="selectedRoute === r.id" @click="selectedRoute = r.id">
            <div class="route-heading"><span class="route-seal"><Compass :size="23" /></span><span>{{ r.unlocked ? formatDuration(r.duration) : '待发现' }}</span></div>
            <h3>{{ r.name }}</h3><p>{{ r.description }}</p>
            <div class="route-produce"><Fish :size="16" /> {{ r.common_name }} · {{ r.rare_name }}</div>
            <div class="route-footer"><span v-if="r.unlocked">{{ r.coins }} 红叶币 · {{ r.stamina }} 体力</span><span v-else><Lock :size="13" /> 完成 {{ r.required_voyages }} 次航行开放</span><Check v-if="selectedRoute === r.id" :size="18" /></div>
          </button>
        </div>
        </section>
        <div class="sailing-preparation">
          <article class="sailing-panel crew-panel">
            <div class="section-title"><span>02</span><h2>安排伙伴</h2><small>{{ party.length }} / 3</small></div>
            <p class="muted">水产倾向擅长捕捞，探索倾向擅长群岛。所有伙伴都能参与航海检定；出航会撤下原有驻场安排。</p>
            <div class="crew-list">
              <button v-for="partner in game.state?.partners" :key="partner.partner_id" class="crew-option" :class="{ selected: party.includes(partner.partner_id) }" :disabled="unavailable(partner) || (!party.includes(partner.partner_id) && party.length >= 3)" :aria-pressed="party.includes(partner.partner_id)" @click="togglePartner(partner.partner_id)">
                <PartnerAvatar :artwork="partner.artwork" :crop="partner.avatar_crop" :name="partner.name" :size="38" />
                <div class="crew-copy"><strong>{{ partner.name }}</strong><small>{{ unavailable(partner) ? '暂时无法出航' : tendencyText(partner) }}</small></div><Check v-if="party.includes(partner.partner_id)" :size="18" /><span v-else>Lv.{{ partner.level }}</span>
              </button>
              <p v-if="!game.state?.partners.length" class="muted">先去招募一名伙伴，再一起出海吧。</p>
            </div>
          </article>
          <article class="sailing-panel departure-panel">
            <div class="section-title"><span>03</span><h2>准备补给</h2></div>
            <div class="supply-list">
              <button v-for="s in sailing.supplies" :key="s.id" class="supply-option" :class="{ selected: selectedSupply === s.id }" :aria-pressed="selectedSupply === s.id" @click="selectedSupply = s.id">
                <div><strong>{{ s.name }}</strong><p>{{ s.description }}</p><small v-if="s.quantity">{{ s.item_name }} {{ s.owned }} / {{ s.quantity }} · 优先使用低品质</small></div><Check v-if="selectedSupply === s.id" :size="18" />
              </button>
            </div>
            <div class="departure-summary"><span class="departure-caption">本次航行</span><span>{{ route?.name }} · {{ formatDuration(route?.duration || 0) }}</span><strong>{{ route?.coins }} 红叶币 ＋ {{ route?.stamina }} 体力</strong></div>
            <ActionButton class="departure-button" action-key="sailing:start" group="sailing:" :disabled="Boolean(blockedReason)" :reason="blockedReason" @click="start"><Sailboat :size="18" /> {{ blockedReason || '准备好了，出航' }}</ActionButton>
          </article>
        </div>
      </template>

      <article v-if="journal" class="sailing-panel journal-panel">
        <div class="panel-heading"><h2><Compass :size="20" /> {{ run ? '本次航海日志' : '上次航海日志' }}</h2><span>{{ journal.route_name }}</span></div>
        <div class="sailing-loot"><span v-for="drop in journal.drops" :key="drop.item_id"><Package :size="15" /> {{ drop.name }} ×{{ drop.quantity }}</span><span>居民经验 ＋{{ journal.experience }}</span></div>
        <ol class="journal-list"><li v-for="log in journal.logs" :key="log.event_id"><strong>{{ log.name }}</strong><p>{{ log.text }}</p><small>{{ game.state?.partners.find(p => p.partner_id === log.actor_id)?.name || log.actor_id }} · {{ attributeNames[log.attribute] }}检定 {{ log.roll }} {{ log.modifier >= 0 ? '+' : '−' }} {{ Math.abs(log.modifier) }} · {{ log.success ? '成功' : '未成功' }}</small></li></ol>
      </article>
      <div class="sailing-bottom-grid">
        <article class="sailing-panel"><div class="panel-heading"><h2><Anchor :size="20" /> 船舶改装</h2><span>最高三级</span></div><div v-for="upgrade in sailing.upgrades" :key="upgrade.kind" class="upgrade-row"><div><strong>{{ upgrade.name }} Lv.{{ upgrade.level }}</strong><p>{{ upgrade.description }}</p><small v-if="upgrade.level < 3">{{ upgrade.coins }} 红叶币 · {{ upgrade.item_name }} {{ upgrade.owned }} / {{ upgrade.quantity }}</small></div><ActionButton :action-key="`sailing:upgrade:${upgrade.kind}`" group="sailing:" variant="secondary" :disabled="Boolean(run) || upgrade.level >= 3 || (game.player?.coins || 0) < upgrade.coins || upgrade.owned < upgrade.quantity" @click="game.upgradeSailing(upgrade.kind, upgrade.level)">{{ upgrade.level >= 3 ? '已满级' : '改装' }}</ActionButton></div><p v-if="run" class="muted">回港领取收获后可以改装。</p></article>
        <article class="sailing-panel"><div class="panel-heading"><h2><Fish :size="20" /> 航海见闻册</h2></div><div class="collection-grid"><div v-for="item in sailing.collection" :key="item.item_id"><strong>{{ item.quantity ? item.name : '？' }}</strong><small>{{ item.quantity ? `累计带回 ${item.quantity}` : '尚未发现' }}</small></div></div><div class="discovery-list"><span v-for="entry in sailing.discoveries" :key="entry.id" :class="{ discovered: entry.discovered }">{{ entry.discovered ? '✓' : '◇' }} {{ entry.name }}</span></div></article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.sailing-view { --sea: #91cec7; display: grid; gap: 28px; min-width: 0; }
.harbor-banner { position: relative; display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(190px, 1fr); align-items: center; gap: 20px; padding: 32px 36px; border: 1px solid #82c9cb45; border-radius: 22px; background: radial-gradient(ellipse at 85% 20%, #518d7b24, transparent 70%), linear-gradient(120deg, #203f38, #152e2e 75%); box-shadow: inset 0 1px #b6dfd518, 0 16px 40px #0002; overflow: hidden; }
.harbor-copy { position: relative; max-width: 570px; }
.harbor-eyebrow { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.harbor-label { color: #b7d4c7; font-size: 12px; letter-spacing: .18em; }
.harbor-status { padding: 4px 9px; border: 1px solid #c6d5a735; border-radius: 6px; color: #d9ddb4; font-size: 12px; }
.harbor-copy h2 { margin: 18px 0 12px; color: #f4ecda; font: 600 clamp(24px, 2.8vw, 34px)/1.4 Georgia, 'Noto Serif SC', serif; letter-spacing: .02em; }
.harbor-copy p, .muted { margin: 0; color: #b4c8bf; font-size: 13px; line-height: 1.85; }
.harbor-destination { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 24px; padding: 13px 0; border-top: 1px solid #bbd7c620; border-bottom: 1px solid #bbd7c620; font-size: 12px; color: #a3bfb2; }
.harbor-destination strong { color: #e7d4a3; font-size: 16px; }
.harbor-destination > span:last-child { margin-left: auto; color: #e7d4a3; }
.harbor-facts { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 20px; color: #a4c5b8; font-size: 12px; }
.harbor-facts span, .panel-heading h2, .route-produce { display: flex; align-items: center; gap: 8px; }
.boat-scene { align-self: stretch; display: grid; place-items: center; min-width: 0; }
.boat-scene svg { display: block; width: 100%; max-width: 340px; }
.sailing-panel { padding: 24px; border-radius: 18px; border: 1px solid #bfd5c71b; background: #14221dd9; min-width: 0; }
.section-title { display: flex; align-items: center; gap: 10px; margin: 0 0 18px; }
.section-title > span { display: grid; place-items: center; flex: 0 0 28px; height: 28px; border: 1px solid #91cec72a; border-radius: 8px; color: var(--sea); font-size: 12px; }
.section-title h2, .panel-heading h2 { margin: 0; color: #ebe5d8; font-size: 18px; font-weight: 600; }
.section-title small { margin-left: auto; text-align: right; }
.panel-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.panel-heading > span, .panel-heading > strong { color: var(--sea); font-size: 13px; }
.trial-note { display: flex; align-items: center; gap: 14px; padding: 18px 22px; border: 1px solid #d4bd8030; border-left: 3px solid #d4bd80; border-radius: 4px 12px 12px 4px; background: #d4bd8008; color: #e1ce9b; }
.trial-note > svg { flex-shrink: 0; }
.trial-note strong { font-size: 14px; }
.trial-note p { margin: 6px 0 0; color: #a6b6a9; font-size: 13px; line-height: 1.7; }
.sailing-route-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.route-card { text-align: left; color: inherit; background: #13211bd9; border: 1px solid #bfd5c720; border-radius: 16px; padding: 22px; cursor: pointer; display: flex; flex-direction: column; min-width: 0; transition: border-color .18s, background .18s; }
.route-card:hover:not(:disabled) { border-color: #91cec770; }
.route-card.selected { border-color: #a3d2bb99; background: linear-gradient(145deg, #2b4d3c95, #192e2680); box-shadow: inset 0 3px #a3d2bb, 0 8px 22px #0002; }
.crew-option.selected, .supply-option.selected { border-color: #91cec77a; background: #91cec70e; }
.route-card.unavailable { opacity: .65; cursor: default; }
.route-heading, .route-footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--sea); font-size: 12px; }
.route-heading > span:last-child { padding: 5px 8px; border-radius: 6px; background: #a1c8b50b; }
.route-seal { width: 40px; height: 40px; display: grid; place-items: center; border: 1px solid #a1c8b52a; border-radius: 50%; }
.route-card h3 { margin: 20px 0 10px; color: #eee4d1; font: 600 21px/1.4 Georgia, 'Noto Serif SC', serif; }
.route-card p { margin: 0 0 20px; font-size: 13px; color: #b3c3b8; line-height: 1.8; flex: 1; }
.route-produce { color: #d7c9a7; font-size: 12px; margin-bottom: 20px; }
.route-footer { border-top: 1px solid #bdd3c61c; padding-top: 16px; min-height: 34px; }
.sailing-preparation { display: grid; grid-template-columns: 1.1fr 1fr; gap: 22px; align-items: start; }
.crew-list { display: grid; gap: 10px; max-height: 480px; overflow: auto; margin-top: 20px; padding-right: 3px; }
.crew-option, .supply-option { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 14px; text-align: left; border: 1px solid #bfd5c71c; border-radius: 11px; background: #0b181230; color: inherit; cursor: pointer; }
.crew-copy { flex: 1; min-width: 0; }
.crew-option:disabled { opacity: .45; cursor: default; }
.crew-option strong, .supply-option strong, .upgrade-row strong { font-size: 14px; }
.crew-option small, .collection-grid small { display: block; margin-top: 5px; }
.sailing-view small, .crew-option > span { font-size: 12px; color: #9db3a4; }
.supply-list { display: grid; gap: 10px; }
.supply-option p, .upgrade-row p { font-size: 12px; color: #a9bfb0; line-height: 1.75; margin: 6px 0; }
.supply-option > svg { flex-shrink: 0; color: var(--sea); }
.departure-panel { border-color: #d5bb7345; background: linear-gradient(150deg, #28332870, #15251dd9); box-shadow: 0 10px 28px #0002; }
.departure-summary { display: grid; gap: 9px; margin: 24px 0 18px; padding-top: 20px; border-top: 1px solid #d5bb7326; font-size: 14px; }
.departure-caption { color: #a6b6a5; font-size: 12px; }
.departure-summary strong { color: #e6cb88; font-size: 19px; font-weight: 600; }
.departure-button { width: 100%; min-height: 48px; justify-content: center; gap: 8px; }
.departure-button:not(:disabled) { color: #292514; background: linear-gradient(130deg, #e7cd8c, #c9ad69); box-shadow: 0 5px 20px #dbb96418; }
.voyage-status { border-color: #91cec755; background: #1c39304d; }
.voyage-status p { font-size: 13px; color: #b4c3c0; margin: 18px 0; }
.sailing-loot { display: flex; flex-wrap: wrap; gap: 10px; }
.sailing-loot span { display: flex; align-items: center; gap: 6px; padding: 10px 12px; border: 1px solid #d5bb7320; border-radius: 8px; color: #ddc594; background: #ddc5940a; font-size: 13px; }
.journal-list { list-style: none; padding: 0 0 0 18px; margin: 26px 0 0; border-left: 1px solid #82c9cb40; display: grid; gap: 24px; }
.journal-list strong { font-size: 14px; }
.journal-list p { color: #b4c3c0; font-size: 13px; line-height: 1.8; margin: 8px 0; }
.sailing-bottom-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; padding-top: 4px; }
.sailing-bottom-grid > .sailing-panel { background: #ffffff02; }
.upgrade-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 18px 0; border-top: 1px solid #ffffff10; }
.collection-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.collection-grid > div { padding: 16px; border-radius: 10px; background: #ffffff04; }
.collection-grid strong { font-size: 14px; }
.discovery-list { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; font-size: 12px; color: #9faeaa; }
.discovery-list .discovered { color: var(--sea); }
.route-card:focus-visible, .crew-option:focus-visible, .supply-option:focus-visible { outline: 2px solid #c9deb4; outline-offset: 3px; }
@media (max-width: 1100px) and (min-width: 761px) { .sailing-preparation, .sailing-bottom-grid { grid-template-columns: 1fr; } .harbor-banner { grid-template-columns: 1fr; } .boat-scene { display: none; } }
@media (max-width: 760px) {
  .sailing-view { gap: 22px; }
  .sailing-route-grid, .sailing-preparation, .sailing-bottom-grid { grid-template-columns: 1fr; }
  .harbor-banner { grid-template-columns: 1fr; padding: 26px 22px; }
  .harbor-copy h2 { font-size: 26px; }
  .boat-scene { display: none; }
  .harbor-destination { gap: 8px; }
  .harbor-facts { gap: 12px; }
  .sailing-panel { padding: 20px; }
  .route-card { padding: 20px; }
  .section-title h2 { font-size: 17px; }
  .section-title small { max-width: 45%; }
  .sailing-preparation, .sailing-bottom-grid { gap: 20px; }
  .trial-note { padding: 16px; align-items: flex-start; }
}
</style>

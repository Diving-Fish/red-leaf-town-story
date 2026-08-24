export interface PlayerSummary {
  player_id: string
  display_name: string
  level: number
  experience: number
  current_level_xp: number
  next_level_xp: number | null
  coins: number
  maple_flame: number
  guide_leaves: number
  companion_marks: number
  stamina: number
  stamina_cap: number
  stamina_restore_seconds: number
  stamina_updated_at: number
  unlocks: string[]
}

export interface CropDefinition {
  id: string
  name: string
  icon: string
  seed_item_id: string
  produce_item_id: string
  growth_seconds: number
  time_difficulty: number
  stamina_cost: number
  min_level: number
  accent: string
  quality: QualityCurveDefinition
}

export interface QualityCurveDefinition {
  thresholds: number[]
  width: number
  miracle_probability_cap: number
  miracle_eligible: boolean
}

export interface QualityGradeDefinition {
  level: number
  name: string
  sale_multiplier: number
}

export interface CropAdminDefinition extends CropDefinition {
  yield_min: number
  yield_max: number
  plant_xp: number
  harvest_xp: number
  seed_price: number | null
  shop_id: string | null
  produce_sell_price: number
  chart_enabled: boolean
}

export interface CropAdminPayload {
  schema_version: number
  quality_grades: QualityGradeDefinition[]
  crops: CropAdminDefinition[]
}

export interface TaskQualitySnapshot extends QualityCurveDefinition {
  ability: number
  probabilities: number[]
  miracle_width_multiplier: number
  miracle_cap_ignored: boolean
}

export interface PlotState {
  slot: number
  crop_id: string
  planted_at: number
  ready_at: number
  assigned_partner_ids: string[]
  task_snapshot: ProductionTaskSnapshot | null
  task_results: ProductionResultSnapshot[]
  empty: boolean
  ready: boolean
  remaining_seconds: number
  crop: CropDefinition | null
  assigned_partners: OwnedPartner[]
  assignment_locked: boolean
  assignment_locked_until: number | null
}

export interface ProductionResultSnapshot {
  item_id: string
  quantity: number
  quality: number
  resolved_at: number
  quality_name?: string
  item?: {
    id: string
    name: string
    icon: string
    kind: string
    sell_price: number
    has_quality: boolean
  } | null
}

export interface TaskPartnerSnapshot {
  partner_id: string
  level: number
  effective_level: number
  breakthrough: number
  ability: number
}

export interface ProductionTaskSnapshot {
  rule_version: number
  industry: string
  content_id: string
  production_slot_id: string
  started_at: number
  ready_at: number
  assigned_partner_ids: string[]
  support_partner_ids: string[]
  partner_snapshots: TaskPartnerSnapshot[]
  applied_effects: Array<Record<string, unknown>>
  character_ability: number
  total_ability: number
  time_efficiency: number
  yield_efficiency: number
  base_duration: number
  final_duration: number
  produce_item_id: string
  yield_min: number
  yield_max: number
  harvest_xp: number
  consumed_inputs: TaskInputSnapshot[]
  draw_count: number
  quality_parameters: TaskQualitySnapshot
}

export interface TaskInputSnapshot {
  item_id: string
  quality: number
  quantity: number
}

export interface IndustryRules {
  character_base_ability: number
  base_character_ability: number
  global_ability_bonus: number
  partner_capacity: number
  partner_level_cap: number
  collaborator_slots: number
  base_partner_capacity: number
}

export interface GatheringTaskDefinition {
  id: string
  site_id: string
  name: string
  duration_seconds: number
  minimum_duration_seconds: number
  time_difficulty: number
  outputs: GatheringOutputDefinition[]
  draws: GatheringDrawDefinition
  stamina_cost: number
  collect_xp: number
  min_level: number
  quality: QualityCurveDefinition
  item: {
    id: string
    name: string
    icon: string
    kind: string
    sell_price: number
    has_quality: boolean
  }
}

export interface GatheringDrawDefinition {
  base_draws: number
  ability_bonus: number
  difficulty: number
}

export interface GatheringOutputDefinition {
  item_id: string
  weight: number
  quantity_min: number
  quantity_max: number
  item: {
    id: string
    name: string
    icon: string
    kind: string
    sell_price: number
    has_quality: boolean
  }
}

export interface GatheringSiteState {
  site_id: string
  assigned_partner_ids: string[]
  task_snapshot: ProductionTaskSnapshot | null
  task_results: ProductionResultSnapshot[]
  empty: boolean
  ready: boolean
  remaining_seconds: number
  definition: {
    id: string
    name: string
    description: string
    accent: string
    min_level: number
  } | null
  task: GatheringTaskDefinition | null
  available_tasks: GatheringTaskDefinition[]
  assigned_partners: OwnedPartner[]
  assignment_locked: boolean
  assignment_locked_until: number | null
}

export interface TalentNode {
  id: string
  industry: string
  name: string
  description: string
  cost: number
  min_level: number
  prerequisites: string[]
  partner_capacity_bonus: number
  global_ability_bonus: number
  unlocked: boolean
  can_unlock: boolean
  locked_reason: string | null
}

export interface TalentState {
  earned_points: number
  available_points: number
  unlocked_node_ids: string[]
  nodes: TalentNode[]
}

export interface RewardItem {
  item_id: string
  name: string
  icon: string
  quantity: number
  quality: number
  quality_name: string | null
}

export interface RewardPartner {
  partner_id: string
  name: string
}

export interface Reward {
  coins: number
  experience: number
  talent_points: number
  maple_flame: number
  guide_leaves: number
  items: RewardItem[]
  partners: RewardPartner[]
  empty: boolean
}

export interface PortalTribute {
  id: string
  item_id: string
  name: string
  icon: string
  quantity: number
  min_quality: number | null
  min_quality_name: string | null
  delivered: number
  remaining: number
  deliverable: number
  owned: number
  completed: boolean
  reward: Reward
}

export interface PortalPrerequisite {
  portal_id: string
  name: string
  completed: boolean
}

export interface PortalState {
  portal_id: string
  name: string
  description: string
  accent: string
  min_level: number
  prerequisites: PortalPrerequisite[]
  unlocked: boolean
  locked_reason: string | null
  completed: boolean
  completed_at: number
  tributes: PortalTribute[]
  tribute_count: number
  completed_tribute_count: number
  completion_reward: Reward
}

export interface TributeDeliveryResult {
  portal_id: string
  portal_name: string
  tribute_id: string
  delivered: number
  total_delivered: number
  required: number
  tribute_completed: boolean
  portal_completed: boolean
  rewards: (Reward & { source: 'tribute' | 'portal'; label: string; levels: number[] })[]
  unlocked_portals: { portal_id: string; name: string }[]
}

export interface CommissionItem {
  id: string
  name: string
  icon: string
  kind: string
  sell_price: number
  has_quality: boolean
}

export type CommissionStatus = 'open' | 'forwarded' | 'completed' | 'forward_completed'

export interface CommissionState {
  day: string
  commission_id: string
  npc_id: string
  npc_name: string
  npc_title: string
  line: string
  item_id: string
  quantity: number
  tier: number
  tier_name: string
  lucky: boolean
  reward_maple_flame: number
  status: CommissionStatus
  forwarded_at: number
  completed_at: number
  completed_by_name: string
  item: CommissionItem | null
  owned: number
  settled: boolean
  can_submit: boolean
  can_forward: boolean
  can_withdraw: boolean
  owner_reward: number
  taker_reward: number
}

export interface CommissionTake {
  day: string
  commission_id: string
  owner_name: string
  item_id: string
  quantity: number
  reward_maple_flame: number
  completed_at: number
}

export interface CommissionsState {
  day: string
  unlocked: boolean
  min_level: number
  board_available: boolean
  refresh_at: number
  lucky_weekday: number
  lucky_today: boolean
  reward_maple_flame: number
  lucky_reward_maple_flame: number
  daily_take_limit: number
  remaining_takes: number
  takes: CommissionTake[]
  commission: CommissionState | null
}

export interface CommissionBoardEntry {
  commission_id: string
  day: string
  owner_name: string
  npc_name: string
  npc_title: string
  line: string
  item_id: string
  quantity: number
  tier: number
  lucky: boolean
  reward_maple_flame: number
  owner_reward: number
  taker_reward: number
  forwarded_at: number
  item: CommissionItem | null
  owned: number
  can_take: boolean
}

export interface CommissionBoard {
  day: string
  available: boolean
  refresh_at: number
  remaining_takes: number
  daily_take_limit: number
  entries: CommissionBoardEntry[]
}

export interface RecipeInputState {
  item_id: string
  quantity: number
  item: GatheringTaskDefinition['item']
  owned_quantity: number
  owned_by_quality: Record<number, number>
}

export interface RecipeState {
  id: string
  station_id: string
  name: string
  inputs: RecipeInputState[]
  produce_item_id: string
  produce_quantity: number
  duration_seconds: number
  time_difficulty: number
  stamina_cost: number
  collect_xp: number
  quality: QualityCurveDefinition
  unlock_condition: { hook: string; params: Record<string, number | string | boolean> }
  item: GatheringTaskDefinition['item']
  unlocked: boolean
  unlock_description: string
  ingredients_available: boolean
}

export interface CraftingStationState {
  station_id: string
  assigned_partner_ids: string[]
  task_snapshot: ProductionTaskSnapshot | null
  task_results: ProductionResultSnapshot[]
  empty: boolean
  ready: boolean
  remaining_seconds: number
  definition: {
    id: string
    name: string
    description: string
    accent: string
    min_level: number
  } | null
  recipe: RecipeState | null
  recipes: RecipeState[]
  assigned_partners: OwnedPartner[]
  assignment_locked: boolean
  assignment_locked_until: number | null
}

export interface MiningTaskDefinition {
  id: string
  site_id: string
  name: string
  produce_item_id: string
  duration_seconds: number
  yield_bonus: number
  yield_difficulty: number
  yield_min: number
  yield_max: number
  stamina_cost: number
  collect_xp: number
  min_level: number
  quality: QualityCurveDefinition
  item: GatheringTaskDefinition['item']
}

export interface MiningSiteState {
  site_id: string
  assigned_partner_ids: string[]
  task_snapshot: ProductionTaskSnapshot | null
  task_results: ProductionResultSnapshot[]
  empty: boolean
  ready: boolean
  remaining_seconds: number
  definition: {
    id: string
    name: string
    description: string
    accent: string
    min_level: number
  } | null
  task: MiningTaskDefinition | null
  available_tasks: MiningTaskDefinition[]
  assigned_partners: OwnedPartner[]
  assignment_locked: boolean
  assignment_locked_until: number | null
}

export interface InventoryItem {
  item_id: string
  inventory_key: string
  name: string
  icon: string
  kind: string
  quantity: number
  quality: number | null
  quality_name: string | null
  quality_sale_multiplier: number
  base_sell_price: number
  sell_price: number
}

export interface ShopEntry {
  id: string
  item_id: string
  price: number
  currency: 'coins'
  min_level: number
  locked: boolean
  item: {
    id: string
    name: string
    icon: string
    kind: string
    sell_price: number
  }
  crop: CropDefinition | null
}

export interface GameState {
  server_time: number
  player: PlayerSummary
  plots: PlotState[]
  next_plot_level: number | null
  gathering_sites: GatheringSiteState[]
  next_gathering_site_level: number | null
  crafting_stations: CraftingStationState[]
  next_crafting_station_level: number | null
  mining_sites: MiningSiteState[]
  next_mining_site_level: number | null
  inventory: InventoryItem[]
  task_items: TaskItemState[]
  partners: OwnedPartner[]
  partner_count: number
  partner_growth: PartnerGrowthState
  gacha_pools: GachaPoolState[]
  industry_rules: Record<string, IndustryRules>
  talents: TalentState
  portals: PortalState[]
  commissions: CommissionsState
  crops: CropDefinition[]
  shop: ShopEntry[]
}

export interface AccountState {
  player_id: string
  display_name: string
  bindings: string[]
  state: GameState
}

export interface ActionResult {
  result: Record<string, unknown>
  state: GameState
}

export type IndustryId = 'farming' | 'gathering' | 'mining' | 'aquatic' | 'livestock' | 'crafting' | 'exploration'
export type GrowthCurveId = 'early' | 'linear' | 'late'

export interface PartnerTendency {
  industry: IndustryId
  level_1: number
  level_60: number
}

export interface PartnerArtwork {
  breakthrough: number
  asset_key: string
  width: number
  height: number
  content_type: string
  url?: string | null
}

export interface CropRect {
  x: number
  y: number
  w: number
  h: number
}

export interface AvatarCrop extends CropRect {
  breakthrough: number
}

export interface PartnerDefinition {
  id: string
  name: string
  rarity: 3 | 4 | 5
  description: string
  growth_curve: GrowthCurveId
  tendencies: PartnerTendency[]
  trait_codes: string[]
  artworks: PartnerArtwork[]
  avatar_crops: AvatarCrop[]
  ascensions?: PartnerAscension[]
  complete?: boolean
  ability_preview?: Record<string, Record<string, number>>
}

export interface PartnerAdminOptions {
  industries: Array<{ id: IndustryId; name: string }>
  growth_curves: Array<{ id: GrowthCurveId; name: string }>
  rarities: Array<3 | 4 | 5>
  breakthrough_level_caps: number[]
  cdn: { provider: string; configured: boolean; base_url: string }
  traits: Array<{ code: string; name: string; description: string; implemented: boolean }>
}

export interface PartnerAdminPayload {
  partners: PartnerDefinition[]
  options: PartnerAdminOptions
}

export interface OwnedPartnerTendency extends PartnerTendency {
  name: string
  current_ability: number
  effective_level: number
  effective_ability: number
}

export interface OwnedPartnerTrait {
  code: string
  name: string
  description: string
  implemented: boolean
}

export interface OwnedPartner {
  partner_id: string
  level: number
  experience: number
  breakthrough: number
  stars: number
  acquired_at: number
  missing: boolean
  name: string
  rarity: 3 | 4 | 5 | null
  description?: string
  growth_curve?: GrowthCurveId
  growth_curve_name?: string
  level_cap?: number
  experience_to_next_level?: number | null
  artwork?: PartnerArtwork | null
  avatar_crop?: AvatarCrop | null
  tendencies?: OwnedPartnerTendency[]
  traits?: OwnedPartnerTrait[]
  upgrade_available?: boolean
  breakthrough_available?: boolean
  breakthrough_reason?: string | null
  ascension?: PartnerAscensionState | null
  star_up_available?: boolean
  star_up_cost?: number | null
  assigned_plot_slot: number | null
  assigned_gathering_site_id: string | null
  assigned_crafting_station_id: string | null
  assigned_mining_site_id: string | null
  locked: boolean
  locked_until: number | null
}

export interface PartnerAscensionItem {
  item_id: string
  quantity: number
  min_quality: number
}

export interface PartnerAscension {
  breakthrough: 1 | 2
  coins: number
  items: PartnerAscensionItem[]
}

export interface PartnerAscensionState extends PartnerAscension {
  items: Array<PartnerAscensionItem & { name: string; icon: string; owned: number }>
}

export interface TaskItemState {
  id: string
  name: string
  description: string
  icon: string
  effect: string
  value: number
  timing: 'start' | 'active'
  eligible_industries: string[]
  quantity: number
}

export interface PartnerExperienceBook {
  item_id: string
  experience: number
  owned: number
  item: { id: string; name: string; icon: string; kind: string; sell_price: number; has_quality: boolean }
}

export interface PartnerGrowthState {
  experience_books: PartnerExperienceBook[]
}

export interface GachaCatalogPartner {
  partner_id: string
  name: string
  rarity: 3 | 4 | 5
  artwork: PartnerArtwork | null
  avatar_crop: AvatarCrop | null
}

export interface GachaPoolBackground {
  asset_key: string
  width: number
  height: number
  content_type: string
  url?: string | null
}

export interface GachaPoolState {
  pool_id: string
  title: string
  unlocked: boolean
  min_level: number
  maple_flame_per_leaf: number
  rarity_probabilities: Record<number, number>
  item_probability: number
  four_star_guarantee: number
  five_star_pity: number
  pulls_until_four_star: number
  pulls_until_five_star: number
  max_pulls_per_player: number | null
  total_pulls: number
  remaining_pulls: number | null
  background: GachaPoolBackground | null
  featured_partner_id: string | null
  featured_rate: number
  catalog: GachaCatalogPartner[]
  task_items: Omit<TaskItemState, 'quantity'>[]
}

export interface GachaDrop {
  kind: 'partner' | 'task_item'
  content_id: string
  rarity: number | null
  duplicate: boolean
  quantity: number
  companion_marks: number
}

export interface GachaResult {
  request_id: string
  pool_id: string
  count: 1 | 10
  created_at: number
  results: GachaDrop[]
  replayed: boolean
}

export interface AdminPlayerSummary {
  player_id: string
  display_name: string
  level: number
  experience: number
  coins: number
  maple_flame: number
  owned_partner_ids: string[]
  updated_at: number
}

export interface AdminPlayerResourceGrantResult {
  coins: number
  experience: number
  maple_flame: number
  unlocked_levels: number[]
  player: AdminPlayerSummary
}

export interface AdminPartnerGrantResult {
  owned_partner: {
    partner_id: string
    level: number
    breakthrough: number
    acquired_at: number
  }
  player: AdminPlayerSummary
}

export type StoryAssetKind = 'background' | 'portrait'
export type StoryMode = 'inline' | 'stage'
export type StoryPortraitSlot = 'left' | 'right'

export interface StoryAssetLayout {
  scale: number
  offset_x: number
  offset_y: number
}

export interface StoryAsset {
  id: string
  kind?: StoryAssetKind
  name: string
  asset_key: string
  width: number
  height: number
  layouts?: Record<StoryMode, StoryAssetLayout>
  inline_layout?: StoryAssetLayout
  stage_layout?: StoryAssetLayout
  content_type?: string
  created_at?: number
  url?: string
}

export interface StoryBackgroundStep {
  type: 'background'
  asset_id: string
  asset: StoryAsset | null
}

export interface StoryPortraitStep {
  type: 'portrait'
  slot: StoryPortraitSlot
  visible: boolean
  asset_id: string
  partner_id: string
  breakthrough: number
  asset: StoryAsset | null
}

export interface StoryDialogueStep {
  type: 'dialogue'
  speaker: string
  text: string
  focus: StoryPortraitSlot | 'none'
}

export type StoryStep = StoryBackgroundStep | StoryPortraitStep | StoryDialogueStep

export interface StoryScript {
  id: string
  title: string
  mode: StoryMode
  priority: number
  repeatable: boolean
  trigger_description: string
  rewards: Reward
  steps: StoryStep[]
}

export interface StoryCueResult {
  cue: string
  stories: StoryScript[]
}

export interface StoryAdminPayload {
  assets: StoryAsset[]
  scripts: StoryScript[]
  options: {
    kinds: { id: StoryAssetKind; name: string }[]
    trigger_hooks: string[]
    script_directory: string
    cdn: { provider: string; configured: boolean; base_url: string }
  }
}

export interface PlayerSummary {
  player_id: string
  display_name: string
  level: number
  experience: number
  current_level_xp: number
  next_level_xp: number | null
  coins: number
  stamina: number
  stamina_cap: number
  stamina_restore_seconds: number
  stamina_updated_at: number
  unlocks: string[]
}

export interface CropDefinition {
  id: string
  name: string
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

export interface TaskQualitySnapshot extends QualityCurveDefinition {
  ability: number
  probabilities: number[]
}

export interface PlotState {
  slot: number
  crop_id: string
  planted_at: number
  ready_at: number
  assigned_partner_ids: string[]
  task_snapshot: ProductionTaskSnapshot | null
  task_result: ProductionResultSnapshot | null
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
  base_duration: number
  final_duration: number
  produce_item_id: string
  yield_min: number
  yield_max: number
  harvest_xp: number
  quality_parameters: TaskQualitySnapshot
}

export interface IndustryRules {
  character_base_ability: number
  partner_capacity: number
  partner_level_cap: number
  collaborator_slots: number
  base_partner_capacity: number
}

export interface GatheringTaskDefinition {
  id: string
  site_id: string
  name: string
  produce_item_id: string
  duration_seconds: number
  time_difficulty: number
  yield_min: number
  yield_max: number
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

export interface GatheringSiteState {
  site_id: string
  assigned_partner_ids: string[]
  task_snapshot: ProductionTaskSnapshot | null
  task_result: ProductionResultSnapshot | null
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
  inventory: InventoryItem[]
  partners: OwnedPartner[]
  partner_count: number
  industry_rules: Record<string, IndustryRules>
  talents: TalentState
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
  breakthrough: number
  acquired_at: number
  missing: boolean
  name: string
  rarity: 3 | 4 | 5 | null
  description?: string
  growth_curve?: GrowthCurveId
  growth_curve_name?: string
  level_cap?: number
  artwork?: PartnerArtwork | null
  avatar_crop?: AvatarCrop | null
  tendencies?: OwnedPartnerTendency[]
  traits?: OwnedPartnerTrait[]
  upgrade_available?: boolean
  breakthrough_available?: boolean
  assigned_plot_slot: number | null
  assigned_gathering_site_id: string | null
  locked: boolean
  locked_until: number | null
}

export interface AdminPlayerSummary {
  player_id: string
  display_name: string
  level: number
  owned_partner_ids: string[]
  updated_at: number
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

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
  stamina_cost: number
  min_level: number
  accent: string
}

export interface PlotState {
  slot: number
  crop_id: string
  planted_at: number
  ready_at: number
  empty: boolean
  ready: boolean
  remaining_seconds: number
  crop: CropDefinition | null
}

export interface InventoryItem {
  item_id: string
  name: string
  icon: string
  kind: string
  quantity: number
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
  inventory: InventoryItem[]
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

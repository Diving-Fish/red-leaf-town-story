"""成长内容外放、通用灰度隔离、扣费事务及多物种养殖回归。"""
import pytest

from red_leaf_town.application import GameError
from red_leaf_town.domain.economy import add_item
from red_leaf_town.domain.progression import settle_stamina
from test_livestock import ranch, set_level, give, facility_of, CYCLE


def enable(ranch, monkeypatch, level=20):
    service, repo, clock, player = ranch
    monkeypatch.setenv('RED_LEAF_TOWN_BETA_PLAYERS', 'someone-else')
    set_level(repo, player.player_id, level)
    service.snapshot_by_sub('stock-sub')
    return service, repo, clock, player


def materials(ranch, facility_id):
    service, repo, _, player = ranch
    tier = service.content.livestock_facility_map[facility_id].tier(2)
    for m in tier.build_materials:
        give(repo, player.player_id, m.item_id, m.quantity, 1)


def test_future_beta_content_still_requires_allowlist(ranch, monkeypatch):
    service, repo, _, player = ranch
    # 本批已外放；用显式测试标记保留下一批内容的灰度保护回归。
    for level in service.content.levels:
        if level.level >= 17: level.beta = True
    for collection, ids in [
        (service.content.crops, {'corn'}),
        (service.content.items, {'corn_seed'}),
        (service.content.shop, {'corn_seed'}),
        (service.content.gathering_sites, {'reed_wetland'}),
        (service.content.gathering_tasks, {'collect_reed_wetland'}),
        (service.content.recipes, {'make_flax_thread'}),
        (service.content.livestock_species, {'duck'}),
    ]:
        for entry in collection:
            if entry.id in ids: entry.beta = True
    service.content.livestock_facility_map['coop_1'].tier(2).beta = True
    monkeypatch.setenv('RED_LEAF_TOWN_BETA_PLAYERS', 'not-this-player')
    set_level(repo, player.player_id, 20)
    state = service.snapshot_by_sub('stock-sub')
    assert state['player']['level'] == 16
    assert state['player']['next_level_xp'] is None
    assert not any(c['id'] == 'corn' for c in state['crops'])
    assert not any(e['id'] == 'corn_seed' for e in state['shop'])
    assert not any(s['site_id'] == 'reed_wetland' for s in state['gathering_sites'])
    assert not any(r['id'] == 'make_flax_thread' for station in state['crafting_stations'] for r in station['recipes'])
    assert facility_of(state, 'coop_1')['upgrade'] is None
    assert [s['id'] for s in facility_of(state, 'coop_1')['species']] == ['chicken']
    actions = [
        lambda: service.buy('stock-sub', 'corn_seed', 1),
        lambda: service.plant('stock-sub', 0, 'corn'),
        lambda: service.start_crafting('stock-sub', 'town_workbench', 'make_flax_thread'),
        lambda: service.start_gathering('stock-sub', 'reed_wetland', 'collect_reed_wetland'),
        lambda: service.upgrade_livestock_facility('stock-sub', 'coop_1', 2),
        lambda: service.buy_animal('stock-sub', 'coop_1', 'duck'),
        lambda: service.incubate_egg('stock-sub', 'coop_1', 1, species_id='duck'),
    ]
    for action in actions:
        before = repo.get(player.player_id)
        with pytest.raises(GameError):
            action()
        after = repo.get(player.player_id)
        assert after.coins == before.coins and after.inventory == before.inventory


@pytest.mark.parametrize('level,cap', [(17,52),(18,54),(19,56),(20,58)])
def test_public_levels_and_stamina_caps(ranch, monkeypatch, level, cap):
    service, repo, clock, player = enable(ranch, monkeypatch, level)
    state = service.snapshot_by_sub('stock-sub')
    assert state['player']['level'] == level
    saved = repo.get(player.player_id)
    saved.stamina = 0
    saved.stamina_updated_at = clock.now
    settle_stamina(saved, service.content, clock.now + 100 * service.content.stamina.restore_seconds)
    assert saved.stamina == cap
    assert saved.experience == service.content.level_definition(level).total_xp


def test_upgrade_atomic_idempotent_and_keeps_animals(ranch, monkeypatch):
    service, repo, clock, player = enable(ranch, monkeypatch)
    service.buy_animal('stock-sub', 'coop_1', 'chicken')
    original_ids = [a.animal_id for a in repo.get(player.player_id).animals]
    materials(ranch, 'coop_1')
    # Keep a higher-quality reserve to prove low-quality-first consumption.
    give(repo, player.player_id, 'rope', 3, 3)
    before = repo.get(player.player_id)
    result = service.upgrade_livestock_facility('stock-sub', 'coop_1', 2)
    after = repo.get(player.player_id)
    assert after.coins == before.coins - 6000
    assert after.inventory['rope'] == {3:3}
    assert [a.animal_id for a in after.animals] == original_ids
    coop = facility_of(result['state'], 'coop_1')
    assert (coop['capacity'], coop['gene_cap'], coop['overflow_cycles']) == (8,85,4)
    assert service.upgrade_livestock_facility('stock-sub', 'coop_1', 2)['result']['duplicate']
    assert repo.get(player.player_id).coins == after.coins
    materials(ranch, 'barn_1')
    service.upgrade_livestock_facility('stock-sub', 'barn_1', 2)
    assert service._feed_slot_capacity(repo.get(player.player_id)) == 1700


def test_upgrade_checks_level_and_missing_material_without_charging(ranch, monkeypatch):
    service, repo, _, player = enable(ranch, monkeypatch, 12)
    materials(ranch, 'coop_1')
    before = repo.get(player.player_id)
    with pytest.raises(GameError, match='13'):
        service.upgrade_livestock_facility('stock-sub', 'coop_1', 2)
    assert repo.get(player.player_id).coins == before.coins
    set_level(repo, player.player_id, 13)
    repo.update(player.player_id, lambda p: p.inventory.pop('reed_mat'))
    before = repo.get(player.player_id)
    with pytest.raises(GameError, match='材料不足'):
        service.upgrade_livestock_facility('stock-sub', 'coop_1', 2)
    after = repo.get(player.player_id)
    assert before.inventory == after.inventory and before.coins == after.coins


def test_duck_incubation_sheep_breeding_and_shared_capacity(ranch, monkeypatch):
    service, repo, clock, player = enable(ranch, monkeypatch)
    for facility, species in [('coop_1','duck'),('barn_1','sheep')]:
        with pytest.raises(GameError):
            service.buy_animal('stock-sub', facility, species)
        materials(ranch, facility)
        service.upgrade_livestock_facility('stock-sub', facility, 2)
    give(repo, player.player_id, 'duck_egg', 1, 2)
    hatched = service.incubate_egg('stock-sub', 'coop_1', 2, species_id='duck')['result']['animal']
    assert hatched['species_id'] == 'duck'
    assert hatched['stage'] == 'incubating'
    assert 'duck' not in repo.get(player.player_id).achievement_stats.bred_species_ids
    sheep = [service.buy_animal('stock-sub', 'barn_1', 'sheep')['result']['animal']['animal_id'] for _ in range(2)]
    cow = service.buy_animal('stock-sub', 'barn_1', 'cow')['result']['animal']['animal_id']
    def mature(p):
        for a in p.animals:
            if a.animal_id in sheep + [cow]: a.stage = 'adult'
    repo.update(player.player_id, mature)
    before = repo.get(player.player_id)
    with pytest.raises(GameError, match='同物种'):
        service.breed_animals('stock-sub', 'barn_1', [sheep[0],cow])
    assert repo.get(player.player_id).feed_slot.units == before.feed_slot.units
    born = service.breed_animals('stock-sub', 'barn_1', sheep)['result']['animal']
    assert born['species_id'] == 'sheep'
    assert repo.get(player.player_id).achievement_stats.bred_species_ids == ['sheep']
    for _ in range(7): service.buy_animal('stock-sub', 'coop_1', 'chicken')
    with pytest.raises(GameError, match='住满'):
        service.buy_animal('stock-sub', 'coop_1', 'duck')
    clock.advance(3*CYCLE)
    service.snapshot_by_sub('stock-sub')
    assert next(a for a in repo.get(player.player_id).animals if a.animal_id == hatched['animal_id']).stage == 'juvenile'
    assert repo.get(player.player_id).achievement_stats.bred_species_ids == ['duck', 'sheep']
    assert any(a.achievement_id == 'duck_sheep_bred' for a in repo.get(player.player_id).achievements)


def test_nutrition_level_gate_and_cloth_batch_cost(ranch, monkeypatch):
    service, repo, clock, player = enable(ranch, monkeypatch, 16)
    for id,q in [('refined_fodder',2),('grain_fodder',2),('flax',3)]: give(repo, player.player_id,id,q,1)
    with pytest.raises(GameError, match='17'):
        service.start_crafting('stock-sub','town_workbench','make_nutrition_fodder')
    before = repo.get(player.player_id)
    service.start_crafting('stock-sub','town_workbench','make_flax_thread')
    assert repo.get(player.player_id).stamina == before.stamina - 2
    clock.advance(120)
    service.collect_crafting('stock-sub','town_workbench')
    assert sum(repo.get(player.player_id).inventory['flax_thread'].values()) == 3
    set_level(repo, player.player_id,17)
    service.start_crafting('stock-sub','town_workbench','make_nutrition_fodder')
    clock.advance(360)
    service.collect_crafting('stock-sub','town_workbench')
    assert sum(repo.get(player.player_id).inventory['nutrition_fodder'].values()) == 3


def test_released_growth_is_visible_without_allowlist(ranch, monkeypatch):
    service, repo, _, player = enable(ranch, monkeypatch)
    state = service.snapshot_by_sub('stock-sub')
    assert state['player']['level'] == 20
    assert 'corn' in {entry['id'] for entry in state['crops']}
    assert 'corn_seed' in {entry['id'] for entry in state['shop']}
    assert 'reed_wetland' in {entry['site_id'] for entry in state['gathering_sites']}
    assert 'make_flax_thread' in {r['id'] for station in state['crafting_stations'] for r in station['recipes']}
    assert facility_of(state, 'coop_1')['upgrade']['level'] == 2
    assert 'duck' in {entry['id'] for entry in facility_of(state, 'coop_1')['species']}
    service.buy('stock-sub', 'corn_seed', 1)
    service.plant('stock-sub', 0, 'corn')


def test_duck_and_sheep_collection_achievements_require_actual_collection(ranch, monkeypatch):
    service, repo, clock, player = enable(ranch, monkeypatch)
    for facility, species in [('coop_1', 'duck'), ('barn_1', 'sheep')]:
        materials(ranch, facility)
        service.upgrade_livestock_facility('stock-sub', facility, 2)
        service.buy_animal('stock-sub', facility, species)
    def produce(p):
        for animal in p.animals:
            animal.stage = 'adult'
            animal.pending_output = {2: 1}
            animal.pending_special = 1
    repo.update(player.player_id, produce)
    assert not repo.get(player.player_id).achievement_stats.livestock_item_ids
    service.collect_livestock('stock-sub', 'coop_1')
    collected = service.collect_livestock('stock-sub', 'barn_1')
    done = {a['achievement_id'] for a in collected['state']['achievements']['entries'] if a['completed']}
    assert {'duck_sheep_products', 'duck_sheep_specials', 'expanded_ranch'} <= done
    with pytest.raises(GameError):
        service.collect_livestock('stock-sub', 'barn_1')
    assert repo.get(player.player_id).achievement_stats.livestock_item_ids == ['cloud_fleece', 'duck_egg', 'jade_duck_egg', 'wool']

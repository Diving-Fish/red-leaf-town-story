import random

import pytest

from red_leaf_town.application import GameError, GameService
from red_leaf_town.content import load_content
from red_leaf_town.domain import PlayerState
from red_leaf_town.domain.economy import add_item
from red_leaf_town.infrastructure import InMemoryPlayerRepository
from red_leaf_town.partner_content import PartnerCatalog, PartnerDefinition
from red_leaf_town.sailing_content import SailingContent, load_sailing_content


@pytest.fixture
def sailing_game(monkeypatch):
    content = load_content()
    repo = InMemoryPlayerRepository(content)
    catalog = PartnerCatalog(partners=[PartnerDefinition.model_validate({
        'id': name, 'name': name, 'rarity': 3,
        'tendencies': [{'industry': industry, 'level_1': 40, 'level_60': 80}],
        'avatar_crops': [{'breakthrough': stage, 'x': 0, 'y': 0, 'w': 1, 'h': 1} for stage in range(3)],
    }) for name, industry in [('sailor', 'aquatic'), ('scout', 'exploration'), ('farmer', 'farming')]])
    clock = [1_700_000_000]
    game = GameService(content, repo, clock=lambda: clock[0], rng=random.Random(7), partner_catalog_loader=lambda: catalog)
    player = game.ensure_player('sailing-sub', '航海测试员')
    monkeypatch.setenv('RED_LEAF_TOWN_BETA_PLAYERS', player.player_id)
    for entry in catalog.partners:
        game.admin_grant_partner(player.player_id, entry.id)

    def prepare(p):
        p.experience = content.level_definition(16).total_xp
        p.coins = 100_000
        p.stamina = 100
        for item in ('pickled_carrot', 'refined_fodder', 'maple_plank', 'red_copper_ore'):
            add_item(p, item, 50, 1)
    repo.update(player.player_id, prepare)
    return game, repo, player, clock


def start(game, request_id='voyage-1', route='reed_bay', party=None, supply='none'):
    return game.start_sailing('sailing-sub', route, ['sailor'] if party is None else party, supply, request_id)


def finish(game, clock, started):
    run = started['state']['sailing']['active_run']
    clock[0] = run['ready_at']
    return game.collect_sailing('sailing-sub', run['run_id'])


def test_sailing_content_references_and_duplicate_validation():
    content = load_sailing_content()
    content.validate_items(load_content().item_map)
    with pytest.raises(ValueError, match='unknown sailing items'):
        content.validate_items({})
    payload = content.model_dump()
    payload['routes'].append(payload['routes'][0])
    with pytest.raises(ValueError, match='duplicate sailing'):
        SailingContent.model_validate(payload)


def test_schema_30_migrates_without_changing_existing_assets(sailing_game):
    game, repo, player, _ = sailing_game
    old = repo.get(player.player_id).model_dump()
    old.pop('sailing')
    old['schema_version'] = 30
    migrated = PlayerState.model_validate(old)
    assert migrated.schema_version == 31
    assert migrated.sailing.active_run is None
    assert migrated.sailing.completed_voyages == 0
    assert migrated.inventory == old['inventory']


def test_beta_and_level_gates_apply_to_all_mutations(sailing_game, monkeypatch):
    game, repo, player, _ = sailing_game
    monkeypatch.setenv('RED_LEAF_TOWN_BETA_PLAYERS', 'someone-else')
    assert game.snapshot_by_sub('sailing-sub')['sailing'] is None
    for action in (lambda: start(game), lambda: game.collect_sailing('sailing-sub', 'missing'),
                   lambda: game.upgrade_sailing('sailing-sub', 'cargo', 0)):
        with pytest.raises(GameError, match='内测'):
            action()
    monkeypatch.setenv('RED_LEAF_TOWN_BETA_PLAYERS', player.player_id)
    repo.update(player.player_id, lambda p: setattr(p, 'experience', 0))
    assert not game.snapshot_by_sub('sailing-sub')['sailing']['unlocked']
    with pytest.raises(GameError, match='16'):
        start(game)


@pytest.mark.parametrize('party', [[], ['sailor', 'sailor'], ['sailor'] * 4, ['missing'], [None], 'sailor', [{}]])
def test_invalid_parties_never_charge(sailing_game, party):
    game, repo, player, _ = sailing_game
    before = repo.get(player.player_id)
    with pytest.raises(GameError):
        start(game, party=party)
    after = repo.get(player.player_id)
    assert after.coins == before.coins
    assert after.inventory == before.inventory
    assert after.sailing.active_run is None


def test_trial_freezes_results_and_collects_once_after_arrival(sailing_game):
    game, repo, player, clock = sailing_game
    before = repo.get(player.player_id)
    started = start(game)
    run = started['state']['sailing']['active_run']
    frozen = repo.get(player.player_id).sailing.active_run.model_dump()
    assert run['ready_at'] - run['started_at'] == 60
    assert not run['drops'] and not run['logs']
    assert repo.get(player.player_id).coins == before.coins - run['coins']
    assert repo.get(player.player_id).stamina == before.stamina - run['stamina']
    assert repo.get(player.player_id).inventory == before.inventory
    assert start(game)['result']['duplicate']
    assert repo.get(player.player_id).sailing.active_run.model_dump() == frozen
    assert game.snapshot_by_sub('sailing-sub')['sailing']['active_run'] == run
    with pytest.raises(GameError, match='还没有回港'):
        game.collect_sailing('sailing-sub', run['run_id'])
    clock[0] = run['ready_at'] + 86400
    ready = game.snapshot_by_sub('sailing-sub')
    assert not next(p for p in ready['partners'] if p['partner_id'] == 'sailor')['locked']
    assert ready['sailing']['active_run']['drops']
    claimed = game.collect_sailing('sailing-sub', run['run_id'])
    assert claimed['state']['sailing']['completed_voyages'] == 1
    assert claimed['state']['sailing']['active_run'] is None
    assert repo.get(player.player_id).sailing.last_run.model_dump() == frozen
    after = repo.get(player.player_id)
    for drop in frozen['drops']:
        assert after.inventory[drop['item_id']][0] == drop['quantity']
    assert after.experience == before.experience + frozen['experience']
    assert next(p for p in after.owned_partners if p.partner_id == 'sailor').experience > 0
    assert game.collect_sailing('sailing-sub', run['run_id'])['result']['duplicate']
    assert repo.get(player.player_id).inventory == after.inventory
    assert repo.get(player.player_id).experience == after.experience
    assert start(game)['result']['duplicate']
    assert repo.get(player.player_id).sailing.active_run is None


def test_normal_routes_unlock_by_completed_voyages(sailing_game):
    game, _, _, clock = sailing_game
    with pytest.raises(GameError, match='完成 1 次'):
        start(game, route='white_sail')
    first = finish(game, clock, start(game))
    assert first['state']['sailing']['routes'][1]['unlocked']
    second = start(game, 'voyage-2', 'white_sail')
    run = second['state']['sailing']['active_run']
    assert not run['trial'] and run['ready_at'] - run['started_at'] == 21600
    with pytest.raises(GameError, match='船还在航行'):
        start(game, 'voyage-3')
    finish(game, clock, second)
    finish(game, clock, start(game, 'voyage-3'))
    third = start(game, 'voyage-4', 'mist_isles', ['scout'])
    assert third['state']['sailing']['active_run']['ability'] > 0
    finish(game, clock, third)


def test_supply_cost_uses_lowest_quality_and_failure_rolls_back(sailing_game):
    game, repo, player, _ = sailing_game
    def prepare(p):
        p.inventory['pickled_carrot'] = {1: 1, 3: 4}
    repo.update(player.player_id, prepare)
    start(game, supply='ration')
    state = repo.get(player.player_id)
    assert state.inventory['pickled_carrot'] == {3: 3}
    assert state.sailing.active_run.consumed_inputs == [
        {'item_id': 'pickled_carrot', 'quality': 1, 'quantity': 1},
        {'item_id': 'pickled_carrot', 'quality': 3, 'quantity': 1},
    ]


def test_insufficient_resources_do_not_charge_or_move_partner(sailing_game):
    game, repo, player, _ = sailing_game
    def prepare(p):
        p.inventory['pickled_carrot'] = {1: 1}
        p.fishing.companion_partner_id = 'sailor'
    repo.update(player.player_id, prepare)
    before = repo.get(player.player_id)
    with pytest.raises(GameError, match='补给数量不足'):
        start(game, supply='ration')
    after = repo.get(player.player_id)
    assert after.inventory == before.inventory and after.coins == before.coins
    assert after.stamina == before.stamina
    assert after.fishing.companion_partner_id == 'sailor'
    repo.update(player.player_id, lambda p: setattr(p, 'stamina', 0))
    with pytest.raises(GameError, match='体力不足'):
        start(game)
    assert repo.get(player.player_id).coins == before.coins


def test_departure_clears_fishing_and_blocks_farming_fishing_and_exploration(sailing_game):
    game, repo, player, clock = sailing_game
    game.assign_fishing_companion('sailing-sub', 'sailor')
    started = start(game, party=['sailor', 'scout', 'farmer'])
    assert repo.get(player.player_id).fishing.companion_partner_id == ''
    with pytest.raises(GameError, match='伙伴正在'):
        game.assign_fishing_companion('sailing-sub', 'sailor')
    with pytest.raises(GameError, match='伙伴正在'):
        game.assign_partner('sailing-sub', 0, 'farmer')
    with pytest.raises(GameError, match='伙伴正在出海'):
        game.start_exploration('sailing-sub', 'red_maple_hinterland', ['scout'], 'scout')
    clock[0] = started['state']['sailing']['active_run']['ready_at']
    game.assign_fishing_companion('sailing-sub', 'sailor')
    game.start_exploration('sailing-sub', 'red_maple_hinterland', ['scout'], 'scout')


def test_active_explorer_cannot_sail(sailing_game):
    game, _, _, _ = sailing_game
    game.start_exploration('sailing-sub', 'red_maple_hinterland', ['scout'], 'scout')
    with pytest.raises(GameError, match='伙伴正在探索'):
        start(game, party=['scout'])


def test_upgrades_are_atomic_bounded_and_frozen_for_voyage(sailing_game):
    game, repo, player, clock = sailing_game
    before = repo.get(player.player_id)
    upgraded = game.upgrade_sailing('sailing-sub', 'cargo', 0)
    assert upgraded['result']['level'] == 1
    assert repo.get(player.player_id).coins < before.coins
    with pytest.raises(GameError, match='等级已变化'):
        game.upgrade_sailing('sailing-sub', 'cargo', 0)
    started = start(game)
    assert started['state']['sailing']['active_run']['cargo_level'] == 1
    with pytest.raises(GameError, match='回港'):
        game.upgrade_sailing('sailing-sub', 'cargo', 1)
    finish(game, clock, started)
    game.upgrade_sailing('sailing-sub', 'cargo', 1)
    game.upgrade_sailing('sailing-sub', 'cargo', 2)
    with pytest.raises(GameError, match='满级'):
        game.upgrade_sailing('sailing-sub', 'cargo', 3)
    assert repo.get(player.player_id).sailing.last_run.cargo_level == 1


def test_busy_production_partner_cannot_depart_and_assignment_is_preserved(sailing_game):
    game, repo, player, _ = sailing_game
    game.buy('sailing-sub', 'carrot_seed', 1)
    game.assign_partner('sailing-sub', 0, 'farmer')
    game.plant('sailing-sub', 0, 'carrot')
    before = repo.get(player.player_id)
    with pytest.raises(GameError, match='伙伴正在参与任务'):
        start(game, party=['farmer'])
    after = repo.get(player.player_id)
    assert after.coins == before.coins and after.stamina == before.stamina
    assert after.plots == before.plots
    assert after.sailing.active_run is None

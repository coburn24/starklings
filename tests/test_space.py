from typing import List, NamedTuple, Tuple
import pytest

from starkware.starknet.business_logic.state.state import BlockInfo
from starkware.starknet.testing.starknet import Starknet
from starkware.starknet.testing.contract import StarknetContract
from starkware.starknet.public.abi import get_selector_from_name
from sympy import false

from fixtures import *
from deploy import deploy_contract
from utils import assert_revert, str_to_felt, to_uint

ADMIN = get_selector_from_name('admin')
ANYONE = get_selector_from_name('anyone')
SPACE_SIZE = 6
MAX_TURN = 50
MAX_DUST = 2
MAX_FELT = 2**251 + 17 * 2**192 + 1

@pytest.fixture
async def space_factory(starknet: Starknet) -> StarknetContract:
    rand = await deploy_contract(starknet, 'test/fake_rand.cairo')
    space = await deploy_contract(starknet, 'core/space.cairo')
    dust = await deploy_contract(starknet, 'core/dust.cairo', constructor_calldata=[space.contract_address, rand.contract_address])
    await space.initialize(dust.contract_address, SPACE_SIZE, MAX_TURN, MAX_DUST).invoke(caller_address=ADMIN)
    return space, dust

@pytest.mark.asyncio
async def test_get_first_non_empty_cell(space_factory):
    space, dust = space_factory

    execution_info = await space.get_first_non_empty_cell(0, 0).call()
    (px, py), (lo, hi), ship = execution_info.result.cell
    assert px == SPACE_SIZE
    assert py == 0
    assert lo == 0
    assert hi == 0
    assert ship == 0

    execution_info = await space.get_first_non_empty_cell(2, 5).call()
    (px, py), (lo, hi), ship = execution_info.result.cell
    assert px == SPACE_SIZE
    assert py == 0
    assert lo == 0
    assert hi == 0
    assert ship == 0

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 1), Vector2(0, 1))

    execution_info = await space.get_first_non_empty_cell(0, 0).call()
    (px, py), (lo, hi), ship = execution_info.result.cell
    assert px == 0
    assert py == 1
    assert lo == 1
    assert hi == 0
    assert ship == 0

    execution_info = await space.get_first_non_empty_cell(px, py+1).call()
    (px, py), (lo, hi), ship = execution_info.result.cell
    assert px == SPACE_SIZE
    assert py == 0
    assert lo == 0
    assert hi == 0
    assert ship == 0

@pytest.mark.asyncio
async def test_get_first_empty_cell(space_factory):
    space, dust = space_factory

    execution_info = await space.get_first_empty_cell(0, 0).call()
    (px, py) = execution_info.result.position
    assert px == 0
    assert py == 0

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 1), Vector2(0, 1))

    execution_info = await space.get_first_empty_cell(0, 0).call()
    (px, py) = execution_info.result.position
    assert px == 0
    assert py == 0

    execution_info = await space.get_first_empty_cell(0, 1).call()
    (px, py) = execution_info.result.position
    assert px == 0
    assert py == 2

@pytest.mark.asyncio
async def test_turn_count(starknet: Starknet):
    rand = await deploy_contract(starknet, 'test/fake_rand.cairo')
    space = await deploy_contract(starknet, 'core/space.cairo')
    dust = await deploy_contract(starknet, 'core/dust.cairo', constructor_calldata=[space.contract_address, rand.contract_address])

    MAX_TURN = 2
    await space.initialize(dust.contract_address, SPACE_SIZE, MAX_TURN, MAX_DUST).invoke(caller_address=ADMIN)

    execution_info = await space.get_max_turn_count().call()
    assert execution_info.result.count == MAX_TURN
    execution_info = await space.get_current_turn().call()
    assert execution_info.result.num == 0

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    execution_info = await space.get_current_turn().call()
    assert execution_info.result.num == 1

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    execution_info = await space.get_current_turn().call()
    assert execution_info.result.num == 2

    # Next turn --------------------------------------------------
    await assert_revert(space.next_turn().invoke(caller_address=ADMIN))

@pytest.mark.asyncio
async def test_next_turn_no_ship(space_factory):
    space, dust = space_factory

    # Assert grid is empty
    await assert_grid_dust(space, 0, 0, [], [])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 1), Vector2(0, 1))
    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 1), 1)], [])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 2), Vector2(0, 1))
    await assert_dust_position(dust, 2, Vector2(0, 4), Vector2(0, -1))
    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 2), 1), Dust(Vector2(0, 4), 2)], [])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 3), Vector2(0, 1))
    await assert_dust_position(dust, 2, Vector2(0, 3), Vector2(0, -1))
    # MAX_DUST == 2 so no more dust has been spawned

    # A collision occured, assert the dust was burnt
    await assert_revert(dust.ownerOf(to_uint(1)).call(), reverted_with='ERC721: owner query for nonexistent token')

    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 3), 1)], [])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 4), Vector2(0, 1))
    # a new dust was spawned
    await assert_dust_position(dust, 3, Vector2(5, 1), Vector2(0, 1))

    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 4), 1), Dust(Vector2(5, 1), 3)], [])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 5), Vector2(0, 1))
    await assert_dust_position(dust, 3, Vector2(5, 2), Vector2(0, 1))
    # no new dust was spawned, because it would have been at the same position (5,2)

    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 5), 1), Dust(Vector2(5, 2), 3)], [])


@pytest.mark.asyncio
async def test_add_ship(starknet: Starknet, space_factory):
    space, _ = space_factory
    ship1 = await deploy_contract(starknet, 'ships/static_ship.cairo')
    ship2 = await deploy_contract(starknet, 'ships/static_ship.cairo')

    await space.add_ship(3, 3, ship1.contract_address).invoke(caller_address=ADMIN)
    await assert_grid_dust(space, 0, 0, [], [Ship(Vector2(3, 3), ship1.contract_address)])

    await assert_revert(space.add_ship(3, 3, ship2.contract_address).invoke(caller_address=ADMIN))


@pytest.mark.asyncio
async def test_next_turn_with_ship(starknet: Starknet, space_factory):
    space, dust = space_factory
    ship: StarknetContract = await deploy_contract(starknet, 'ships/static_ship.cairo')
    await space.add_ship(0, 3, ship.contract_address).invoke(caller_address=ADMIN)
    ship_assertion = Ship(Vector2(0, 3), ship.contract_address)

    # Assert grid is empty
    await assert_grid_dust(space, 0, 0, [], [ship_assertion])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 1), Vector2(0, 1))
    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 1), 1)], [ship_assertion])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 2), Vector2(0, 1))
    await assert_dust_position(dust, 2, Vector2(0, 4), Vector2(0, -1))
    await assert_grid_dust(space, 0, 0, [Dust(Vector2(0, 2), 1), Dust(Vector2(0, 4), 2)], [ship_assertion])

    # Assert the space owns the dusts
    execution_info = await dust.ownerOf(to_uint(0)).call()
    assert execution_info.result == (space.contract_address,)
    execution_info = await dust.ownerOf(to_uint(1)).call()
    assert execution_info.result == (space.contract_address,)

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 1, Vector2(0, 3), Vector2(0, 1))
    await assert_dust_position(dust, 2, Vector2(0, 3), Vector2(0, -1))
    # MAX_DUST == 2 so no more dust has been spawned

    # Assert the ship earned the dusts at position (0, 3)
    execution_info = await dust.ownerOf(to_uint(0)).call()
    assert execution_info.result == (ship.contract_address,)
    execution_info = await dust.ownerOf(to_uint(1)).call()
    assert execution_info.result == (ship.contract_address,)

    await assert_grid_dust(space, 0, 0, [], [ship_assertion])

    # Next turn --------------------------------------------------
    await space.next_turn().invoke(caller_address=ADMIN)

    await assert_dust_position(dust, 3, Vector2(5, 1), Vector2(0, 1))

    await assert_grid_dust(space, 0, 0, [Dust(Vector2(5, 1), 3)], [ship_assertion])

#
# Helpers to assert the state of the entire grid
#
class Vector2(NamedTuple):
    x: int
    y: int

class Dust(NamedTuple):
    pos: Vector2
    id: int

class Ship(NamedTuple):
    pos: Vector2
    id: int

async def assert_grid_dust(space, x:int, y:int, dusts:List[Dust], ships:List[Ship]):
    if x >= SPACE_SIZE:
        assert len(dusts) == 0
        assert len(ships) == 0
        return
    if y >= SPACE_SIZE:
        assert_grid_dust(space, x+1, 0, dusts, ships)
    
    execution_info = await space.get_first_non_empty_cell(x, y).call()
    (px, py), (lo, hi), ship = execution_info.result.cell
    if px >= SPACE_SIZE: # => nothing found
        assert len(dusts) == 0
        assert len(ships) == 0
        return
    assert_dust_id_at(Vector2(px, py), lo, dusts)
    assert_ship_at(Vector2(px, py), ship, ships)
    assert_grid_dust(space, x, y+1, dusts, ships)

def assert_dust_id_at(position:Vector2, id_lo:int, dusts:List[Dust]):
    for d in dusts:
        if d.pos.x == position.x and d.pos.y == position.y:
            assert id_lo == d.id, 'Expected dust {id}, at position ({x}, {y}). Got {res}'.format(id=id_lo, x=position.x, y=position.y, res=d.id)
            dusts.remove(d)

def assert_ship_at(position:Vector2, ship:int, ships:List[Ship]):
    for s in ships:
        if s.pos.x == position.x and s.pos.y == position.y:
            assert ship == s.id, 'Expected ship {id}, at position ({x}, {y}). Got {res}'.format(id=ship, x=position.x, y=position.y, res=s.id)
            ships.remove(s)

async def assert_dust_position(dust, id:int, position:Vector2, direction:Vector2):
    execution_info = await dust.metadata(to_uint(id-1)).call()
    _, (px, py), (dx, dy) = execution_info.result.metadata
    assert px == position.x
    assert py == position.y
    assert dx == direction.x % MAX_FELT
    assert dy == direction.y % MAX_FELT
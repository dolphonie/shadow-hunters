import pytest

# test_specials.py
# Tests the special abilities of each character
import helpers as H

def test_bob_kill_hunter():
    # Get a game containing Bob
    gc, ef, p = H.get_game_with_character("Bob")

    # Check that Bob hasn't won initially, or with 4 equips
    assert not p.character.win_cond(gc, p)

    # Check that Bob wins if he kills a neutral
    hunter = H.get_a_hunter(gc)
    hunter.setDamage(20, p)
    assert not p.character.win_cond(gc, p)
    assert p in gc.getDeadPlayers()

test_bob_kill_hunter()
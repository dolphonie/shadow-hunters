from collections import defaultdict

import concurrency as R
import constants as C
from agent import Agent


class Player:
    def __init__(self, user_id, socket_id, color, ai):
        self.user_id = user_id
        self.socket_id = socket_id
        self.color = color
        self.gc = None  # game context (abbreviated for convenience)
        self.state = C.PlayerState.Hidden
        self.character = None
        self.equipment = []
        self.damage = 0
        self.location = None
        self.modifiers = defaultdict(lambda: False)
        self.modifiers['attack_dice_type'] = "attack"
        self.special_active = False
        self.ai = ai
        self.agent = Agent()
        self.delexicalizations = dict()

    def setCharacter(self, character):
        self.character = character

    def resetModifiers(self):
        self.modifiers = defaultdict(lambda: False)
        self.modifiers['attack_dice_type'] = "attack"

    def reveal(self):

        # Set state
        self.state = C.PlayerState.Revealed

        # Reveal character to frontend
        self.gc.update_h()

        # Broadcast reveal
        display_data = {'type': 'reveal', 'player': self.dump()}
        self.gc.show_h(display_data)

    def takeTurn(self):

        # Announce player
        self.gc.tell_h("It's {}'s turn!", [self.user_id])

        # Guardian Angel wears off
        # if "guardian_angel" in self.modifiers:
        if self.modifiers['guardian_angel']:
            self.gc.tell_h("The effect of {}\'s {} wore off!",
                           [self.user_id, "Guardian Angel"])
            del self.modifiers["guardian_angel"]

        # If AI player, chance to reveal and use special at turn start
        R.reveal_lock.acquire()
        if self.ai and self.state == C.PlayerState.Hidden:
            if self.agent.choose_reveal(self, self.gc):
                self.state = C.PlayerState.Revealed  # Guard
                self.special_active = True  # Guard
                R.reveal_lock.release()
                self.reveal()
                self.character.special(self.gc, self, turn_pos='now')
                self.gc.update_h()
            else:
                R.reveal_lock.release()
        else:
            R.reveal_lock.release()

        # Before turn check for special ability
        if self.special_active:
            self.character.special(self.gc, self, turn_pos='start')

        # Someone could have died here, so check win conditions
        if self.gc.checkWinConditions(tell=False):
            return  # let the win conditions check in GameContext.play() handle

        # The current player could have died -- if so end their turn
        if self.state == C.PlayerState.Dead:
            return

        # takeTurn
        self._takeTurn()

        # Someone could have died here, so check win conditions
        if self.gc.checkWinConditions(tell=False):
            return  # let the win conditions check in GameContext.play() handle

        # The current player could have died -- if so end their turn
        if self.state == C.PlayerState.Dead:
            return

        # After turn check for special ability
        if self.special_active:
            self.character.special(self.gc, self, turn_pos='end')

    def _takeTurn(self):

        # Roll dice
        self.gc.tell_h("{} is rolling for movement...", [self.user_id])
        roll_result = self.rollDice('area')

        if self.hasEquipment("Mystic Compass"):
            # If player has mystic compass, roll again
            self.gc.tell_h("{}'s {} lets them roll again!",
                           [self.user_id, "Mystic Compass"])
            second_roll = self.rollDice('area')

            # Pick the preferred roll
            data = {'options': ["Use {}".format(
                roll_result), "Use {}".format(second_roll)]}
            answer = self.gc.ask_h('yesno', data, self.user_id)['value']
            roll_result = int(answer[4:])

        # Figure out area to move to
        if roll_result == 7:

            # Select an area
            self.gc.tell_h("{} is selecting an area...", [self.user_id])
            data = {'options': self.gc.getAreas()}
            dst_name = self.gc.ask_h('select', data, self.user_id)['value']

            # Get Area object from area name
            zs = self.gc.zones
            dst = [a for z in zs for a in z.areas if a.name == dst_name][0]

        else:

            # Get area from roll
            dst = self.gc.getAreaFromRoll(roll_result)

            # Get string from area
            dst_name = dst.name

        # Move to area
        self.move(dst)
        self.gc.tell_h("{} moves to {}!", [self.user_id, dst_name])

        # Take area action
        data = {'options': [dst.desc, 'Decline']}
        answer = self.gc.ask_h('yesno', data, self.user_id)['value']
        if answer != 'Decline':
            self.location.action(self.gc, self)
        else:
            self.gc.tell_h(
                '{} declined to perform their area action.', [self.user_id])

        # Someone could have died here, so check win conditions
        if self.gc.checkWinConditions(tell=False):
            return  # let the win conditions check in GameContext.play() handle

        # The current player could have died -- if so end their turn
        if self.state == C.PlayerState.Dead:
            return

        # Attack
        self.attackSequence(dice_type=self.modifiers['attack_dice_type'])

    def attackSequence(self, dice_type="attack"):

        # Give player option to attack or decline
        self.gc.tell_h("{} is deciding to attack...", [self.user_id])
        options = ["Attack other players!"]
        if not self.hasEquipment("Cursed Sword Masamune"):
            options.append("Decline")

        answer = self.gc.ask_h(
            'yesno', {'options': options}, self.user_id)["value"]

        if answer != "Decline":
            # Get attackable players
            live_players = self.gc.getLivePlayers(lambda p: p.location)
            targets = [p for p in live_players if (
                    p.location.zone == self.location.zone and p != self)]

            if self.hasEquipment("Handgun"):
                self.gc.tell_h("{}'s {} reverses their attack range.", [
                    self.user_id, "Handgun"])
                targets = [p for p in live_players if (
                        p.location.zone != self.location.zone and p != self)]

            # If player has Masamune, can't decline unless there are no options
            opts = [t.user_id for t in targets]
            if not self.hasEquipment("Cursed Sword Masamune") or not len(opts):
                opts.append("Decline")

            answer = self.gc.ask_h('select', {'options': opts}, self.user_id)
            answer = answer['value']

            if answer != 'Decline':

                # Get target
                target_name = answer
                target_Player = self.gc.getLivePlayers(
                    lambda x: x.user_id == target_name
                )[0]
                self.gc.tell_h(
                    "{} is attacking {}!",
                    [self.user_id, target_name]
                )

                # Roll with the 4-sided die if the player has masamune
                roll_result = 0
                if self.hasEquipment("Cursed Sword Masamune"):
                    self.gc.tell_h(
                        "{} rolls with the 4-sided die using the {}!",
                        [self.user_id, "Cursed Sword Masamune"]
                    )
                    roll_result = self.rollDice('4')
                else:
                    roll_result = self.rollDice(dice_type)

                # If player has Machine Gun, launch attack on everyone in the
                # zone. Otherwise, attack the target
                if self.hasEquipment("Machine Gun"):
                    self.gc.tell_h(
                        "{}'s {} hits everyone in their attack range!",
                        [self.user_id, "Machine Gun"]
                    )
                else:
                    targets = [target_Player]

                for t in targets:
                    # Dry run the attack if we're Bob
                    if self.modifiers['steal_for_damage']:
                        potential_damage = self.attack(
                            t,
                            roll_result,
                            dryrun=True
                        )
                        if potential_damage >= 3 and len(t.equipment):
                            # Ask whether to steal equipment or deal damage
                            data = {
                                'options': [
                                    "Steal equipment",
                                    "Don't steal equipment",
                                ]
                            }
                            choose_steal = self.gc.ask_h(
                                'yesno', data, self.user_id
                            )['value'] == "Steal equipment"

                            if choose_steal:
                                desired_eq = self.chooseEquipment(t)
                                t.giveEquipment(self, desired_eq)
                                self.gc.tell_h(
                                    ("{} stole {}'s {}"),
                                    [self.user_id, t.user_id, desired_eq.title, ]
                                )
                                # Actually deal damage
                                damage_dealt = self.attack(t, roll_result)
                            else:
                                # Actually deal damage
                                damage_dealt = self.attack(t, roll_result)
                        else:
                            # Actually deal damage
                            damage_dealt = self.attack(t, roll_result)
                    else:
                        # Actually deal damage
                        damage_dealt = self.attack(t, roll_result)

            else:
                self.gc.tell_h("{} declined to attack.", [self.user_id])
        else:
            self.gc.tell_h("{} declined to attack.", [self.user_id])

    def drawCard(self, deck):

        # Draw card and tell frontend about it
        drawn = deck.drawCard()
        is_hermit = drawn.color == C.CardType.Hermit
        public_title = drawn.title if not is_hermit else 'a Hermit Card'
        self.gc.tell_h("{} drew {}!", [self.user_id, public_title])
        display_data = drawn.dump()
        display_data['type'] = 'draw'
        if not is_hermit:
            self.gc.show_h(display_data)
        else:
            self.gc.show_h(display_data, self.socket_id)

        # Use card if it's single-use, or add to arsenal if it's equipment
        if drawn.is_equipment:
            self.gc.ask_h('confirm', {'options': [
                "Add {} to arsenal".format(drawn.title)]},
                          self.user_id)
            self.gc.tell_h("{} added {} to their arsenal!",
                           [self.user_id, public_title])
            self.equipment.append(drawn)
            self.gc.update_h()
        else:
            args = {'self': self, 'card': drawn}
            drawn.use(args)

    def rollDice(self, type):

        # Preprocess all rolls
        assert type in ["area", "attack", "6", "4"]
        roll_4 = self.gc.die4.roll()
        roll_6 = self.gc.die6.roll()
        diff = abs(roll_4 - roll_6)
        sum = roll_4 + roll_6

        # Set values based on type of roll
        if type == "area":
            ask_data = {'options': ['Roll the dice!']}
            display_data = {'type': 'roll',
                            '4-sided': roll_4, '6-sided': roll_6}
            message = ("{} rolled {}!", [self.user_id, sum])
            result = sum
        elif type == "attack":
            ask_data = {'options': ['Roll for damage!']}
            display_data = {'type': 'roll',
                            '4-sided': roll_4, '6-sided': roll_6}
            message = ("{} rolled {}!", [self.user_id, diff])
            result = diff
        elif type == "6":
            ask_data = {'options': ['Roll the 6-sided die!']}
            display_data = {'type': 'roll', '4-sided': 0, '6-sided': roll_6}
            message = ("{} rolled a {}!", [self.user_id, roll_6])
            result = roll_6
        elif type == "4":
            ask_data = {'options': ['Roll the 4-sided die!']}
            display_data = {'type': 'roll', '4-sided': roll_4, '6-sided': 0}
            message = ("{} rolled a {}!", [self.user_id, roll_4])
            result = roll_4

        # Ask for confirmation and display results
        self.gc.ask_h('confirm', ask_data, self.user_id)
        self.gc.show_h(display_data)
        self.gc.tell_h(message[0], message[1])
        return result

    def choosePlayer(self, include_self=False, filter_fn=(lambda x: True)):

        # Select a player from all live players who arent you
        if not include_self:
            opts = [p for p in self.gc.getLivePlayers() if p != self]
        else:
            opts = self.gc.getLivePlayers()

        opts = list(filter(filter_fn, opts))

        if not len(opts):  # nobody to choose from
            return None

        data = {'options': [p.user_id for p in opts]}

        self.gc.tell_h("{} is choosing a player...", [self.user_id])
        target = self.gc.ask_h('select', data, self.user_id)['value']

        # Return the chosen player
        target_Player = [p for p in self.gc.getLivePlayers()
                         if p.user_id == target][0]
        self.gc.tell_h("{} chose {}!", [self.user_id, target])
        return target_Player

    def chooseEquipment(self, target):

        # Select an equipment card belonging to the given target
        data = {'options': [eq.title for eq in target.equipment]}
        equip = self.gc.ask_h('select', data, self.user_id)['value']

        # Return the selected equipment card
        equip_Equipment = [
            eq for eq in target.equipment if eq.title == equip][0]
        return equip_Equipment

    def giveEquipment(self, receiver, eq):

        # Transfer equipment
        i = self.equipment.index(eq)
        eq = self.equipment.pop(i)
        receiver.equipment.append(eq)
        eq.holder = receiver

        # Tell frontend about transfer
        self.gc.tell_h("{} forfeited their {} to {}!", [
            self.user_id, eq.title, receiver.user_id])
        self.gc.update_h()

    def hasEquipment(self, equipment_name):
        return equipment_name in [eq.title for eq in self.equipment]

    def attack(self, other, amount, dryrun=False):

        # Compose equipment functions
        is_attack = True
        successful = (amount != 0)
        for eq in self.equipment:
            if eq.use:
                amount = eq.use(is_attack, successful, amount)

        # Check for spear of longinus
        has_spear = self.hasEquipment("Spear of Longinus")
        is_hunter = self.character.alleg == C.Alleg.Hunter
        is_revealed = self.state == C.PlayerState.Revealed
        if successful and is_hunter and is_revealed and has_spear and self.damage >= 7:
            if not dryrun:
                self.gc.tell_h("{} strikes with their {}!", [
                    self.user_id, "Spear of Longinus"])
            amount += 2

        # Return damage dealt
        dealt = other.defend(self, amount, dryrun)

        # If we dealt damage, some specials might have external effects
        if dealt > 0:
            if self.modifiers['damage_dealt_fn']:
                self.modifiers['damage_dealt_fn'](self)

        return dealt

    def defend(self, other, amount, dryrun=False):

        # Check for guardian angel
        if self.modifiers['guardian_angel']:
            if not dryrun:
                self.gc.tell_h("{}\'s {} shielded them from damage!", [
                    self.user_id, "Guardian Angel"])
            return 0

        # Compose equipment functions
        is_attack = False
        successful = False
        for eq in self.equipment:
            if eq.use:
                amount = eq.use(is_attack, successful, amount)

        # Return damage dealt
        dealt = amount
        if dryrun:
            return dealt

        self.moveDamage(-dealt, attacker=other)
        self.gc.tell_h("{} hit {} for {} damage!", [
            other.user_id, self.user_id, dealt])

        if self.state != C.PlayerState.Dead:
            # Check for counterattack
            if self.modifiers['counterattack']:
                # Ask if player wants to counterattack
                self.gc.tell_h(
                    "{}, the {}, is deciding whether to counterattack!",
                    [self.user_id, "Werewolf"])
                answer = self.gc.ask_h(
                    'confirm', {'options': ["Counterattack", "Decline"]},
                    self.user_id)['value']

                if answer != "Decline":
                    self.gc.tell_h("{} is counterattacking!", [self.user_id])
                    # Roll with the 4-sided die if the player has masamune
                    roll_result = 0
                    if self.hasEquipment("Cursed Sword Masamune"):
                        self.gc.tell_h(
                            "{} rolls with the 4-sided die using the {}!",
                            [self.user_id, "Cursed Sword Masamune"]
                        )
                        roll_result = self.rollDice('4')
                    else:
                        roll_result = self.rollDice(
                            self.modifiers['attack_dice_type'])
                    self.attack(other, roll_result)
                else:
                    self.gc.tell_h(
                        "{} declined to counterattack.",
                        [self.user_id]
                    )

        return dealt

    def moveDamage(self, damage_change, attacker):

        # Tell frontend to animate sprite
        if damage_change < 0:
            self.gc.show_h({'type': 'damage', 'player': self.dump()})

        # Set new damage
        self.damage = min(self.damage - damage_change,
                          self.character.max_damage)
        self.damage = max(0, self.damage)
        self.checkDeath(attacker)
        return self.damage

    def setDamage(self, damage, attacker):
        if damage < self.damage:
            self.gc.show_h({'type': 'damage', 'player': self.dump()})
        self.damage = damage
        self.checkDeath(attacker)

    def checkDeath(self, attacker):
        if self.damage >= self.character.max_damage:
            self.gc.update_h()
            self.die(attacker)
        self.gc.update_h()

    def die(self, attacker):

        # Set state to dead
        R.reveal_lock.acquire()
        self.state = C.PlayerState.Dead
        R.reveal_lock.release()

        # Report to console
        display_data = {'type': 'die', 'player': self.dump()}
        self.gc.show_h(display_data)

        # Equipment stealing if dead player has equipment
        if self.equipment and self != attacker:

            has_silver_rosary = ("Silver Rosary" in [
                e.title for e in attacker.equipment])
            has_steal_all_mod = attacker.modifiers['steal_all_on_kill']

            if has_silver_rosary or has_steal_all_mod:

                # Steal all of the player's equipment
                if has_silver_rosary:
                    self.gc.tell_h(
                        "{}'s {} let them steal all of {}'s equipment!",
                        [attacker.user_id, "Silver Rosary", self.user_id]
                    )
                else:
                    msg = "{} ({}) stole all of {}'s equipment"
                    msg += " using their special ability!"
                    self.gc.tell_h(
                        msg,
                        [attacker.user_id, "Bob", self.user_id]
                    )

                attacker.equipment += self.equipment
                for eq in attacker.equipment:
                    eq.holder = attacker
                self.equipment = []
                self.gc.update_h()

            else:

                # Choose which equipment to take
                self.gc.ask_h(
                    'confirm', {
                        'options': [
                            'Take equipment from {}'.format(self.user_id)
                        ]
                    }, attacker.user_id
                )
                equip_Equipment = attacker.chooseEquipment(self)

                # Transfer equipment from one player to the other
                self.giveEquipment(attacker, equip_Equipment)

        # Put remaining equipment back in the deck (discard pile)
        while self.equipment:
            eq = self.equipment.pop()
            if eq.color == C.CardType.Black:
                self.gc.black_cards.addToDiscard(eq)
            elif eq.color == C.CardType.White:
                self.gc.white_cards.addToDiscard(eq)

            # Green cards should never be popped here

        # Set self to null location
        self.location = None

        # PK: handle bob kill
        if attacker.character.name == "Bob" and self.character.name != "Bob":
            if self.character.alleg != C.Alleg.Neutral:
                attacker.setDamage(20, attacker)
            else:
                attacker.modifiers["killed_neutral"] = True

    def move(self, location):
        self.location = location
        self.gc.update_h()

    def dump(self):
        return {
            'user_id': self.user_id,
            'socket_id': self.socket_id,
            'color': self.color,
            'state': self.state.value,
            'equipment': [eq.dump() for eq in self.equipment],
            'damage': self.damage,
            'character': self.character.dump() if self.character else {},
            'location': self.location.dump() if self.location else {},
            'special_active': self.special_active,
            'ai': self.ai,
            'delexicalizations': self.delexicalizations
        }

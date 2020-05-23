import random
import json


class AgentInterface():
    """Defines an agent that can interact with the game"""

    def __init__(self):
        pass

    def choose_action(self, options, player, gc):
        """Choose an action from the options provided"""
        raise NotImplementedError

    def choose_reveal(self, player, gc):
        """Return true if the agent chooses to reveal"""
        raise NotImplementedError


class RandomAgent(AgentInterface):
    """Defines an agent that randomly interacts with the game"""

    def choose_action(self, options, player, gc):
        """Choose an action from the options provided"""

        if 'Decline' in options and len(options) > 1:
            options.remove('Decline')
        return {'value': random.choice(options)}

    def choose_reveal(self, player, gc):
        """Return true if the agent chooses to reveal"""
        reveal_chance = gc.round_count / 20
        return (random.random() <= reveal_chance)


class DevRandomAgent(AgentInterface):
    """Defines an agent that randomly interacts with the game"""

    def choose_action(self, options, player, gc):
        """Choose an action from the options provided"""

        print("\n" * 4)
        print("=========================")
        print(f"PLAYER {player.user_id}")
        print("=========================")
        print("-----")
        print(f"Options")
        print("-----")
        print(options)
        public_state, private_state = gc.dump()
        priv = [p for p in private_state if p['user_id'] == player.user_id]
        print("-----")
        print(f"Public state")
        print("-----")
        print(json.dumps(public_state['players'], indent=4))
        print("-----")
        print(f"Private state")
        print("-----")
        print(json.dumps(priv, indent=4))
        if 'Decline' in options and len(options) > 1:
            options.remove('Decline')
        return {'value': random.choice(options)}

    def choose_reveal(self, player, gc):
        """Return true if the agent chooses to reveal"""
        reveal_chance = gc.round_count / 20
        return (random.random() <= reveal_chance)


class RLAgent(AgentInterface):
    """Defines an RL agent that interacts with the game"""

    def choose_action(self, options, player, gc):
        """Choose an action from the options provided"""
        if len(options) == 1:
            # If there's only one possible option, don't think too hard :-)
            return {'value': options[0]}

        pass

    def choose_reveal(self, player, gc):
        """Return true if the agent chooses to reveal"""
        pass


Agent = DevRandomAgent

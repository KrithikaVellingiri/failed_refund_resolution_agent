from app.schemas.state import CaseState, ALLOWED_TRANSITIONS

class InvalidTransitionError(ValueError):
    def __init__(self, current_state: CaseState, next_state: CaseState):
        super().__init__(f"Invalid transition from {current_state} to {next_state}")
        self.current_state = current_state
        self.next_state = next_state

def validate_transition(current_state: CaseState, next_state: CaseState):
    """
    Validates whether a transition from current_state to next_state is allowed.
    Raises InvalidTransitionError if the transition is invalid.
    """
    allowed_next_states = ALLOWED_TRANSITIONS.get(current_state, set())
    if next_state not in allowed_next_states:
        raise InvalidTransitionError(current_state, next_state)
    return True

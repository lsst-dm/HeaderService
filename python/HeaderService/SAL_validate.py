import os
import sys
import logging
import HeaderService.states as states

LOGGER = logging.getLogger(__name__)

def validate_transition(current_state, new_state):
    current_index = states.state_enumeration[current_state]
    new_index = states.state_enumeration[new_state]
    transition_is_valid = states.state_matrix[current_index][new_index]
    return transition_is_valid 

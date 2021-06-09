import logging
import os
import re
import en_core_web_sm
import inflect
import sentry_sdk

import common.constants as common_constants
import common.dialogflow_framework.stdm.dialogflow_extention as dialogflow_extention
import common.dialogflow_framework.utils.state as state_utils
from common.utils import is_no
import dialogflows.scopes as scopes
from dialogflows.flows.wild_animals_states import State as WAS
from dialogflows.flows.animals_states import State as AnimalsState
from common.animals import PETS_TEMPLATE, stop_about_animals, find_entity_by_types, find_entity_conceptnet, \
    WILD_ANIMALS_Q, ANIMALS_WIKI_Q
from common.fact_retrieval import get_all_facts

sentry_sdk.init(os.getenv('SENTRY_DSN'))
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

nlp = en_core_web_sm.load()
p = inflect.engine()

CONF_1 = 1.0
CONF_2 = 0.99
CONF_3 = 0.95
CONF_4 = 0.0


def plural_nouns(text):
    plural_text = text
    try:
        processed_text = nlp(text)
        processed_tokens = []
        for token in processed_text:
            if token.tag_ == "NNP":
                processed_tokens.append(p.plural_noun(token.text))
            else:
                processed_tokens.append(token.text)
        plural_text = " ".join(processed_tokens)
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.exception(e)
    return plural_text


def activate_after_wiki_skill(vars):
    flag = False
    cross_link = state_utils.get_cross_link(vars, service_name="dff_animals_skill")
    from_skill = cross_link.get("from_service", "")
    isno = is_no(state_utils.get_last_human_utterance(vars))
    if from_skill == "dff_wiki_skill" and isno:
        flag = True
    logger.info(f"activate_after_wiki_skill {cross_link}")
    return flag


def stop_animals_request(ngrams, vars):
    flag = False
    user_uttr = state_utils.get_last_human_utterance(vars)
    shared_memory = state_utils.get_shared_memory(vars)
    if stop_about_animals(user_uttr, shared_memory):
        flag = True
    logger.info(f"stop_animals_request={flag}")
    return flag


def animal_questions_request(ngrams, vars):
    flag = False
    user_uttr = state_utils.get_last_human_utterance(vars)
    annotations = state_utils.get_last_human_utterance(vars)["annotations"]
    found_animal = find_entity_by_types(annotations, {"Q55983715", "Q16521"})
    found_animal_cnet = find_entity_conceptnet(annotations, ["animal"])
    shared_memory = state_utils.get_shared_memory(vars)
    users_wild_animal = shared_memory.get("users_wild_animal", "")
    found_pet = re.findall(PETS_TEMPLATE, user_uttr["text"])
    found_bird = re.findall(r"(\bbird\b|\bbirds\b)", user_uttr["text"])
    used_wild_q = shared_memory.get("used_wild_q", [])
    all_facts_used = len(used_wild_q) == len(WILD_ANIMALS_Q)
    if not found_pet and (found_bird or users_wild_animal or found_animal or found_animal_cnet) and not all_facts_used:
        flag = True
    logger.info(f"animal_questions_request, found_animal {found_animal} users_wild_animal {users_wild_animal}")
    logger.info(f"animal_questions_request={flag}")
    return flag


def animal_questions_response(vars):
    user_uttr = state_utils.get_last_human_utterance(vars)
    annotations = state_utils.get_last_human_utterance(vars)["annotations"]
    shared_memory = state_utils.get_shared_memory(vars)
    users_wild_animal = shared_memory.get("users_wild_animal", "")
    animal_wp = find_entity_by_types(annotations, {"Q55983715", "Q16521"})
    animal_cnet = find_entity_conceptnet(annotations, ["animal"])
    found_bird = re.findall(r"(\bbird\b|\bbirds\b)", user_uttr["text"])
    if animal_wp:
        facts = get_all_facts(annotations, "animal")
        if facts:
            state_utils.save_to_shared_memory(vars, wild_animal_facts=facts)

    cur_animal = ""
    if animal_wp:
        cur_animal = plural_nouns(animal_wp)
    elif animal_cnet:
        cur_animal = plural_nouns(animal_cnet)
    elif users_wild_animal:
        cur_animal = users_wild_animal
    elif found_bird:
        cur_animal = found_bird[0]
    if cur_animal:
        state_utils.save_to_shared_memory(vars, users_wild_animal=cur_animal)

    response = ""
    used_wild_q = shared_memory.get("used_wild_q", [])
    for num, question_info in enumerate(WILD_ANIMALS_Q):
        if num not in used_wild_q:
            statement = question_info["statement"].format(cur_animal)
            question = question_info["question"].format(cur_animal)
            response = f"{statement} {question}".strip().replace("  ", " ")
            used_wild_q.append(num)
            state_utils.save_to_shared_memory(vars, used_wild_q=used_wild_q)
            break

    state_utils.save_to_shared_memory(vars, start=True)
    state_utils.save_to_shared_memory(vars, is_wild=True)
    if response:
        state_utils.set_confidence(vars, confidence=CONF_1)
        state_utils.set_can_continue(vars, continue_flag=common_constants.MUST_CONTINUE)
    else:
        state_utils.set_confidence(vars, confidence=CONF_4)
        state_utils.set_can_continue(vars, continue_flag=common_constants.CAN_NOT_CONTINUE)
    logger.info(f"animal_questions_response: {response}")
    return response


def animal_facts_request(ngrams, vars):
    flag = False
    shared_memory = state_utils.get_shared_memory(vars)
    isno = is_no(state_utils.get_last_human_utterance(vars))
    facts = shared_memory.get("wild_animal_facts", [])
    used_wild_animal_facts = shared_memory.get("used_wild_animal_facts", [])
    if facts and len(facts) > len(used_wild_animal_facts):
        flag = True
    if len(facts) == len(used_wild_animal_facts) + 1 and isno:
        flag = False
    logger.info(f"animal_facts_request={flag}")
    return flag


def animal_facts_response(vars):
    shared_memory = state_utils.get_shared_memory(vars)
    users_wild_animal = shared_memory.get("users_wild_animal", "")
    facts = shared_memory.get("wild_animal_facts", [])
    isno = is_no(state_utils.get_last_human_utterance(vars))
    used_wild_animal_facts = shared_memory.get("used_wild_animal_facts", [])
    found_fact = {}
    found_num = -1
    for num, fact in enumerate(facts):
        if num not in used_wild_animal_facts:
            found_num = num
            found_fact = fact
            used_wild_animal_facts.append(num)
            state_utils.save_to_shared_memory(vars, used_wild_animal_facts=used_wild_animal_facts)
            break
    logger.info(f"animal_facts_response, found_num {found_num} used_wild_animals_facts {used_wild_animal_facts}")
    response = ""
    facts_str = " ".join(found_fact["sentences"][:2]).strip().replace("  ", " ")
    if found_num == 0:
        facts_str = f"I know a lot about {users_wild_animal}. {facts_str}".strip().replace("  ", " ")
    if found_num != len(facts) - 1:
        next_fact = facts[found_num + 1]
        next_title = next_fact["title"]
        question = ANIMALS_WIKI_Q.get(next_title, "").format(users_wild_animal)
        if isno and found_num != 0:
            facts_str = ""
        response = f"{facts_str} {question}".strip().replace("  ", " ")
    else:
        response = facts_str

    if response:
        state_utils.set_confidence(vars, confidence=CONF_1)
        state_utils.set_can_continue(vars, continue_flag=common_constants.MUST_CONTINUE)
    else:
        state_utils.set_confidence(vars, confidence=CONF_4)
        state_utils.set_can_continue(vars, continue_flag=common_constants.CAN_NOT_CONTINUE)
    return response


def to_animals_flow_request(ngrams, vars):
    flag = True
    logger.info(f"to_animals_flow_request={flag}")
    return flag


def error_response(vars):
    state_utils.set_confidence(vars, 0)
    return ""


simplified_dialog_flow = dialogflow_extention.DFEasyFilling(WAS.USR_START)

simplified_dialog_flow.add_user_serial_transitions(
    WAS.USR_START,
    {
        WAS.SYS_ERR: stop_animals_request,
        WAS.SYS_ANIMAL_Q: animal_questions_request,
        (scopes.ANIMALS, AnimalsState.USR_START): to_animals_flow_request,
    },
)

simplified_dialog_flow.add_user_serial_transitions(
    WAS.USR_ANIMAL_Q,
    {
        WAS.SYS_ERR: stop_animals_request,
        WAS.SYS_ANIMAL_Q: animal_questions_request,
        WAS.SYS_ANIMAL_F: animal_facts_request,
        (scopes.ANIMALS, AnimalsState.USR_START): to_animals_flow_request,
    },
)

simplified_dialog_flow.add_user_serial_transitions(
    WAS.USR_ANIMAL_F,
    {
        WAS.SYS_ERR: stop_animals_request,
        WAS.SYS_ANIMAL_F: animal_facts_request,
        (scopes.ANIMALS, AnimalsState.USR_START): to_animals_flow_request,
    },
)

simplified_dialog_flow.add_system_transition(WAS.SYS_ANIMAL_Q, WAS.USR_ANIMAL_Q, animal_questions_response, )
simplified_dialog_flow.add_system_transition(WAS.SYS_ANIMAL_F, WAS.USR_ANIMAL_F, animal_facts_response, )
simplified_dialog_flow.add_system_transition(WAS.SYS_ERR, (scopes.MAIN, scopes.State.USR_ROOT), error_response, )

simplified_dialog_flow.set_error_successor(WAS.USR_START, WAS.SYS_ERR)
simplified_dialog_flow.set_error_successor(WAS.SYS_ANIMAL_Q, WAS.SYS_ERR)
simplified_dialog_flow.set_error_successor(WAS.USR_ANIMAL_Q, WAS.SYS_ERR)
simplified_dialog_flow.set_error_successor(WAS.SYS_ANIMAL_F, WAS.SYS_ERR)
simplified_dialog_flow.set_error_successor(WAS.USR_ANIMAL_F, WAS.SYS_ERR)

dialogflow = simplified_dialog_flow.get_dialogflow()

import functools
import logging
import random
from typing import Any, Callable, Optional, Iterator

from common.dff.integration.processing import save_slots_to_ctx
from df_engine.core import Context, Actor

logger = logging.getLogger(__name__)


@functools.singledispatch
def save_to_slots(slots: Any) -> None:
    """A decorator for saving to slots. Ignores `NoneType`."""
    raise NotImplementedError


@save_to_slots.register
def _(slots: str) -> Callable:
    def slot_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def slot_wrapper(ctx: Context, actor: Actor) -> Optional[str]:
            result = func(ctx, actor)
            if result is None:
                return ctx
            return save_slots_to_ctx({slots: result})(ctx, actor)

        return slot_wrapper

    return slot_decorator


@save_to_slots.register
def _(slots: tuple) -> Callable:
    def slot_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def slot_wrapper(ctx: Context, actor: Actor) -> Context:
            results = func(ctx, actor)
            if results is None:
                return ctx
            return save_slots_to_ctx({slot: result for slot, result in zip(slots, results) if result is not None})(
                ctx, actor
            )

        return slot_wrapper

    return slot_decorator


def save_next_key(keys: Iterator, maindict: dict) -> Callable:
    try:
        return save_slots_to_ctx(maindict[next(keys)])
    except StopIteration:
        return save_slots_to_ctx(maindict[random.choice(list(maindict.keys()))])


def execute_response(
    ctx: Context,
    actor: Actor,
) -> Context:
    """Execute the callable response preemptively,
    so that slots can be filled"""
    processed_node = ctx.a_s.get("processed_node", ctx.a_s["next_node"])
    if callable(processed_node.response):
        processed_node.response = processed_node.response(ctx, actor)
    ctx.a_s["processed_node"] = processed_node

    return ctx


def set_flag(label: str, value: bool = True) -> Callable:
    """Sets a flag, modified coronavirus skill"""

    def set_flag_handler(ctx: Context, actor: Actor) -> Context:
        ctx.misc["flags"] = ctx.misc.get("flags", {})
        ctx.misc["flags"].update({label: value})
        return ctx

    return set_flag_handler

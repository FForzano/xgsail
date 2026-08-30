"""Resolving a guest-boat claim: the two ways a placeholder stops being one.

A guest boat (``boats.is_guest``) is a real ``boats`` row somebody created for
a boat they do not own, so an outing could be recorded against it. When the
actual owner claims it, one of two things happens:

* they have no boat record of their own — ``promote_guest_boat`` hands them the
  existing row, sessions and all;
* they already have one — ``merge_boat`` folds the guest into it and deletes it.

Pure mechanics: the caller (the router) has already decided the claim may be
resolved and by whom. Deliberately no worker dispatch either, same split as
``session_split``: this module only moves rows.
"""

import logging
import uuid

from ..repositories import get_repos

logger = logging.getLogger(__name__)


def promote_guest_boat(boat_id: uuid.UUID, *, new_owner_id: uuid.UUID,
                       previous_owner_id: uuid.UUID) -> None:
    """Hand the guest boat itself to the claimant, keeping every session
    already recorded on it.

    The creator stays on as a ``visitor``: they sailed the boat, and boat
    membership is what gates read access to those sessions — dropping them
    would hide their own outings from them.
    """
    repos = get_repos()
    if repos.boats.get_member(boat_id, new_owner_id) is None:
        repos.boats.add_member(boat_id, user_id=new_owner_id, role="owner")
    else:
        repos.boats.set_member_role(boat_id, new_owner_id, role="owner")

    if previous_owner_id != new_owner_id:
        repos.boats.set_member_role(boat_id, previous_owner_id, role="visitor")

    repos.boats.clear_guest(boat_id)
    logger.info("promoted guest boat %s to owner %s", boat_id, new_owner_id)


def merge_boat(source_id: uuid.UUID, target_id: uuid.UUID) -> dict:
    """Fold guest boat ``source_id`` into the claimant's real boat
    ``target_id`` and delete the guest row.

    Returns per-table counts of what moved. Raises ``ValueError`` for the
    states the caller must reject: an unknown boat, a merge into itself, and a
    source that is not a guest boat — the last one because this deletes the
    source, and doing that to a real boat is not recoverable.
    """
    repos = get_repos()
    source = repos.boats.get(source_id)
    target = repos.boats.get(target_id)
    if source is None or target is None:
        raise ValueError("Boat not found")
    if source_id == target_id:
        raise ValueError("Cannot merge a boat into itself")
    if not source.is_guest:
        raise ValueError("Only a guest boat can be merged away")

    moved = repos.boats.merge_into(source_id, target_id)
    logger.info("merged guest boat %s into %s: %s", source_id, target_id, moved)
    return moved

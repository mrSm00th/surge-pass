def waiting_zset(event_id: str) -> str:

    return f"queue:{event_id}:waiting"


def admitted_counter(event_id: str) -> str:

    return f"queue:{event_id}:admitted_count"


def admitted_set(event_id: str) -> str:

    return f"queue:{event_id}:admitted"


def admission_token(event_id: str, user_id: str) -> str:

    return f"queue:{event_id}:token:{user_id}"


def event_config(event_id: str) -> str:

    return f"queue:{event_id}:config"

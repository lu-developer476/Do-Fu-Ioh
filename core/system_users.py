from django.contrib.auth.models import User

AI_USERNAME = "__dojo_ai__"
SOLO_PLAYER_USERNAME = "__solo_player__"
RESERVED_SYSTEM_USERNAMES = frozenset({AI_USERNAME, SOLO_PLAYER_USERNAME})


def get_or_create_system_user(username: str) -> User:
    if username not in RESERVED_SYSTEM_USERNAMES:
        raise ValueError(f"{username} no es un usuario del sistema reservado.")

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": "",
            "is_active": False,
            "first_name": "system",
            "last_name": "mvp",
        },
    )

    fields_to_update = []
    if user.is_active:
        user.is_active = False
        fields_to_update.append("is_active")
    if user.has_usable_password():
        user.set_unusable_password()
        fields_to_update.append("password")

    if fields_to_update or created:
        user.save(update_fields=fields_to_update or None)

    return user


def get_single_player_system_users() -> tuple[User, User]:
    """Return the shared system actors used by the session-based single-player MVP.

    These users are not an identity mechanism for humans. The real per-player
    ownership for the MVP lives in the Django session that stores the active
    room code.
    """

    return (
        get_or_create_system_user(SOLO_PLAYER_USERNAME),
        get_or_create_system_user(AI_USERNAME),
    )

from fastapi import HTTPException, status

from src.app.core.auth import CurrentUser
from src.app.modules.users.models import User, UserRole


def require_roles(*allowed_roles: UserRole):

    def role_checker(current_user: CurrentUser) -> User:

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your account to access this resource.",
            )
        return current_user

    return role_checker

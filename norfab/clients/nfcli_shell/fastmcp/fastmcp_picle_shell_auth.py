import logging
from typing import Union
from uuid import uuid4

from picle.models import Outputters
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
)

from norfab.workers.fastmcp_worker.fastmcp_models import (
    BearerTokenCheckInput,
    BearerTokenDeleteInput,
    BearerTokenListInput,
    BearerTokenStoreInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job

log = logging.getLogger(__name__)


class CreateAuthToken(
    ClientRunJobArgs,
    BearerTokenStoreInput,
    use_enum_values=True,
    populate_by_name=True,
):
    token: Union[None, StrictStr] = Field(
        None, description="Token string to store, autogenerate if not given"
    )

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        if "token" not in kwargs:
            kwargs["token"] = uuid4().hex

        result = run_future_job(
            "fastmcp",
            "bearer_token_store",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class ListAuthToken(
    ClientRunJobArgs,
    BearerTokenListInput,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "fastmcp",
            "bearer_token_list",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_rich_table
        outputter_kwargs = {"sortby": "worker"}


class DeleteAuthToken(
    ClientRunJobArgs,
    BearerTokenDeleteInput,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "fastmcp",
            "bearer_token_delete",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CheckAuthToken(
    ClientRunJobArgs,
    BearerTokenCheckInput,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "fastmcp",
            "bearer_token_check",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class FastMCPAuthCommandsModel(BaseModel):
    create_token: CreateAuthToken = Field(
        None, description="Create authentication token", alias="create-token"
    )
    list_tokens: ListAuthToken = Field(
        None, description="Retrieve authentication tokens", alias="list-tokens"
    )
    delete_token: DeleteAuthToken = Field(
        None, description="Delete existing authentication token", alias="delete-token"
    )
    check_token: CheckAuthToken = Field(
        None, description="Check if given token valid", alias="check-token"
    )

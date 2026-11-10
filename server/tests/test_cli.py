import pytest

from whaat.cli.main import ForeignInstanceError, running_instance
from whaat.config import Settings


@pytest.fixture
def dev(settings: Settings) -> Settings:
    from dataclasses import replace

    return replace(settings, instance="dev")


def test_nothing_answering_means_start_one(dev: Settings) -> None:
    assert running_instance(dev, None) is False


def test_our_instance_answering_is_used(dev: Settings) -> None:
    assert running_instance(dev, {"app": "whaat", "instance": "dev"}) is True


@pytest.mark.parametrize("health", [{"app": "whaat", "instance": "live"}, {"app": "whaat"}])
def test_another_or_an_unnamed_instance_is_refused(dev: Settings, health: dict[str, object]) -> None:
    with pytest.raises(ForeignInstanceError, match="refusing"):
        running_instance(dev, health)

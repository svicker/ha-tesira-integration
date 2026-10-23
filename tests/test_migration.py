"""Migration of an entry created by the old integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import make_entry, wait_for
from .fake_tesira import FakeTesira


async def test_legacy_entry_migrates_and_keeps_entities(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    entry = make_entry(fake, version=1, unique_id=f"127.0.0.1:{fake.port}")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "media_player",
        "tesira",
        f"{entry.entry_id}_klubraum",
        config_entry=entry,
        suggested_object_id="tesira_klubraum",
    )
    assert entry.options == {}

    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.unique_id == "127.0.0.1"
    assert set(entry.options["zones"]) >= {"klubraum", "ela_saal", "ela_flur"}
    assert entry.options["sources"]["SourceRouterKlubRaum"]["1"] == "Apple TV"
    assert (entry.options["min_db"], entry.options["max_db"]) == (-100.0, 12.0)
    # The registry entry is untouched.
    assert registry.async_get(old.entity_id).unique_id == f"{entry.entry_id}_klubraum"
    assert hass.states.get("media_player.tesira_klubraum").state == "on"


async def test_entry_without_options_works_with_defaults(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    entry = make_entry(fake)  # already v2 but options empty
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    assert hass.states.get("media_player.tesira_saal") is not None

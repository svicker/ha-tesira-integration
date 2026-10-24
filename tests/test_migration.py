"""Migration of an entry created by the old integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.tesira.options import default_options

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
    assert entry.version == 3
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


async def test_v2_entry_migrates_to_v3_gates_and_ducker_name(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    options = default_options().to_dict()
    for zone in options["zones"].values():
        zone["gate"] = None  # as stored by 2.0.x
    options["zones"]["ela_aussen_sitzen"]["ducker"] = "DuckerELAAussenSitzen"
    options["zones"]["saal"]["gate"] = "MeinEigenesGate"  # set by the user: keep
    options["zones"]["ela_theke"]["ducker"] = "MeinDucker"  # set by the user: keep
    entry = make_entry(fake, options, version=2)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    bypass = registry.async_get_or_create(
        "switch",
        "tesira",
        f"{entry.entry_id}_ela_aussen_sitzen_ducker_bypass",
        config_entry=entry,
        suggested_object_id="tesira_ela_aussen_sitzen_ducker_bypass",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()

    zones = entry.options["zones"]
    assert entry.version == 3
    assert zones["klubraum"]["gate"] == "MicGateKlub"
    assert zones["ela_aussen_sitzen"]["gate"] == "MicGateELAAussenSitz"
    assert zones["ela_aussen_sitzen"]["ducker"] == "DuckerELAAussenSitz"
    assert zones["ela_saal"]["gate"] is None
    assert zones["saal"]["gate"] == "MeinEigenesGate"
    assert zones["ela_theke"]["ducker"] == "MeinDucker"
    # The renamed ducker works again and keeps unique_id and entity_id.
    after = registry.async_get(bypass.entity_id)
    assert after.unique_id == f"{entry.entry_id}_ela_aussen_sitzen_ducker_bypass"
    assert hass.states.get(bypass.entity_id).state == "off"
    assert fake.values[("DuckerELAAussenSitz", "bypass", None)] is False
    assert '"DuckerELAAussenSitz" get bypass' in fake.received
    assert not [line for line in fake.received if " set " in line]
    assert hass.states.get("switch.tesira_klubraum_mikrofon") is not None


async def test_legacy_v1_entry_gets_gates_too(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake, version=1, unique_id=f"127.0.0.1:{fake.port}")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    assert entry.version == 3
    assert entry.options["zones"]["klubraum"]["gate"] == "MicGateKlub"
    assert entry.options["zones"]["ela_aussen_sitzen"]["ducker"] == "DuckerELAAussenSitz"

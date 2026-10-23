"""Entity behaviour against the fake Tesira."""

from __future__ import annotations

import asyncio
import logging

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.tesira.const import DEFAULT_ZONES
from custom_components.tesira.options import default_options

from .conftest import make_entry, setup_entry, wait_for
from .fake_tesira import FakeTesira

KLUB = "media_player.tesira_klubraum"
AUSSEN = "media_player.tesira_ela_aussen"
AUSSEN_SITZEN = "media_player.tesira_ela_aussen_sitzen"


def attr(hass: HomeAssistant, entity_id: str, name: str) -> object:
    return hass.states.get(entity_id).attributes.get(name)


async def call(hass: HomeAssistant, service: str, entity_id: str, **data: object) -> None:
    await hass.services.async_call(
        "media_player", service, {"entity_id": entity_id, **data}, blocking=True
    )


async def test_all_entities_keep_their_ids(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    expected = {
        "klubraum": "media_player.tesira_klubraum",
        "saal": "media_player.tesira_saal",
        "ela_saal": "media_player.tesira_ela_saal",
        "ela_kk_stand": "media_player.tesira_ela_kk_stand",
        "ela_theke": "media_player.tesira_ela_theke",
        "ela_aussen": "media_player.tesira_ela_aussen",
        "ela_aussen_sitzen": "media_player.tesira_ela_aussen_sitzen",
        "ela_toilette": "media_player.tesira_ela_toilette",
        "ela_flur": "media_player.tesira_ela_flur",
    }
    assert set(expected) == set(DEFAULT_ZONES)
    for key, entity_id in expected.items():
        reg = registry.async_get(entity_id)
        assert reg is not None, entity_id
        assert reg.unique_id == f"{entry.entry_id}_{key}"
        assert hass.states.get(entity_id).state == "on"
    # ELA Saal has no sources, the others do.
    assert "source_list" not in hass.states.get("media_player.tesira_ela_saal").attributes
    assert "Mikrofon" not in hass.states.get(KLUB).attributes["source_list"]
    assert hass.states.get(KLUB).attributes["source_list"] == [
        "Aus",
        "Apple TV",
        "SAT TV",
        "Musik",
        "PC Theke",
    ]


async def test_initial_state_and_volume_mapping(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    state = hass.states.get(KLUB)
    assert state.attributes["volume_level"] == pytest.approx(0.6)
    assert state.attributes["source"] == "Musik"
    assert state.attributes["is_volume_muted"] is False


async def test_volume_round_trip(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    await call(hass, "volume_set", KLUB, volume_level=0.6)
    await wait_for(lambda: '"LevelKlubRaum" set level 1 -32.8' in fake.received)
    await fake.set_external("LevelKlubRaum", "level", -100.0, 1)
    await wait_for(lambda: attr(hass, KLUB, "volume_level") == 0.0)
    await fake.set_external("LevelKlubRaum", "level", 12.0, 1)
    await wait_for(lambda: attr(hass, KLUB, "volume_level") == 1.0)
    await fake.set_external("LevelKlubRaum", "level", -32.8, 1)
    await wait_for(lambda: attr(hass, KLUB, "volume_level") == pytest.approx(0.6))


async def test_volume_writes_are_throttled(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    for step in range(1, 21):
        await call(hass, "volume_set", KLUB, volume_level=step / 40)
    await wait_for(lambda: fake.values[("LevelKlubRaum", "level", 1)] == -44.0)
    sent = [line for line in fake.received if "set level" in line and "LevelKlubRaum" in line]
    assert len(sent) < 20
    assert sent[-1] == '"LevelKlubRaum" set level 1 -44.0'


async def test_volume_step(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    await call(hass, "volume_up", KLUB)
    await wait_for(lambda: fake.values[("LevelKlubRaum", "level", 1)] == pytest.approx(-31.8))


async def test_mute(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    await call(hass, "volume_mute", KLUB, is_volume_muted=True)
    assert fake.values[("LevelKlubRaum", "mute", 1)] is True
    assert hass.states.get(KLUB).state == "idle"
    assert attr(hass, KLUB, "is_volume_muted") is True
    await fake.set_external("LevelKlubRaum", "mute", False, 1)
    await wait_for(lambda: hass.states.get(KLUB).state == "on")


async def test_select_source_and_read_back_push(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    await call(hass, "select_source", KLUB, source="Apple TV")
    assert fake.values[("SourceRouterKlubRaum", "sourceSelection", None)] == 1
    assert attr(hass, KLUB, "source") == "Apple TV"
    # Changed from outside (Tesira software) shows up without polling.
    await fake.set_external("SourceRouterKlubRaum", "sourceSelection", 4)
    await wait_for(lambda: attr(hass, KLUB, "source") == "PC Theke")
    await call(hass, "select_source", KLUB, source="Aus")
    assert fake.values[("SourceRouterKlubRaum", "sourceSelection", None)] == 0


async def test_unknown_source_name_is_rejected(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    with pytest.raises(HomeAssistantError):
        await call(hass, "select_source", KLUB, source="Mikrofon")


async def test_shared_router_keeps_both_zones_in_step(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    await setup_entry(hass, make_entry(fake))
    await call(hass, "select_source", AUSSEN, source="SAT TV")
    assert attr(hass, AUSSEN, "source") == "SAT TV"
    assert attr(hass, AUSSEN_SITZEN, "source") == "SAT TV"
    await fake.set_external("SourceRouterAussen", "sourceSelection", 1)
    await wait_for(lambda: attr(hass, AUSSEN, "source") == "Apple TV")
    assert attr(hass, AUSSEN_SITZEN, "source") == "Apple TV"
    # Only one router command per change, not one per zone.
    assert fake.received.count('"SourceRouterAussen" set sourceSelection 2') == 1


async def test_unknown_source_index_gives_none_and_warns_once(
    hass: HomeAssistant, fake: FakeTesira, caplog: pytest.LogCaptureFixture
) -> None:
    await setup_entry(hass, make_entry(fake))
    with caplog.at_level(logging.WARNING):
        await fake.set_external("SourceRouterKlubRaum", "sourceSelection", 9)
        await wait_for(lambda: attr(hass, KLUB, "source") is None)
        await fake.set_external("SourceRouterKlubRaum", "sourceSelection", 8)
        await wait_for(
            lambda: len([r for r in caplog.records if "not in the source" in r.message]) == 2
        )
    assert attr(hass, KLUB, "source") is None
    assert hass.states.get(KLUB).state == "on"
    # One warning per distinct index (9 and 8), not one per update.
    await fake.set_external("SourceRouterKlubRaum", "sourceSelection", 9)
    await fake.set_external("SourceRouterKlubRaum", "sourceSelection", 8)
    await asyncio.sleep(0.1)
    warnings = [r for r in caplog.records if "not in the source list" in r.message]
    assert len(warnings) == 2


async def test_err_from_device(
    hass: HomeAssistant, fake: FakeTesira, caplog: pytest.LogCaptureFixture
) -> None:
    options = default_options().to_dict()
    options["zones"]["klubraum"]["level"] = "LevelDoesNotExist"
    await setup_entry(hass, make_entry(fake, options))
    # Setup survives, the broken zone just has no values, others work.
    assert hass.states.get(KLUB).attributes["volume_level"] == 0.0
    assert hass.states.get("media_player.tesira_saal").attributes["volume_level"] > 0.5
    assert any("rejected" in r.message for r in caplog.records)
    with pytest.raises(HomeAssistantError):
        await call(hass, "volume_mute", KLUB, is_volume_muted=True)
    # The next command is still paired correctly.
    await call(hass, "select_source", "media_player.tesira_saal", source="Aus")
    assert fake.values[("SourceRouterSaal", "sourceSelection", None)] == 0


async def test_reconnect_resubscribes_and_reloads_state(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    await setup_entry(hass, make_entry(fake))
    port = fake.port
    await fake.stop()
    await wait_for(lambda: hass.states.get(KLUB).state == "unavailable")
    # Changed while the Tesira was off:
    fake.values[("SourceRouterKlubRaum", "sourceSelection", None)] = 2
    await fake.start(port)
    await wait_for(lambda: hass.states.get(KLUB).state == "on")
    assert hass.states.get(KLUB).attributes["source"] == "SAT TV"
    # Subscriptions were renewed on the new connection: pushes arrive again.
    await fake.set_external("LevelKlubRaum", "mute", True, 1)
    await wait_for(lambda: hass.states.get(KLUB).state == "idle")


async def test_connection_drop_recovers(hass: HomeAssistant, fake: FakeTesira) -> None:
    await setup_entry(hass, make_entry(fake))
    await fake.drop_connections()
    await wait_for(lambda: hass.states.get(KLUB).state != "unavailable" or fake.connection_count)
    await wait_for(lambda: hass.states.get(KLUB).state == "on" and fake.connection_count == 1)


async def test_device_offline_at_startup_then_comes_up(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    port = fake.port
    await fake.stop()
    entry = make_entry(fake)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(KLUB).state == "unavailable"
    await fake.start(port)
    await wait_for(lambda: hass.states.get(KLUB).state == "on")


async def test_unload_closes_connection(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    assert fake.connection_count == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    await wait_for(lambda: fake.connection_count == 0)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_gate_switch_only_with_tag(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("switch", "tesira", f"{entry.entry_id}_klubraum_mic_gate")
        is None
    )
    await hass.config_entries.async_unload(entry.entry_id)

    options = default_options().to_dict()
    options["zones"]["klubraum"]["gate"] = "MicGateKlub"
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()
    entity_id = registry.async_get_entity_id(
        "switch", "tesira", f"{entry.entry_id}_klubraum_mic_gate"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "off"  # gate muted = microphones blocked
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    assert fake.values[("MicGateKlub", "mute", 1)] is False
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"


async def test_ducker_entities_disabled_by_default(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    for suffix, domain in (("ducker_bypass", "switch"), ("ducking_level", "number")):
        entity_id = registry.async_get_entity_id(
            domain, "tesira", f"{entry.entry_id}_klubraum_{suffix}"
        )
        assert entity_id is not None
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None
    # Disabled entities cost nothing on the wire.
    assert not any("DuckerKlubRaum" in line for line in fake.received)


async def test_enabled_ducker_entities_read_and_write(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    entry = make_entry(fake)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    switch = registry.async_get_or_create(
        "switch", "tesira", f"{entry.entry_id}_klubraum_ducker_bypass", config_entry=entry
    )
    number = registry.async_get_or_create(
        "number", "tesira", f"{entry.entry_id}_klubraum_ducking_level", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    await wait_for(lambda: hass.states.get(number.entity_id).state == "-20.0")
    assert hass.states.get(switch.entity_id).state == "off"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch.entity_id}, blocking=True
    )
    assert fake.values[("DuckerKlubRaum", "bypass", None)] is True
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number.entity_id, "value": -12.5}, blocking=True
    )
    assert fake.values[("DuckerKlubRaum", "duckingLevel", None)] == -12.5
    await fake.set_external("DuckerKlubRaum", "bypass", False)
    await wait_for(lambda: hass.states.get(switch.entity_id).state == "off")

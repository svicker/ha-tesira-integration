"""Config flow, reconfigure flow, options flow, diagnostics."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.tesira.const import DOMAIN
from custom_components.tesira.diagnostics import async_get_config_entry_diagnostics
from custom_components.tesira.options import default_options

from .conftest import make_entry, setup_entry, wait_for
from .fake_tesira import FakeTesira

KLUB = "media_player.tesira_klubraum"


async def start_user_flow(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result["flow_id"]


async def test_user_flow_creates_entry(hass: HomeAssistant, fake: FakeTesira) -> None:
    flow_id = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"host": "127.0.0.1", "port": fake.port, "name": "Tesira"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tesira"
    assert result["data"]["host"] == "127.0.0.1"
    entry = result["result"]
    assert entry.unique_id == "127.0.0.1"
    assert entry.version == 3
    await wait_for(lambda: hass.states.get(KLUB) and hass.states.get(KLUB).state == "on")


async def test_user_flow_cannot_connect(hass: HomeAssistant, fake: FakeTesira) -> None:
    port = fake.port
    await fake.stop()
    flow_id = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"host": "127.0.0.1", "port": port, "name": "Tesira"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    await fake.start(port)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"host": "127.0.0.1", "port": port, "name": "Tesira"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    server = FakeTesira(username="admin", password="secret")
    server.add("LevelSaal", "level", -1.0, 1)
    await server.start()
    try:
        flow_id = await start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {"host": "127.0.0.1", "port": server.port, "name": "Tesira"}
        )
        assert result["errors"] == {"base": "invalid_auth"}
        result = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                "host": "127.0.0.1",
                "port": server.port,
                "name": "Tesira",
                "username": "admin",
                "password": "wrong",
            },
        )
        assert result["errors"] == {"base": "invalid_auth"}
    finally:
        await server.stop()


async def test_duplicate_host_is_refused(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    flow_id = await start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {"host": "127.0.0.1", "port": fake.port, "name": "Other"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_port(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    second = FakeTesira()
    second.add("LevelKlubRaum", "level", -10.0, 1)
    second.add("LevelKlubRaum", "mute", False, 1)
    await second.start()
    try:
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "127.0.0.1", "port": second.port}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data["port"] == second.port
        await wait_for(lambda: second.connection_count == 1)
    finally:
        await second.stop()


async def test_options_flow_changes_source_list(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"router": "SourceRouterKlubRaum"}
    )
    assert result["step_id"] == "sources_edit"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"sources_text": "0=Aus\n1=Radio\n2=Gast-PC", "prefill": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["sources"]["SourceRouterKlubRaum"] == {
        "0": "Aus",
        "1": "Radio",
        "2": "Gast-PC",
    }
    # Other routers keep their list.
    assert entry.options["sources"]["SourceRouterSaal"]["1"] == "Apple TV"
    await hass.async_block_till_done()
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()
    assert hass.states.get(KLUB).attributes["source_list"] == ["Aus", "Radio", "Gast-PC"]
    # Router value 3 is no longer in the list, so no source is shown.
    assert hass.states.get(KLUB).attributes.get("source") is None
    await hass.services.async_call(
        "media_player", "select_source", {"entity_id": KLUB, "source": "Gast-PC"}, blocking=True
    )
    assert fake.values[("SourceRouterKlubRaum", "sourceSelection", None)] == 2


@pytest.mark.parametrize(
    "text",
    ["", "Aus", "0=Aus\n0=Nochmal", "0=Aus\n1=Aus", "x=Aus", "0="],
)
async def test_options_flow_rejects_bad_source_lists(
    hass: HomeAssistant, fake: FakeTesira, text: str
) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"router": "SourceRouterSaal"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"sources_text": text, "prefill": False}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_sources"}


async def test_options_flow_prefill_reads_labels_only(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    fake.add("SourceRouterSaal", "numInputs", 2)
    fake.add("SourceRouterSaal", "inputLabel", "Fernseher", 1)
    fake.add("SourceRouterSaal", "inputLabel", "Anlage", 2)
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    fake.received.clear()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"router": "SourceRouterSaal"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"sources_text": "0=Aus", "prefill": True}
    )
    assert result["type"] is FlowResultType.FORM
    assert not result["errors"]
    assert fake.received == [
        '"SourceRouterSaal" get numInputs',
        '"SourceRouterSaal" get inputLabel 1',
        '"SourceRouterSaal" get inputLabel 2',
    ]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"sources_text": "0=Aus\n1=Fernseher\n2=Anlage", "prefill": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def edit_zone(hass: HomeAssistant, entry_id: str, zone: str) -> str:
    result = await hass.config_entries.options.async_init(entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "zones"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"zone": zone})
    assert result["step_id"] == "zone_edit"
    return result["flow_id"]


BASE = {
    "name": "Klubraum",
    "router": "SourceRouterKlubRaum",
    "level": "LevelKlubRaum",
    "gate": "MicGateKlub",
    "ducker": "DuckerKlubRaum",
}


async def test_options_flow_validates_tags_and_clears_gate(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_klubraum_mic_gate"
    assert registry.async_get_entity_id("switch", DOMAIN, unique_id) is not None
    flow_id = await edit_zone(hass, entry.entry_id, "klubraum")

    bad = await hass.config_entries.options.async_configure(flow_id, {**BASE, "gate": 'Bad"Tag'})
    assert bad["errors"] == {"base": "invalid_tag"}
    missing = await hass.config_entries.options.async_configure(flow_id, {**BASE, "level": ""})
    assert missing["errors"] == {"base": "required"}

    # Unknown tags are reported at the field, and nothing is written.
    fake.received.clear()
    unknown_gate = await hass.config_entries.options.async_configure(
        flow_id, {**BASE, "gate": "MicGateGibtEsNicht"}
    )
    assert unknown_gate["errors"] == {"gate": "unknown_tag"}
    unknown_ducker = await hass.config_entries.options.async_configure(
        flow_id, {**BASE, "ducker": "DuckerGibtEsNicht"}
    )
    assert unknown_ducker["errors"] == {"ducker": "unknown_tag"}
    assert '"MicGateGibtEsNicht" get mute 1' in fake.received
    assert '"DuckerGibtEsNicht" get bypass' in fake.received
    assert not [line for line in fake.received if " set " in line]
    assert not entry.options  # nothing was saved by the failed attempts

    # Leaving the gate empty removes the switch.
    done = await hass.config_entries.options.async_configure(
        flow_id, {k: v for k, v in BASE.items() if k != "gate"}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["zones"]["klubraum"]["gate"] is None
    await hass.async_block_till_done()
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("switch", DOMAIN, unique_id) is None
    # The unique_id of the media player itself did not change.
    assert registry.async_get(KLUB).unique_id == f"{entry.entry_id}_klubraum"


async def test_options_flow_unchanged_tags_are_not_rechecked(
    hass: HomeAssistant, fake: FakeTesira
) -> None:
    options = default_options().to_dict()
    options["zones"]["klubraum"]["gate"] = "MicGateGibtEsNicht"  # already saved earlier
    entry = make_entry(fake, options)
    await setup_entry(hass, entry)
    flow_id = await edit_zone(hass, entry.entry_id, "klubraum")
    fake.received.clear()
    done = await hass.config_entries.options.async_configure(
        flow_id, {**BASE, "name": "Klub", "gate": "MicGateGibtEsNicht"}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert '"MicGateGibtEsNicht" get mute 1' not in fake.received


async def test_options_flow_offline_skips_tag_check(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    flow_id = await edit_zone(hass, entry.entry_id, "klubraum")
    await fake.stop()
    await wait_for(lambda: not entry.runtime_data.connected)
    done = await hass.config_entries.options.async_configure(
        flow_id, {**BASE, "gate": "MicGateIrgendwas"}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_level_limits(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "levels"}
    )
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"], {"min_db": 0, "max_db": -10}
    )
    assert bad["errors"] == {"base": "invalid_range"}
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], {"min_db": -60, "max_db": 0}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()
    # -32.8 dB in a -60..0 range:
    assert hass.states.get(KLUB).attributes["volume_level"] == pytest.approx(27.2 / 60)


async def test_diagnostics(hass: HomeAssistant, fake: FakeTesira) -> None:
    entry = make_entry(fake)
    await setup_entry(hass, entry)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["config"]["host"] == "**REDACTED**"
    assert "127.0.0.1" not in str(data["config"])
    assert data["connected"] is True
    assert data["values"]["LevelKlubRaum.level.1"] == -32.8
    assert data["values"]["SourceRouterKlubRaum.sourceSelection"] == 3
    assert 0 < len(data["protocol_log"]) <= 50
    assert data["options"] == {} or "zones" in data["options"]

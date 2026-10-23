"""Config flow, reconfigure flow and options flow."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import TesiraAuthError, TesiraClient, TesiraConnectionError
from .const import (
    CONFIG_VERSION,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    OPT_MAX_DB,
    OPT_MIN_DB,
    OPT_SOURCES,
    OPT_ZONES,
)
from .options import parse_options, valid_tag

_LOGGER = logging.getLogger(__name__)

CONF_ZONE = "zone"
CONF_ROUTER = "router"
CONF_SOURCES = "sources_text"
CONF_PREFILL = "prefill"


def _connection_schema(defaults: Mapping[str, Any], *, with_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(
            CONF_USERNAME, description={"suggested_value": defaults.get(CONF_USERNAME)}
        ): str,
        vol.Optional(
            CONF_PASSWORD, description={"suggested_value": defaults.get(CONF_PASSWORD)}
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
    if with_name:
        fields[vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = str
    return vol.Schema(fields)


async def _async_test(data: Mapping[str, Any]) -> str | None:
    """Try to connect; return an error key or None."""
    client = TesiraClient(
        data[CONF_HOST],
        data[CONF_PORT],
        username=data.get(CONF_USERNAME) or None,
        password=data.get(CONF_PASSWORD) or None,
    )
    try:
        await client.probe()
    except TesiraAuthError:
        return "invalid_auth"
    except (TesiraConnectionError, OSError):
        return "cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error while testing the connection")
        return "unknown"
    return None


def _clean(user_input: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_HOST] = str(data[CONF_HOST]).strip()
    for key in (CONF_USERNAME, CONF_PASSWORD):
        if not data.get(key):
            data.pop(key, None)
    return data


class TesiraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Tesira."""

    VERSION = CONFIG_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TesiraOptionsFlow:
        return TesiraOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            await self.async_set_unique_id(data[CONF_HOST].lower())
            self._abort_if_unique_id_configured()
            if error := await _async_test(data):
                errors["base"] = error
            else:
                return self.async_create_entry(title=data.get(CONF_NAME, DEFAULT_NAME), data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema({}, with_name=True), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            existing = await self.async_set_unique_id(data[CONF_HOST].lower())
            if existing is not None and existing.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")
            if error := await _async_test(data):
                errors["base"] = error
            else:
                new_data = {**entry.data, **data}
                for key in (CONF_USERNAME, CONF_PASSWORD):
                    if key not in data:
                        new_data.pop(key, None)
                return self.async_update_reload_and_abort(
                    entry, unique_id=data[CONF_HOST].lower(), data=new_data
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or entry.data, with_name=False),
            errors=errors,
        )


class TesiraOptionsFlow(OptionsFlow):
    """Zones, source lists and level limits."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._zone_key: str | None = None
        self._router: str | None = None

    def _load(self) -> None:
        if not self._options:
            self._options = parse_options(self.config_entry.options).to_dict()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._load()
        return self.async_show_menu(step_id="init", menu_options=["zones", "sources", "levels"])

    # -- zones ---------------------------------------------------------

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._zone_key = user_input[CONF_ZONE]
            return await self.async_step_zone_edit()
        choices = [
            SelectOptionDict(value=key, label=zone["name"])
            for key, zone in self._options[OPT_ZONES].items()
        ]
        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE): SelectSelector(
                        SelectSelectorConfig(options=choices, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def async_step_zone_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._zone_key is not None
        zones: dict[str, dict[str, Any]] = self._options[OPT_ZONES]
        current = zones[self._zone_key]
        errors: dict[str, str] = {}
        if user_input is not None:
            values = {key: (user_input.get(key) or "").strip() for key in current}
            tags = [
                values["level"],
                *(values[k] for k in ("router", "gate", "ducker") if values[k]),
            ]
            if not values["name"] or not values["level"]:
                errors["base"] = "required"
            elif not all(valid_tag(tag) for tag in tags):
                errors["base"] = "invalid_tag"
            else:
                zones[self._zone_key] = {
                    "name": values["name"],
                    "level": values["level"],
                    "router": values["router"] or None,
                    "gate": values["gate"] or None,
                    "ducker": values["ducker"] or None,
                }
                if values["router"] and values["router"] not in self._options[OPT_SOURCES]:
                    defaults = parse_options({}).sources
                    fallback = next(iter(defaults.values()))
                    self._options[OPT_SOURCES][values["router"]] = {
                        str(index): name for index, name in fallback.items()
                    }
                return self.async_create_entry(data=self._options)
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("router"): str,
                vol.Required("level"): str,
                vol.Optional("gate"): str,
                vol.Optional("ducker"): str,
            }
        )
        return self.async_show_form(
            step_id="zone_edit",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or current),
            description_placeholders={"zone": current["name"]},
            errors=errors,
        )

    # -- sources -------------------------------------------------------

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._router = user_input[CONF_ROUTER]
            return await self.async_step_sources_edit()
        routers = sorted({z["router"] for z in self._options[OPT_ZONES].values() if z["router"]})
        if not routers:
            return self.async_abort(reason="no_routers")
        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ROUTER): SelectSelector(
                        SelectSelectorConfig(options=routers, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def async_step_sources_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._router is not None
        sources: dict[str, dict[str, str]] = self._options[OPT_SOURCES]
        errors: dict[str, str] = {}
        text = _sources_to_text(sources.get(self._router, {}))
        if user_input is not None:
            text = user_input.get(CONF_SOURCES, text)
            if user_input.get(CONF_PREFILL):
                labels = await self._async_read_labels(self._router)
                if labels:
                    text = _sources_to_text({str(i): n for i, n in labels.items()})
                else:
                    errors["base"] = "prefill_failed"
            else:
                parsed = _parse_sources(text)
                if parsed is None:
                    errors["base"] = "invalid_sources"
                else:
                    sources[self._router] = {str(i): n for i, n in parsed.items()}
                    return self.async_create_entry(data=self._options)
        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCES): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional(CONF_PREFILL, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="sources_edit",
            data_schema=self.add_suggested_values_to_schema(schema, {CONF_SOURCES: text}),
            description_placeholders={"router": self._router},
            errors=errors,
        )

    async def _async_read_labels(self, router: str) -> dict[int, str]:
        """Ask the running integration for the router's input labels (read-only)."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or not runtime.connected:
            return {}
        try:
            labels: dict[int, str] = await runtime.async_read_input_labels(router)
            return labels
        except (TesiraConnectionError, ValueError):
            return {}

    # -- level limits --------------------------------------------------

    async def async_step_levels(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            low, high = float(user_input[OPT_MIN_DB]), float(user_input[OPT_MAX_DB])
            if low >= high:
                errors["base"] = "invalid_range"
            else:
                self._options[OPT_MIN_DB] = low
                self._options[OPT_MAX_DB] = high
                return self.async_create_entry(data=self._options)
        selector = NumberSelector(
            NumberSelectorConfig(
                min=-200, max=50, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="dB"
            )
        )
        schema = vol.Schema(
            {vol.Required(OPT_MIN_DB): selector, vol.Required(OPT_MAX_DB): selector}
        )
        return self.async_show_form(
            step_id="levels",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or {k: self._options[k] for k in (OPT_MIN_DB, OPT_MAX_DB)}
            ),
            errors=errors,
        )


def _sources_to_text(sources: Mapping[Any, str]) -> str:
    return "\n".join(f"{index}={name}" for index, name in sorted(sources.items(), key=_order))


def _order(item: tuple[Any, str]) -> int:
    return int(item[0])


def _parse_sources(text: str) -> dict[int, str] | None:
    """Parse ``index=name`` lines; None if invalid (bad line, duplicate)."""
    result: dict[int, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        index_text, sep, name = line.partition("=")
        name = name.strip()
        if not sep or not name or not index_text.strip().isdigit():
            return None
        index = int(index_text.strip())
        if index in result or name in result.values():
            return None
        result[index] = name
    return result or None

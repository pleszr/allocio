"""Non-persisting allocation estimates for asset-creation review."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.exceptions import ValidationError
from app.domain import calculator
from app.domain.asset_templates import ASSET_TEMPLATES, AssetTemplate
from app.domain.template_catalog import catalog_keys, overridable_catalog_keys
from app.repository import user_repository


@dataclass(frozen=True)
class EstimateCostInput:
    """One user-entered recurring cost that has not been persisted."""

    client_key: str
    label: str
    amount: Decimal
    interval_value: int
    interval_unit: calculator.IntervalUnit


@dataclass(frozen=True)
class EstimateCostOverride:
    """One edited template amount and optional recurrence interval."""

    technical_key: str
    amount: Decimal
    interval_value: int | None
    interval_unit: calculator.IntervalUnit | None


@dataclass(frozen=True)
class AllocationEstimateLine:
    """Canonical derived values for one recurring wizard row."""

    key: str
    label: str
    reference_amount: Decimal
    annualized_amount: Decimal
    monthly_amount: Decimal
    daily_rate: Decimal


@dataclass(frozen=True)
class AllocationEstimate:
    """Canonical recurring-cost estimate returned to the wizard."""

    currency: str
    lines: list[AllocationEstimateLine]
    daily_total: Decimal
    monthly_total: Decimal
    yearly_total: Decimal


class AllocationEstimateService:
    """Build allocation estimates from backend templates and unsaved custom rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def estimate(
        self,
        user_id: uuid.UUID,
        template_key: str | None,
        selected_cost_keys: list[str] | None,
        cost_overrides: list[EstimateCostOverride] | None,
        custom_time_based_costs: list[EstimateCostInput] | None,
        manual_extra_monthly: Decimal | None = None,
    ) -> AllocationEstimate:
        """Return a quantized estimate without adding, flushing, or committing any rows."""
        currency = self._owner_currency(user_id)
        template = self._resolve_template(template_key)
        selected = self._validate_selection(template, selected_cost_keys)
        overrides = self._validate_overrides(template, selected, cost_overrides)
        inputs = self._template_inputs(template, selected, overrides, currency) + list(
            custom_time_based_costs or ()
        )
        self._validate_inputs(inputs)
        manual_extra = self._resolve_manual_extra(template, currency, manual_extra_monthly)
        lines = [self._line(cost, currency) for cost in inputs]
        if manual_extra > 0:
            lines.append(self._manual_extra_line(manual_extra, currency))

        yearly = sum(
            (
                calculator.time_based_annualized_amount(
                    cost.amount, cost.interval_value, cost.interval_unit
                )
                for cost in inputs
            ),
            Decimal(0),
        ) + manual_extra * Decimal(12)
        return AllocationEstimate(
            currency=currency,
            lines=lines,
            daily_total=calculator.quantize_currency(yearly / calculator.DAYS_PER_YEAR, currency),
            monthly_total=calculator.quantize_currency(yearly / Decimal(12), currency),
            yearly_total=calculator.quantize_currency(yearly, currency),
        )

    def _owner_currency(self, user_id: uuid.UUID) -> str:
        user = user_repository.get_by_id(self._session, user_id)
        if user is None:
            raise ValidationError(f"Owner '{user_id}' not found.")
        return user.default_currency

    def _resolve_template(self, template_key: str | None) -> AssetTemplate | None:
        """Resolve a template key, returning None for a template-less estimate."""
        if template_key is None:
            return None
        template = ASSET_TEMPLATES.get(template_key)
        if template is None:
            raise ValidationError(f"Unknown asset template '{template_key}'.")
        return template

    def _validate_selection(
        self, template: AssetTemplate | None, selected_keys: list[str] | None
    ) -> set[str]:
        selected = set(selected_keys or ())
        if template is None:
            if selected:
                raise ValidationError("Cost selection requires a template.")
            return set()
        unknown = selected - catalog_keys(template.catalog)
        if unknown:
            raise ValidationError(f"Unknown cost keys: {sorted(unknown)}.")
        return selected

    def _validate_overrides(
        self,
        template: AssetTemplate | None,
        selected: set[str],
        overrides: list[EstimateCostOverride] | None,
    ) -> dict[str, EstimateCostOverride]:
        by_key: dict[str, EstimateCostOverride] = {}
        overridable = (
            overridable_catalog_keys(template.catalog) if template is not None else frozenset()
        )
        for override in overrides or ():
            if override.technical_key in by_key:
                raise ValidationError(f"Duplicate cost override for '{override.technical_key}'.")
            if override.technical_key not in selected:
                raise ValidationError(f"Cost override for unselected key '{override.technical_key}'.")
            if override.technical_key not in overridable:
                raise ValidationError(f"Cost key '{override.technical_key}' does not accept an override.")
            if override.amount < 0:
                raise ValidationError("Cost amounts must not be negative.")
            if (override.interval_value is None) != (override.interval_unit is None):
                raise ValidationError("interval_value and interval_unit must be set together or both omitted.")
            by_key[override.technical_key] = override
        return by_key

    def _validate_inputs(self, inputs: list[EstimateCostInput]) -> None:
        """Enforce service-layer money/interval invariants even outside the HTTP schema."""
        seen: set[str] = set()
        for cost in inputs:
            if cost.client_key in seen:
                raise ValidationError(f"Duplicate estimate row key '{cost.client_key}'.")
            seen.add(cost.client_key)
            if cost.amount < 0:
                raise ValidationError("Cost amounts must not be negative.")
            try:
                calculator.interval_years(cost.interval_value, cost.interval_unit)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

    def _template_inputs(
        self,
        template: AssetTemplate | None,
        selected: set[str],
        overrides: dict[str, EstimateCostOverride],
        currency: str,
    ) -> list[EstimateCostInput]:
        """Resolve selected time-based rows; valid usage/maintenance selections contribute no steady estimate."""
        inputs: list[EstimateCostInput] = []
        if template is None:
            return inputs
        for row in template.catalog.time_based_costs:
            if row.technical_key not in selected:
                continue
            override = overrides.get(row.technical_key)
            inputs.append(
                EstimateCostInput(
                    client_key=row.technical_key,
                    label=row.label,
                    amount=override.amount if override is not None else row.amounts[currency],
                    interval_value=(
                        override.interval_value
                        if override is not None and override.interval_value is not None
                        else row.interval_value
                    ),
                    interval_unit=(
                        override.interval_unit
                        if override is not None and override.interval_unit is not None
                        else row.interval_unit
                    ),
                )
            )
        return inputs

    def _resolve_manual_extra(
        self,
        template: AssetTemplate | None,
        currency: str,
        manual_extra_monthly: Decimal | None,
    ) -> Decimal:
        """Use an explicit monthly buffer or the selected template's currency default."""
        if manual_extra_monthly is not None:
            if manual_extra_monthly < 0:
                raise ValidationError("Manual extra must not be negative.")
            return manual_extra_monthly
        if template is None:
            return Decimal(0)
        try:
            return template.manual_extra_monthly_amounts[currency]
        except KeyError as exc:
            raise ValidationError(
                f"Template '{template.key}' has no manual extra default for currency '{currency}'."
            ) from exc

    def _line(self, cost: EstimateCostInput, currency: str) -> AllocationEstimateLine:
        annualized = calculator.time_based_annualized_amount(
            cost.amount, cost.interval_value, cost.interval_unit
        )
        return AllocationEstimateLine(
            key=cost.client_key,
            label=cost.label,
            reference_amount=calculator.quantize_currency(cost.amount, currency),
            annualized_amount=calculator.quantize_currency(annualized, currency),
            monthly_amount=calculator.quantize_currency(annualized / Decimal(12), currency),
            daily_rate=calculator.quantize_currency(annualized / calculator.DAYS_PER_YEAR, currency),
        )

    def _manual_extra_line(self, monthly_amount: Decimal, currency: str) -> AllocationEstimateLine:
        """Build the final estimate line for a positive flat monthly safety buffer."""
        annualized = monthly_amount * Decimal(12)
        return AllocationEstimateLine(
            key="manual_extra",
            label="Manual extra",
            reference_amount=calculator.quantize_currency(monthly_amount, currency),
            annualized_amount=calculator.quantize_currency(annualized, currency),
            monthly_amount=calculator.quantize_currency(monthly_amount, currency),
            daily_rate=calculator.quantize_currency(annualized / calculator.DAYS_PER_YEAR, currency),
        )
